from __future__ import annotations

import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.llm import LLMModel, Conversation, Message


# ── Models ─────────────────────────────────────────────────────────────────────

async def list_models(db: AsyncSession) -> list[dict]:
    result = await db.execute(select(LLMModel).where(LLMModel.is_active == True))  # noqa: E712
    models = result.scalars().all()
    return [{"id": m.id, "object": "model", "owned_by": "local"} for m in models]


# ── Conversations ──────────────────────────────────────────────────────────────

async def list_conversations(
    db: AsyncSession,
    user_id: int | None = None,
) -> list[dict]:
    q = select(Conversation).order_by(Conversation.created_at.desc())
    if user_id:
        q = q.where(Conversation.user_id == user_id)

    result = await db.execute(q)
    convs = result.scalars().all()
    return [
        {"id": str(c.id), "title": c.title, "created_at": c.created_at}
        for c in convs
    ]


async def get_conversation_detail(conv_id: uuid.UUID, db: AsyncSession, user_id: int) -> dict:
    query = (
        select(Conversation)
        .where(Conversation.id == conv_id, Conversation.user_id == user_id)
        .options(selectinload(Conversation.messages))
    )
    result = await db.execute(query)
    conv = result.scalar_one_or_none()
    if conv is None:
        # 404 برای جلوگیری از افشای وجود مکالمه‌ی کاربران دیگر (جلوگیری از enumeration)
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    return {
        "id": str(conv.id),
        "title": conv.title,
        "messages": [
            {"role": m.role, "content": m.content, "created_at": m.created_at}
            for m in conv.messages
        ],
    }


# ── API Keys ───────────────────────────────────────────────────────────────────

async def create_api_key(user_id: int, name: str, db: AsyncSession) -> tuple:
    """Returns (APIKey ORM object, raw_key_string). raw_key shown only once."""
    from app.models.api_key import APIKey
    from app.core.security import generate_api_key, hash_api_key, mask_api_key, encrypt_api_key

    raw_key = generate_api_key()
    key_hash = hash_api_key(raw_key)

    api_key = APIKey(
        user_id=user_id,
        name=name,
        key_hash=key_hash,
        key_hint=mask_api_key(raw_key),
        key_encrypted=encrypt_api_key(raw_key),
    )
    db.add(api_key)
    await db.flush()
    return api_key, raw_key
