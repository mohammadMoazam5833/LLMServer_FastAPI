"""Resolve upstream OpenAI-compatible base URL for a gateway model (LiteLLM-like)."""
from __future__ import annotations

import hashlib
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.llm import LLMModel

settings = get_settings()


def resolve_vllm_base_url(model: LLMModel | None = None, base_url: str | None = None) -> str:
    """
    LiteLLM-aligned resolution:
      1) explicit override argument
      2) active connection.api_base (preferred when bound)
      3) model.base_url (per-model api_base / legacy row)
      4) settings.VLLM_BASE_URL only for unbound legacy models

    If the model is bound to an *inactive* connection, return "" so callers fail
    closed instead of silently using a stale URL.
    """
    chosen = (base_url or "").strip()
    if chosen:
        return chosen.rstrip("/")

    if model is None:
        return (settings.VLLM_BASE_URL or "").strip().rstrip("/")

    conn = getattr(model, "connection", None)
    connection_id = getattr(model, "connection_id", None)

    if connection_id:
        if conn is None:
            # relationship not loaded — do not invent a URL from denormalized cache alone
            # when we know a binding exists; prefer denormalized only if present, else env.
            # After LiteLLM delete semantics, deactivated models clear base_url.
            chosen = (getattr(model, "base_url", None) or "").strip()
            return chosen.rstrip("/")
        if not getattr(conn, "is_active", False):
            return ""
        chosen = (getattr(conn, "base_url", None) or "").strip()
        if chosen:
            return chosen.rstrip("/")
        # active connection without url should not happen
        return ""

    # Unbound (legacy) model: allow model.base_url then global default
    chosen = (getattr(model, "base_url", None) or "").strip()
    if not chosen:
        chosen = (settings.VLLM_BASE_URL or "").strip()
    return chosen.rstrip("/")


def resolve_upstream_api_key(model: LLMModel | None = None) -> str | None:
    """
    Upstream credential for OpenAI-compatible backends:
      1) active connection.api_key (decrypted)
      2) settings.VLLM_API_KEY (cluster-wide default)
    """
    if model is not None:
        conn = getattr(model, "connection", None)
        if conn is not None and getattr(conn, "is_active", False):
            enc = getattr(conn, "api_key_encrypted", None)
            if enc:
                from app.core.security import decrypt_api_key
                key = decrypt_api_key(enc)
                if key and key.strip():
                    return key.strip()

    env_key = (settings.VLLM_API_KEY or "").strip()
    return env_key or None


def upstream_auth_headers(api_key: str | None) -> dict[str, str]:
    """
    Headers accepted by vLLM / OpenAI-compatible servers that require auth.
    Sends both Bearer and X-API-Key (vLLM accepts either).
    """
    key = (api_key or "").strip()
    if not key:
        return {}
    return {
        "Authorization": f"Bearer {key}",
        "X-API-Key": key,
    }


def upstream_api_key_fingerprint(api_key: str | None) -> str:
    """Stable non-secret token for generator cache keys."""
    key = (api_key or "").strip()
    if not key:
        return "nokey"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


async def load_active_model(
    db: AsyncSession,
    model_ref: str,
) -> LLMModel | None:
    """Look up by public id first, then by served model_path."""
    if not model_ref:
        return None
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(LLMModel)
        .where(
            LLMModel.is_active == True,  # noqa: E712
            or_(LLMModel.id == model_ref, LLMModel.model_path == model_ref),
        )
        .options(selectinload(LLMModel.connection))
    )
    model = result.scalars().first()
    if model is None:
        return None

    # Bound models require an active connection (LiteLLM credential must exist)
    if model.connection_id:
        conn = model.connection
        if conn is None or not conn.is_active:
            return None
    return model
