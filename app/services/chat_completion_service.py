"""
chat_completion_service.py — async replacement for Django version.

prepare() is now async because all DB operations are async.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import AsyncIterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.llm import LLMModel, Conversation
from app.models.user import User
from app.runtime.provider_manager import ProviderManager
from app.services.chat_service import ChatService
from app.services.openwebui_tasks import is_openwebui_internal_request
from app.schemas.schemas import ChatCompletionRequest


def _get_last_user(messages) -> str | None:
    for m in reversed(messages):
        role = m.role if hasattr(m, "role") else m["role"]
        if role == "user":
            return m.content if hasattr(m, "content") else m["content"]
    return None


def _get_system(messages) -> str:
    for m in messages:
        role = m.role if hasattr(m, "role") else m["role"]
        if role == "system":
            return m.content if hasattr(m, "content") else m["content"]
    return ""


def _to_openai_messages(messages) -> list[dict]:
    return [
        {
            "role": m.role if hasattr(m, "role") else m["role"],
            "content": m.content if hasattr(m, "content") else m["content"],
        }
        for m in messages
    ]


async def _load_model(data: ChatCompletionRequest, db: AsyncSession) -> LLMModel:
    result = await db.execute(
        select(LLMModel).where(LLMModel.id == data.model, LLMModel.is_active == True)  # noqa: E712
    )
    model = result.scalar_one_or_none()
    if model is None:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Model '{data.model}' not found")
    return model


async def _create_internal_task_completion(
    data: ChatCompletionRequest,
    db: AsyncSession,
) -> dict:
    model = await _load_model(data, db)
    generator = ProviderManager.get_provider(model)
    response = await generator.generate(
        _to_openai_messages(data.messages),
        max_tokens=int(data.max_tokens),
        temperature=float(data.temperature),
    )
    content = response.get("text", "")
    return {
        "id": f"chatcmpl-{uuid.uuid4()}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model.id,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
        "conversation_id": str(data.conversation_id) if data.conversation_id else None,
        "usage": response.get("usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}),
    }


async def _create_internal_task_completion_stream(
    data: ChatCompletionRequest,
    db: AsyncSession,
) -> AsyncIterator[str]:
    model = await _load_model(data, db)
    generator = ProviderManager.get_provider(model)
    cmpl_id = f"chatcmpl-{uuid.uuid4()}"
    created = int(time.time())

    async for token in generator.generate_stream(
        _to_openai_messages(data.messages),
        max_tokens=int(data.max_tokens),
        temperature=float(data.temperature),
    ):
        chunk = {
            "id": cmpl_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model.id,
            "choices": [{"index": 0, "delta": {"content": token}, "finish_reason": None}],
        }
        yield f"data: {json.dumps(chunk)}\n\n"

    yield "data: [DONE]\n\n"


async def _prepare(
    data: ChatCompletionRequest,
    user: User,
    db: AsyncSession,
) -> tuple[ChatService, Conversation, str, str]:
    """
    Resolve model + conversation, build ChatService.
    Returns (service, conversation, model_id, last_user_message)
    """
    # ── Load model ─────────────────────────────────────────────────────────────
    model = await _load_model(data, db)

    # ── Resolve conversation ───────────────────────────────────────────────────
    conv_id = data.conversation_id
    if conv_id:
        result = await db.execute(
            select(Conversation).where(
                Conversation.id == conv_id,
                Conversation.user_id == user.id,
            )
        )
        conv = result.scalar_one_or_none()
        if conv is None:
            # Create new with provided id
            conv = Conversation(
                id=conv_id,
                user_id=user.id,
                model_id=model.id,
                system_prompt=_get_system(data.messages) or "You are a helpful coding assistant.",
            )
            db.add(conv)
            await db.flush()
    else:
        # Find latest conversation for this user+model
        result = await db.execute(
            select(Conversation)
            .where(Conversation.user_id == user.id, Conversation.model_id == model.id)
            .order_by(Conversation.created_at.desc())
            .limit(1)
        )
        conv = result.scalar_one_or_none()
        if conv is None:
            conv = Conversation(
                user_id=user.id,
                model_id=model.id,
                system_prompt=_get_system(data.messages) or "You are a helpful coding assistant.",
            )
            db.add(conv)
            await db.flush()

    generator = ProviderManager.get_provider(model)
    service = ChatService(
        generator=generator,
        model_id=model.id,
        conversation=conv,
        user_id=user.id,
        db=db,
        model_path=model.model_path,
        context_length=model.context_length,
        max_output_tokens=model.max_output_tokens,
    )
    return service, conv, model.id, _get_last_user(data.messages)


# ── Non-streaming ──────────────────────────────────────────────────────────────

async def create_chat_completion(
    data: ChatCompletionRequest,
    user: User,
    db: AsyncSession,
) -> dict:
    if is_openwebui_internal_request(data.messages):
        return await _create_internal_task_completion(data, db)

    service, conv, model_id, msg = await _prepare(data, user, db)
    max_tokens = int(data.max_tokens)
    res = await service.chat(msg, max_tokens)
    return {
        "id": f"chatcmpl-{uuid.uuid4()}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_id,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": res["text"]}}],
        "conversation_id": str(conv.id),
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


# ── Streaming ──────────────────────────────────────────────────────────────────

async def create_chat_completion_stream(
    data: ChatCompletionRequest,
    user: User,
    db: AsyncSession,
) -> AsyncIterator[str]:
    if is_openwebui_internal_request(data.messages):
        async for chunk in _create_internal_task_completion_stream(data, db):
            yield chunk
        return

    service, conv, model_id, msg = await _prepare(data, user, db)
    max_tokens = int(data.max_tokens)
    cmpl_id = f"chatcmpl-{uuid.uuid4()}"
    created = int(time.time())

    async for token in service.stream(msg, max_tokens):
        chunk = {
            "id": cmpl_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model_id,
            "choices": [{"index": 0, "delta": {"content": token}, "finish_reason": None}],
        }
        yield f"data: {json.dumps(chunk)}\n\n"

    yield "data: [DONE]\n\n"
