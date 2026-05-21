"""
chat_completion_service.py — async replacement for Django version.

prepare() is now async because all DB operations are async.
"""
from __future__ import annotations

import json
import logging
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
from app.services.rag_service import retrieve_context
from app.services.token_utils import estimate_message_tokens, estimate_text_tokens
from app.schemas.schemas import ChatCompletionRequest

logger = logging.getLogger(__name__)


def _flatten_content(message) -> str:
    raw = message.content if hasattr(message, "content") else message.get("content", "")
    images = message.images if hasattr(message, "images") else message.get("images", [])

    if images:
        from app.services.rag_service import ocr_base64_image
        texts = []
        if isinstance(raw, str) and raw:
            texts.append(raw)
        for i, img_url in enumerate(images):
            if img_url.startswith("data:image"):
                ocr_text = ocr_base64_image(img_url)
                if ocr_text:
                    texts.append(f"[OCR: {ocr_text}]")
        return "\n".join(texts)

    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        from app.services.rag_service import ocr_base64_image
        texts = []
        for part in raw:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text":
                texts.append(part.get("text", ""))
            elif part.get("type") == "image_url":
                url = part.get("image_url", {}).get("url", "")
                if url.startswith("data:image"):
                    ocr_text = ocr_base64_image(url)
                    if ocr_text:
                        texts.append(f"[OCR: {ocr_text}]")
        return "\n".join(texts)
    return str(raw)


def _get_last_user(messages) -> str | None:
    for m in reversed(messages):
        role = m.role if hasattr(m, "role") else m["role"]
        if role == "user":
            return _flatten_content(m)
    return None


def _get_system(messages) -> str:
    for m in messages:
        role = m.role if hasattr(m, "role") else m["role"]
        if role == "system":
            return _flatten_content(m)
    return ""


def _to_openai_messages(messages) -> list[dict]:
    return [
        {
            "role": m.role if hasattr(m, "role") else m["role"],
            "content": _flatten_content(m),
        }
        for m in messages
    ]


def _with_rag_context(messages: list[dict], context: str) -> list[dict]:
    if not context:
        return messages

    system_message = {
        "role": "system",
        "content": (
            "Use the following retrieved document context when it is relevant. "
            "If the context does not answer the user, say so and answer from general knowledge.\n\n"
            f"{context}"
        ),
    }
    if messages and messages[0]["role"] == "system":
        merged = messages.copy()
        merged[0] = {
            "role": "system",
            "content": f"{messages[0]['content']}\n\n{system_message['content']}",
        }
        return merged
    return [system_message, *messages]


def _estimate_tokens(text: str) -> int:
    return estimate_text_tokens(text)


def _message_token_count(message: dict) -> int:
    return estimate_message_tokens(message)


def _trim_messages_to_budget(messages: list[dict], max_prompt_tokens: int) -> list[dict]:
    if not messages:
        return messages

    system_messages = [message for message in messages if message["role"] == "system"]
    chat_messages = [message for message in messages if message["role"] != "system"]

    system_tokens = sum(_message_token_count(message) for message in system_messages)
    chat_budget = max(256, max_prompt_tokens - system_tokens)

    kept_reversed: list[dict] = []
    used = 0
    for message in reversed(chat_messages):
        message_tokens = _message_token_count(message)
        if kept_reversed and used + message_tokens > chat_budget:
            break
        kept_reversed.append(message)
        used += message_tokens

    kept_chat = list(reversed(kept_reversed))
    dropped = len(chat_messages) - len(kept_chat)
    if dropped:
        logger.info(
            "Trimmed %d OpenAI-compatible history messages to fit prompt budget",
            dropped,
        )

    return [*system_messages, *kept_chat]


def _resolve_max_tokens(data_max_tokens: int, model_max_output: int | None) -> int:
    cap = model_max_output or 4096
    requested = int(data_max_tokens)
    resolved = min(requested, cap)
    logger.info("🔢 max_tokens: request=%d | model_cap=%d | resolved=%d", requested, cap, resolved)
    return resolved


def _prepare_provider_messages(
    data: ChatCompletionRequest,
    model: LLMModel,
    rag_context: str,
) -> list[dict]:
    messages = _with_rag_context(_to_openai_messages(data.messages), rag_context)
    max_output_tokens = _resolve_max_tokens(data.max_tokens, model.max_output_tokens)
    context_length = model.context_length or 8192
    safety_margin = 64
    prompt_budget = max(512, context_length - max_output_tokens - safety_margin)

    messages = _trim_messages_to_budget(messages, prompt_budget)
    prompt_tokens = sum(_message_token_count(message) for message in messages)
    max_output_tokens = min(max_output_tokens, max(1, context_length - prompt_tokens - safety_margin))

    rag_len = len(rag_context) if rag_context else 0
    logger.info(
        "📝 prepare_provider_messages | model_ctx=%d | max_output=%d | prompt_budget=%d | prompt_tokens=%d | rag_context_chars=%d | total_msgs=%d",
        context_length, max_output_tokens, prompt_budget, prompt_tokens, rag_len, len(messages)
    )

    return messages


