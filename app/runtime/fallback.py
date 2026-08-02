"""LiteLLM-style model fallbacks when an upstream deployment fails."""
from __future__ import annotations

import logging
from typing import Any, AsyncIterator

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.llm import LLMModel
from app.runtime.provider_manager import ProviderManager
from app.runtime.vllm_routing import load_active_model, resolve_vllm_base_url

logger = logging.getLogger(__name__)

_RETRYABLE_HTTP = {408, 429, 500, 502, 503, 504}


def is_retryable_upstream_error(exc: BaseException) -> bool:
    """True when another deployment in the chain should be tried."""
    if isinstance(
        exc,
        (
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.WriteTimeout,
            httpx.PoolTimeout,
            httpx.RemoteProtocolError,
            httpx.NetworkError,
        ),
    ):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_HTTP
    if isinstance(exc, RuntimeError):
        msg = str(exc).lower()
        return "api_base" in msg or "no usable" in msg
    return False


def normalize_fallback_ids(raw: list[str] | None, *, self_id: str | None = None) -> list[str]:
    """Dedupe while preserving order; drop empty / self references."""
    out: list[str] = []
    seen: set[str] = set()
    for item in raw or []:
        mid = (item or "").strip()
        if not mid or mid in seen:
            continue
        if self_id and mid == self_id:
            continue
        seen.add(mid)
        out.append(mid)
    return out


async def load_fallback_chain(db: AsyncSession, primary: LLMModel) -> list[LLMModel]:
    """
    Primary first, then active fallback models that have a usable api_base.
    Skips missing/inactive entries without failing the whole request.
    """
    chain: list[LLMModel] = [primary]
    seen = {primary.id}
    for mid in normalize_fallback_ids(getattr(primary, "fallback_model_ids", None) or [], self_id=primary.id):
        if mid in seen:
            continue
        seen.add(mid)
        model = await load_active_model(db, mid)
        if model is None:
            logger.warning("♻️ Fallback skip | id=%s | reason=missing_or_inactive", mid)
            continue
        if not resolve_vllm_base_url(model):
            logger.warning("♻️ Fallback skip | id=%s | reason=no_api_base", mid)
            continue
        chain.append(model)
    return chain


async def generate_with_fallback(
    db: AsyncSession,
    primary: LLMModel,
    messages: list[dict[str, Any]],
    *,
    max_tokens: int,
    temperature: float,
) -> tuple[dict[str, Any], LLMModel]:
    """Try primary then fallbacks; return (response, model_actually_used)."""
    chain = await load_fallback_chain(db, primary)
    last_err: BaseException | None = None

    for i, model in enumerate(chain):
        try:
            if not resolve_vllm_base_url(model):
                raise RuntimeError(f"Model {model.id!r} has no usable api_base")
            generator = ProviderManager.get_provider(model)
            result = await generator.generate(
                messages, max_tokens=max_tokens, temperature=temperature
            )
            if i > 0:
                logger.warning(
                    "♻️ Fallback OK | primary=%s | used=%s | tried=%d",
                    primary.id,
                    model.id,
                    i + 1,
                )
                try:
                    from app.core.request_metrics import record_fallback_success
                    await record_fallback_success(primary.id)
                except Exception:
                    pass
            return result, model
        except Exception as e:
            last_err = e
            has_next = i < len(chain) - 1
            if has_next and is_retryable_upstream_error(e):
                logger.warning(
                    "♻️ Fallback next | failed=%s → try=%s | err=%s",
                    model.id,
                    chain[i + 1].id,
                    e,
                )
                continue
            raise

    assert last_err is not None
    raise last_err


async def generate_stream_with_fallback(
    db: AsyncSession,
    primary: LLMModel,
    messages: list[dict[str, Any]],
    *,
    max_tokens: int,
    temperature: float,
) -> AsyncIterator[tuple[str, LLMModel]]:
    """
    Stream tokens from the first healthy deployment.
    Fallback only if the failure happens before any token is yielded.
    Yields (token, model_used).
    """
    chain = await load_fallback_chain(db, primary)
    last_err: BaseException | None = None

    for i, model in enumerate(chain):
        yielded = False
        try:
            if not resolve_vllm_base_url(model):
                raise RuntimeError(f"Model {model.id!r} has no usable api_base")
            generator = ProviderManager.get_provider(model)
            async for token in generator.generate_stream(
                messages, max_tokens=max_tokens, temperature=temperature
            ):
                yielded = True
                yield token, model
            if i > 0:
                logger.warning(
                    "♻️ Fallback stream OK | primary=%s | used=%s",
                    primary.id,
                    model.id,
                )
                try:
                    from app.core.request_metrics import record_fallback_success
                    await record_fallback_success(primary.id)
                except Exception:
                    pass
            return
        except Exception as e:
            last_err = e
            if yielded:
                raise
            has_next = i < len(chain) - 1
            if has_next and is_retryable_upstream_error(e):
                logger.warning(
                    "♻️ Fallback stream next | failed=%s → try=%s | err=%s",
                    model.id,
                    chain[i + 1].id,
                    e,
                )
                continue
            raise

    assert last_err is not None
    raise last_err
