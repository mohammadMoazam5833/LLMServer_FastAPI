"""Admin CRUD for LLM connections + models (LiteLLM-aligned registry).

LiteLLM concepts we mirror:
  - Connection  ≈ shared credential + api_base + custom_llm_provider
  - Model.id    ≈ model_name (what clients send)
  - model_path  ≈ upstream model id (served name / ollama tag)
  - provider    ≈ openai | vllm | ollama (OpenAI-compatible HTTP today)

Delete connection ⇒ linked models are deactivated and unlinked (route stops),
matching LiteLLM "remove deployment / credential" behaviour.
"""
from __future__ import annotations

import re
from typing import Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import decrypt_api_key, encrypt_api_key, mask_api_key
from app.models.llm import LLMConnection, LLMModel
from app.runtime.fallback import normalize_fallback_ids
from app.runtime.vllm_routing import resolve_vllm_base_url

_SLUG_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")

# LiteLLM-style custom_llm_provider values we support for OpenAI-compatible HTTP.
SUPPORTED_PROVIDER_TYPES = {"openai", "vllm", "ollama"}
_PROVIDER_ALIASES = {
    "openai_compatible": "openai",
    "hosted_vllm": "vllm",
}


def _require_slug(value: str, field: str = "id") -> str:
    value = (value or "").strip()
    if not _SLUG_RE.match(value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field}: use letters, digits, . _ - (max 64)",
        )
    return value


async def _validate_fallback_ids(
    db: AsyncSession,
    *,
    self_id: str,
    fallback_model_ids: list[str] | None,
) -> list[str]:
    ids = normalize_fallback_ids(fallback_model_ids, self_id=self_id)
    for mid in ids:
        other = await db.get(LLMModel, mid)
        if other is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"fallback model not found: {mid}",
            )
    return ids


def _normalize_provider_type(provider_type: str) -> str:
    raw = (provider_type or "openai").strip().lower()
    raw = _PROVIDER_ALIASES.get(raw, raw)
    if raw not in SUPPORTED_PROVIDER_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider_type (supported: {sorted(SUPPORTED_PROVIDER_TYPES)})",
        )
    return raw


def _normalize_base_url(url: str, provider_type: str = "openai") -> str:
    """
    Normalize api_base like LiteLLM expects for OpenAI-compatible calls.
    For ollama, if user passes http://host:11434 we append /v1 (OpenAI compat).
    """
    url = (url or "").strip().rstrip("/")
    if not url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="api_base / base_url is required",
        )
    if not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="base_url must start with http:// or https://",
        )
    if provider_type == "ollama" and not url.endswith("/v1"):
        url = f"{url}/v1"
    return url


def connection_to_dict(conn: LLMConnection) -> dict[str, Any]:
    return {
        "id": conn.id,
        "name": conn.name,
        "provider_type": conn.provider_type,
        "base_url": conn.base_url,
        "api_key_hint": conn.api_key_hint or "",
        "has_api_key": bool(conn.api_key_encrypted),
        "is_active": conn.is_active,
        "created_at": conn.created_at,
    }


def model_to_dict(model: LLMModel) -> dict[str, Any]:
    return {
        "id": model.id,
        "model_path": model.model_path,
        "base_url": model.base_url,
        "effective_base_url": resolve_vllm_base_url(model),
        "connection_id": model.connection_id,
        "provider": model.provider,
        "context_length": model.context_length,
        "max_output_tokens": model.max_output_tokens,
        "is_active": model.is_active,
        "fallback_model_ids": list(getattr(model, "fallback_model_ids", None) or []),
        "created_at": model.created_at,
    }


async def list_connections(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(LLMConnection).order_by(LLMConnection.created_at.desc())
    )
    return [connection_to_dict(c) for c in result.scalars().all()]


async def create_connection(
    db: AsyncSession,
    *,
    id: str,
    name: str,
    base_url: str,
    provider_type: str = "vllm",
    api_key: str | None = None,
    is_active: bool = True,
) -> dict:
    cid = _require_slug(id)
    provider_type = _normalize_provider_type(provider_type)
    existing = await db.get(LLMConnection, cid)
    if existing:
        raise HTTPException(status_code=409, detail="Connection id already exists")

    raw_key = (api_key or "").strip() or None
    conn = LLMConnection(
        id=cid,
        name=(name or cid).strip(),
        provider_type=provider_type,
        base_url=_normalize_base_url(base_url, provider_type),
        api_key_encrypted=encrypt_api_key(raw_key) if raw_key else None,
        api_key_hint=mask_api_key(raw_key) if raw_key else "",
        is_active=is_active,
    )
    db.add(conn)
    await db.flush()
    await db.refresh(conn)
    return connection_to_dict(conn)