def _file_ids(data: ChatCompletionRequest) -> list[uuid.UUID]:
    ids: list[uuid.UUID] = []
    for file in data.files:
        try:
            ids.append(uuid.UUID(str(file.id)))
        except ValueError:
            continue
    return ids


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
    max_tokens = _resolve_max_tokens(data.max_tokens, model.max_output_tokens)
    messages = _trim_messages_to_budget(
        _to_openai_messages(data.messages),
        max(512, (model.context_length or 8192) - max_tokens - 512),
    )
    response = await generator.generate(
        messages,
        max_tokens=max_tokens,
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
    max_tokens = _resolve_max_tokens(data.max_tokens, model.max_output_tokens)
    cmpl_id = f"chatcmpl-{uuid.uuid4()}"
    created = int(time.time())

    async for token in generator.generate_stream(
        _trim_messages_to_budget(
            _to_openai_messages(data.messages),
            max(512, (model.context_length or 8192) - max_tokens - 512),
        ),
        max_tokens=max_tokens,
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
    system_prompt = _get_system(data.messages) or "You are a helpful coding assistant."
    rag_context = await retrieve_context(db, user.id, _file_ids(data), _get_last_user(data.messages) or "")
    if rag_context:
        system_prompt = (
            f"{system_prompt}\n\n"
            "Use the following retrieved document context when it is relevant. "
            "If the context does not answer the user, say so and answer from general knowledge.\n\n"
            f"{rag_context}"
        )

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
                system_prompt=system_prompt,
            )
            db.add(conv)
            await db.flush()
    else:
        conv = Conversation(
            user_id=user.id,
            model_id=model.id,
            system_prompt=system_prompt,
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
        system_prompt=system_prompt,
        model_path=model.model_path,
        context_length=model.context_length,
        max_output_tokens=model.max_output_tokens,
    )
    return service, conv, model.id, _get_last_user(data.messages)


async def create_openai_chat_completion(
    data: ChatCompletionRequest,
    user: User,
    db: AsyncSession,
) -> dict:
    if is_openwebui_internal_request(data.messages):
        return await _create_internal_task_completion(data, db)

    logger.info(
        "🎯 create_openai_chat_completion | model_id=%s | request_max_tokens=%d | stream=%s",
        data.model, data.max_tokens, data.stream
    )

    model = await _load_model(data, db)
    generator = ProviderManager.get_provider(model)
    rag_context = await retrieve_context(db, user.id, _file_ids(data), _get_last_user(data.messages) or "")
    messages = _prepare_provider_messages(data, model, rag_context)
    max_tokens = _resolve_max_tokens(data.max_tokens, model.max_output_tokens)

    response = await generator.generate(
        messages,
        max_tokens=max_tokens,
        temperature=float(data.temperature),
    )
    content = response.get("text", "")
    logger.info("📥 response content length: %d chars", len(content))
    return {
        "id": f"chatcmpl-{uuid.uuid4()}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model.id,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
        "conversation_id": str(data.conversation_id) if data.conversation_id else None,
        "usage": response.get("usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}),
    }


async def create_openai_chat_completion_stream(
    data: ChatCompletionRequest,
    user: User,
    db: AsyncSession,
) -> AsyncIterator[str]:
    if is_openwebui_internal_request(data.messages):
        async for chunk in _create_internal_task_completion_stream(data, db):
            yield chunk
        return

    logger.info(
        "📡 create_openai_chat_completion_stream | model_id=%s | request_max_tokens=%d",
        data.model, data.max_tokens
    )

    model = await _load_model(data, db)
    generator = ProviderManager.get_provider(model)
    rag_context = await retrieve_context(db, user.id, _file_ids(data), _get_last_user(data.messages) or "")
    messages = _prepare_provider_messages(data, model, rag_context)
    max_tokens = _resolve_max_tokens(data.max_tokens, model.max_output_tokens)

    cmpl_id = f"chatcmpl-{uuid.uuid4()}"
    created = int(time.time())

    async for token in generator.generate_stream(
        messages,
        max_tokens=max_tokens,
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


# ── Non-streaming ──────────────────────────────────────────────────────────────

async def create_chat_completion(
    data: ChatCompletionRequest,
    user: User,
    db: AsyncSession,
) -> dict:
    if is_openwebui_internal_request(data.messages):
        return await _create_internal_task_completion(data, db)

    service, conv, model_id, msg = await _prepare(data, user, db)
    max_output_cap = service._kwargs.get("max_output_tokens") or 4096
    max_tokens = _resolve_max_tokens(data.max_tokens, max_output_cap)
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
    max_output_cap = service._kwargs.get("max_output_tokens") or 4096
    max_tokens = _resolve_max_tokens(data.max_tokens, max_output_cap)
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
