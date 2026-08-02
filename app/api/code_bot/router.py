"""
Direct vLLM access endpoints for Cline / Cursor / OpenHands.
Auth: X-API-Key header (or Bearer <key>).
Mounted at: /code_bot/v1/

Acts as a lightweight reverse proxy to vLLM — no RAG, no context
processing, no conversation tracking.  Just auth + passthrough.

Routing:
  - Looks up the request ``model`` in llm_llmmodel (id or model_path)
  - Uses that row's ``base_url`` when set; else settings.VLLM_BASE_URL
  - Rewrites body.model to the DB ``model_path`` (vLLM --served-model-name)
"""
from __future__ import annotations

import json
import logging
import time
from typing import AsyncIterator

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_api_key
from app.database import get_db
from app.models.llm import LLMModel
from app.models.user import User
from app.config import get_settings
from app.runtime.vllm_routing import load_active_model, resolve_vllm_base_url
from app.runtime.fallback import is_retryable_upstream_error, load_fallback_chain
from app.core.request_metrics import record_model_request
from app.services.token_utils import estimate_message_tokens, estimate_text_tokens

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(tags=["Code Bot Direct"])


async def _forward_headers(request: Request) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
    }
    for key in ("Authorization", "X-API-Key", "Cookie"):
        val = request.headers.get(key)
        if val:
            headers[key] = val
    return headers


def _extract_usage_from_payload(payload: dict) -> int:
    usage = payload.get("usage") or {}
    total = usage.get("total_tokens")
    if total:
        return int(total)
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    return prompt + completion


async def _prepare_upstream(
    db: AsyncSession,
    body: dict,
) -> tuple[str, dict]:
    """Return (vllm_base_url, body with model rewritten to model_path)."""
    chain = await _prepare_upstream_chain(db, body)
    if not chain:
        return resolve_vllm_base_url(None), dict(body)
    return chain[0][0], chain[0][1]


async def _prepare_upstream_chain(
    db: AsyncSession,
    body: dict,
) -> list[tuple[str, dict, str]]:
    """Ordered (base_url, body, gateway_model_id) attempts including fallbacks."""
    client_model = body.get("model")
    if isinstance(client_model, str):
        client_model = client_model.strip() or None
    else:
        client_model = None

    model = await load_active_model(db, client_model) if client_model else None
    if model is None:
        base = resolve_vllm_base_url(None)
        return [(base, dict(body), client_model or "")] if base else []

    chain_models = await load_fallback_chain(db, model)
    out: list[tuple[str, dict, str]] = []
    for m in chain_models:
        base = resolve_vllm_base_url(m)
        if not base:
            continue
        rewritten = dict(body)
        if m.model_path:
            rewritten["model"] = m.model_path
        if m.id != model.id:
            logger.warning(
                "♻️ code_bot fallback candidate | primary=%s | try=%s | base=%s",
                model.id,
                m.id,
                base,
            )
        elif rewritten.get("model") != body.get("model"):
            logger.info(
                "🔀 code_bot rewrite model %r → %r | base_url=%s",
                client_model,
                m.model_path,
                base,
            )
        out.append((base, rewritten, m.id))
    return out


async def _stream_from_vllm(
    body: dict,
    headers: dict,
    base_url: str,
    api_key_id: str | None = None,
) -> AsyncIterator[bytes]:
    """Async generator that streams bytes from vLLM while keeping client alive."""
    total_tokens = 0
    completion_parts: list[str] = []
    upstream = f"{base_url.rstrip('/')}/chat/completions"

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(settings.VLLM_REQUEST_TIMEOUT, connect=10.0),
    ) as client:
        async with client.stream(
            "POST",
            upstream,
            json=body,
            headers=headers,
        ) as resp:
            if resp.status_code != 200:
                error_body = await resp.aread()
                yield json.dumps({"error": error_body.decode()}).encode()
                return
            async for chunk in resp.aiter_bytes():
                yield chunk
                if not api_key_id:
                    continue
                try:
                    text = chunk.decode("utf-8", errors="ignore")
                    for line in text.splitlines():
                        if not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if not data_str or data_str == "[DONE]":
                            continue
                        payload = json.loads(data_str)
                        usage_tokens = _extract_usage_from_payload(payload)
                        if usage_tokens:
                            total_tokens = usage_tokens
                        delta = (payload.get("choices") or [{}])[0].get("delta") or {}
                        content = delta.get("content")
                        if content:
                            completion_parts.append(content)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass

    if api_key_id:
        if not total_tokens:
            messages = body.get("messages") or []
            prompt_tokens = sum(estimate_message_tokens(m) for m in messages)
            completion_tokens = estimate_text_tokens("".join(completion_parts))
            total_tokens = prompt_tokens + completion_tokens
        if total_tokens > 0:
            from app.core.rate_limit import record_tokens
            await record_tokens(api_key_id, total_tokens)