async def update_connection(
    db: AsyncSession,
    connection_id: str,
    *,
    name: str | None = None,
    base_url: str | None = None,
    provider_type: str | None = None,
    api_key: str | None = None,
    clear_api_key: bool = False,
    is_active: bool | None = None,
) -> dict:
    conn = await db.get(LLMConnection, connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    if name is not None:
        conn.name = name.strip() or conn.name
    if provider_type is not None:
        conn.provider_type = _normalize_provider_type(provider_type)
    if base_url is not None:
        conn.base_url = _normalize_base_url(base_url, conn.provider_type)
    if clear_api_key:
        conn.api_key_encrypted = None
        conn.api_key_hint = ""
    elif api_key is not None and api_key.strip():
        raw = api_key.strip()
        conn.api_key_encrypted = encrypt_api_key(raw)
        conn.api_key_hint = mask_api_key(raw)

    deactivating = is_active is False and conn.is_active
    if is_active is not None:
        conn.is_active = is_active

    result = await db.execute(
        select(LLMModel).where(LLMModel.connection_id == conn.id)
    )
    linked = list(result.scalars().all())

    # Keep model api_base + provider in sync with connection (LiteLLM credential bind)
    for model in linked:
        model.base_url = conn.base_url
        model.provider = conn.provider_type
        if deactivating:
            model.is_active = False

    await db.flush()
    await db.refresh(conn)
    return connection_to_dict(conn)


async def delete_connection(db: AsyncSession, connection_id: str) -> None:
    """
    LiteLLM-like: removing a credential/deployment disables routes that used it.
    Linked models are deactivated and unlinked (no silent fallback on stale api_base).
    """
    conn = await db.get(LLMConnection, connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    result = await db.execute(
        select(LLMModel).where(LLMModel.connection_id == conn.id)
    )
    for model in result.scalars().all():
        model.connection_id = None
        model.base_url = None
        model.is_active = False

    await db.delete(conn)
    await db.flush()


async def test_openai_compatible_endpoint(
    *,
    base_url: str,
    api_key: str | None = None,
    provider_type: str = "openai",
    timeout: float = 8.0,
) -> dict[str, Any]:
    provider_type = _normalize_provider_type(provider_type)
    base = _normalize_base_url(base_url, provider_type)
    from app.runtime.vllm_routing import upstream_auth_headers
    headers = upstream_auth_headers(api_key)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(f"{base}/models", headers=headers)
    except httpx.HTTPError as exc:
        return {
            "ok": False,
            "base_url": base,
            "error": str(exc),
            "model_ids": [],
        }

    model_ids: list[str] = []
    if resp.is_success:
        try:
            data = resp.json().get("data") or []
            model_ids = [m.get("id") for m in data if isinstance(m, dict) and m.get("id")]
        except Exception:
            model_ids = []

    return {
        "ok": resp.is_success,
        "base_url": base,
        "status_code": resp.status_code,
        "model_ids": model_ids[:20],
        "error": None if resp.is_success else (resp.text[:300] or f"HTTP {resp.status_code}"),
    }


async def test_connection(db: AsyncSession, connection_id: str) -> dict[str, Any]:
    conn = await db.get(LLMConnection, connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    key = decrypt_api_key(conn.api_key_encrypted)
    result = await test_openai_compatible_endpoint(
        base_url=conn.base_url,
        api_key=key,
        provider_type=conn.provider_type,
    )
    result["connection_id"] = conn.id
    return result


async def list_models(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(LLMModel)
        .options(selectinload(LLMModel.connection))
        .order_by(LLMModel.created_at.desc())
    )
    return [model_to_dict(m) for m in result.scalars().all()]


async def create_model(
    db: AsyncSession,
    *,
    id: str,
    model_path: str,
    connection_id: str | None = None,
    base_url: str | None = None,
    provider: str = "vllm",
    context_length: int = 8192,
    max_output_tokens: int = 2048,
    is_active: bool = True,
    fallback_model_ids: list[str] | None = None,
) -> dict:
    """
    LiteLLM model_list entry:
      model_name=id, litellm_params.model=model_path, api_base from connection.
    connection_id is required for new models.
    """
    mid = _require_slug(id)
    existing = await db.get(LLMModel, mid)
    if existing:
        raise HTTPException(status_code=409, detail="Model id already exists")

    path = (model_path or "").strip()
    if not path:
        raise HTTPException(status_code=400, detail="model_path is required")
    if not connection_id:
        raise HTTPException(
            status_code=400,
            detail="connection_id is required (LiteLLM-style: model binds to a provider/credential)",
        )

    conn = await db.get(LLMConnection, connection_id)
    if not conn:
        raise HTTPException(status_code=400, detail="connection_id not found")
    if not conn.is_active:
        raise HTTPException(status_code=400, detail="connection is inactive")

    # Optional per-model api_base override; default = connection api_base
    if base_url and base_url.strip():
        resolved_base = _normalize_base_url(base_url, conn.provider_type)
    else:
        resolved_base = conn.base_url

    fallbacks = await _validate_fallback_ids(db, self_id=mid, fallback_model_ids=fallback_model_ids)

    model = LLMModel(
        id=mid,
        model_path=path,
        base_url=resolved_base,
        connection_id=conn.id,
        provider=conn.provider_type,
        context_length=context_length,
        max_output_tokens=max_output_tokens,
        is_active=is_active,
        fallback_model_ids=fallbacks,
        metadata_={},
    )
    db.add(model)
    await db.flush()
    await db.refresh(model)
    model.connection = conn
    return model_to_dict(model)


async def update_model(
    db: AsyncSession,
    model_id: str,
    *,
    model_path: str | None = None,
    connection_id: str | None = None,
    clear_connection: bool = False,
    base_url: str | None = None,
    context_length: int | None = None,
    max_output_tokens: int | None = None,
    is_active: bool | None = None,
    fallback_model_ids: list[str] | None = None,
) -> dict:
    result = await db.execute(
        select(LLMModel)
        .where(LLMModel.id == model_id)
        .options(selectinload(LLMModel.connection))
    )
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    if model_path is not None:
        path = model_path.strip()
        if not path:
            raise HTTPException(status_code=400, detail="model_path cannot be empty")
        model.model_path = path

    if clear_connection:
        # Unbind = LiteLLM remove deployment binding → deactivate
        model.connection_id = None
        model.connection = None
        model.base_url = None
        model.is_active = False
    elif connection_id is not None:
        conn = await db.get(LLMConnection, connection_id)
        if not conn:
            raise HTTPException(status_code=400, detail="connection_id not found")
        if not conn.is_active:
            raise HTTPException(status_code=400, detail="connection is inactive")
        model.connection_id = conn.id
        model.connection = conn
        model.base_url = conn.base_url
        model.provider = conn.provider_type

    if base_url is not None and not clear_connection:
        provider = model.provider if model.provider in SUPPORTED_PROVIDER_TYPES else "openai"
        if base_url.strip():
            model.base_url = _normalize_base_url(base_url, provider)
        elif model.connection is not None:
            model.base_url = model.connection.base_url

    if context_length is not None:
        model.context_length = context_length
    if max_output_tokens is not None:
        model.max_output_tokens = max_output_tokens
    if is_active is not None:
        if is_active and not model.connection_id:
            raise HTTPException(
                status_code=400,
                detail="Cannot activate a model without an active connection binding",
            )
        model.is_active = is_active
    if fallback_model_ids is not None:
        model.fallback_model_ids = await _validate_fallback_ids(
            db, self_id=model.id, fallback_model_ids=fallback_model_ids
        )

    await db.flush()
    await db.refresh(model)
    return model_to_dict(model)


async def delete_model(db: AsyncSession, model_id: str) -> None:
    from sqlalchemy import func
    from app.models.llm import Conversation

    model = await db.get(LLMModel, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    conv_count = await db.scalar(
        select(func.count()).select_from(Conversation).where(Conversation.model_id == model_id)
    )
    if conv_count and int(conv_count) > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Model has {conv_count} conversation(s); deactivate it instead of deleting, "
                "or delete conversations first."
            ),
        )

    await db.delete(model)
    await db.flush()
