"""Resolve which vLLM OpenAI base URL a gateway model should use."""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.llm import LLMModel

settings = get_settings()


def resolve_vllm_base_url(model: LLMModel | None = None, base_url: str | None = None) -> str:
    """
    Prefer explicit base_url / model.base_url; otherwise settings.VLLM_BASE_URL.
    Always returns without trailing slash issues handled by callers via rstrip.
    """
    chosen = (base_url or "").strip()
    if not chosen and model is not None:
        chosen = (getattr(model, "base_url", None) or "").strip()
    if not chosen:
        chosen = (settings.VLLM_BASE_URL or "").strip()
    return chosen.rstrip("/")


async def load_active_model(
    db: AsyncSession,
    model_ref: str,
) -> LLMModel | None:
    """Look up by public id first, then by served model_path."""
    if not model_ref:
        return None
    result = await db.execute(
        select(LLMModel).where(
            LLMModel.is_active == True,  # noqa: E712
            or_(LLMModel.id == model_ref, LLMModel.model_path == model_ref),
        )
    )
    return result.scalars().first()