@router.get("/models")
async def list_models(
    request: Request,
    user: User = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    List gateway-registered models (so clients see every active DB model).

    Each entry ``id`` is the gateway public id; ``root`` is the served name.
    """
    result = await db.execute(
        select(LLMModel).where(LLMModel.is_active.is_(True)).order_by(LLMModel.id)
    )
    rows = result.scalars().all()
    if rows:
        data = [
            {
                "id": m.id,
                "object": "model",
                "created": 0,
                "owned_by": "gateway",
                "root": m.model_path,
            }
            for m in rows
        ]
        return JSONResponse(content={"object": "list", "data": data})

    # Fallback: proxy single default vLLM if DB has no models
    base = resolve_vllm_base_url(None)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{base}/models",
                headers=await _forward_headers(request),
            )
            resp.raise_for_status()
            return JSONResponse(content=resp.json())
    except httpx.HTTPStatusError as e:
        return JSONResponse(
            status_code=e.response.status_code,
            content={"error": f"vLLM error: {e.response.text}"},
        )
    except Exception as e:
        logger.exception("Failed to proxy models request to vLLM")
        return JSONResponse(
            status_code=502,
            content={"error": f"Failed to reach vLLM: {str(e)}"},
        )


@router.post("/chat/completions")
async def chat_completions(
    request: Request,
    user: User = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Direct passthrough to the vLLM instance for the selected model.

    No RAG, no flattening, no conversation tracking — pure vLLM.
    Supports both streaming and non-streaming responses.
    """
    try:
        body = await request.json()
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"error": f"Invalid JSON body: {str(e)}"},
        )

    chain = await _prepare_upstream_chain(db, body)
    if not chain:
        return JSONResponse(
            status_code=503,
            content={"error": "No usable upstream api_base for this model"},
        )

    is_stream = bool(body.get("stream", False))
    headers = await _forward_headers(request)
    api_key_id = getattr(request.state, "api_key_id", None)
    client_model = body.get("model") if isinstance(body.get("model"), str) else chain[0][2]

    if is_stream:
        base_url, upstream_body, _mid = chain[0]
        return StreamingResponse(
            _stream_from_vllm(upstream_body, headers, base_url, api_key_id=api_key_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    started = time.perf_counter()
    last_error: Exception | None = None
    data = None
    used_fallback = False
    for i, (base_url, upstream_body, mid) in enumerate(chain):
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(settings.VLLM_REQUEST_TIMEOUT, connect=10.0),
            ) as client:
                resp = await client.post(
                    f"{base_url.rstrip('/')}/chat/completions",
                    json=upstream_body,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
            if i > 0:
                used_fallback = True
                logger.warning("♻️ code_bot fallback OK | used=%s", mid)
            break
        except Exception as e:
            last_error = e
            has_next = i < len(chain) - 1
            if has_next and is_retryable_upstream_error(e):
                logger.warning(
                    "♻️ code_bot fallback next | failed=%s → try=%s | err=%s",
                    mid,
                    chain[i + 1][2],
                    e,
                )
                continue
            latency_ms = (time.perf_counter() - started) * 1000.0
            await record_model_request(
                model_id=str(client_model or "unknown"),
                latency_ms=latency_ms,
                ok=False,
                used_fallback=False,
            )
            if isinstance(e, httpx.HTTPStatusError):
                return JSONResponse(
                    status_code=e.response.status_code,
                    content={"error": f"vLLM error: {e.response.text}"},
                )
            logger.exception("Failed to proxy chat/completions request to vLLM")
            return JSONResponse(
                status_code=502,
                content={"error": f"vLLM proxy error: {str(e)}"},
            )

    if data is None:
        err = last_error or RuntimeError("upstream failed")
        latency_ms = (time.perf_counter() - started) * 1000.0
        await record_model_request(
            model_id=str(client_model or "unknown"),
            latency_ms=latency_ms,
            ok=False,
        )
        return JSONResponse(
            status_code=502,
            content={"error": f"vLLM proxy error: {str(err)}"},
        )

    usage = data.get("usage") or {}
    total_tokens = _extract_usage_from_payload(data)
    latency_ms = (time.perf_counter() - started) * 1000.0
    await record_model_request(
        model_id=str(client_model or "unknown"),
        latency_ms=latency_ms,
        ok=True,
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
        total_tokens=total_tokens,
        used_fallback=used_fallback,
    )

    if api_key_id and total_tokens > 0:
        from app.core.rate_limit import record_tokens
        await record_tokens(api_key_id, total_tokens)

    return JSONResponse(content=data)
