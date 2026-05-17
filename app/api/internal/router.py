"""
Internal API endpoints.
Auth: JWT Bearer token.
Mounted at: /api/v1/
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.schemas import (
    ChatCompletionRequest,
    ModelListResponse,
    ConversationSummary,
    ConversationDetail,
    APIKeyCreate,
    APIKeyResponse,
    APIKeyCreatedResponse,
)
from app.services.chat_completion_service import create_chat_completion
from app.services.model_service import (
    list_models,
    list_conversations,
    get_conversation_detail,
    create_api_key,
)

router = APIRouter(tags=["Internal"])


# ── Chat ───────────────────────────────────────────────────────────────────────

@router.post("/chat/completions")
async def internal_chat_completions(
    body: ChatCompletionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await create_chat_completion(body, user, db)


# ── Models ─────────────────────────────────────────────────────────────────────

@router.get("/models", response_model=ModelListResponse)
async def internal_list_models(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await list_models(db)
    return ModelListResponse(data=data)


# ── Conversations ──────────────────────────────────────────────────────────────

@router.get("/chats")
async def list_chats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await list_conversations(db, user_id=user.id)
    return {"object": "list", "data": data}


@router.get("/chats/{chat_id}")
async def chat_detail(
    chat_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_conversation_detail(chat_id, db)


# ── API Keys ───────────────────────────────────────────────────────────────────

@router.post("/api-keys", response_model=APIKeyCreatedResponse, status_code=201)
async def create_key(
    body: APIKeyCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    api_key, raw_key = await create_api_key(user.id, body.name, db)
    return APIKeyCreatedResponse(
        id=api_key.id,
        name=api_key.name,
        is_active=api_key.is_active,
        created_at=api_key.created_at,
        raw_key=raw_key,
    )
