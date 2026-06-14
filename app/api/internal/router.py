"""
Internal API endpoints.
Auth: JWT Bearer token.
Mounted at: /api/v1/
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.llm import RAGChunk
from app.models.user import User
from app.schemas.schemas import (
    ChatCompletionRequest,
    ModelListResponse,
    ConversationSummary,
    ConversationDetail,
    APIKeyCreate,
    APIKeyResponse,
    APIKeyCreatedResponse,
    RAGFileResponse,
)
from app.services.chat_completion_service import (
    create_chat_completion,
    create_chat_completion_stream,
)
from app.services.model_service import (
    list_models,
    list_conversations,
    get_conversation_detail,
    create_api_key,
)
from app.services.rag_service import create_rag_file, list_rag_files, get_rag_file_for_user, reindex_rag_file

router = APIRouter(tags=["Internal"])


# ── Chat ───────────────────────────────────────────────────────────────────────

@router.post("/chat/completions")
async def internal_chat_completions(
    body: ChatCompletionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.stream:
        return StreamingResponse(
            create_chat_completion_stream(body, user, db),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )
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
    return await get_conversation_detail(chat_id, db, user_id=user.id)


# ── RAG Files ─────────────────────────────────────────────────────────────────

@router.post("/files", response_model=RAGFileResponse, status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    process: bool = Query(default=True),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rag_file = await create_rag_file(db, user.id, file, process=process)
    chunk_count = await db.scalar(select(func.count(RAGChunk.id)).where(RAGChunk.file_id == rag_file.id))
    return RAGFileResponse(
        id=rag_file.id,
        filename=rag_file.filename,
        content_type=rag_file.content_type,
        status=rag_file.status,
        created_at=rag_file.created_at,
        chunk_count=chunk_count or 0,
    )


@router.get("/files")
async def files(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return {"object": "list", "data": await list_rag_files(db, user.id)}


@router.post("/files/{file_id}/reindex", response_model=RAGFileResponse)
async def reindex_file(
    file_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rag_file = await get_rag_file_for_user(db, user.id, file_id)
    if rag_file is None:
        raise HTTPException(status_code=404, detail="File not found")
    rag_file = await reindex_rag_file(db, rag_file)
    chunk_count = await db.scalar(select(func.count(RAGChunk.id)).where(RAGChunk.file_id == rag_file.id))
    return RAGFileResponse(
        id=rag_file.id,
        filename=rag_file.filename,
        content_type=rag_file.content_type,
        status=rag_file.status,
        created_at=rag_file.created_at,
        chunk_count=chunk_count or 0,
    )


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
