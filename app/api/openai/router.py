"""
OpenAI-compatible public endpoints.
Auth: X-API-Key header (or Bearer <key>).
Mounted at: /v1/
"""
from __future__ import annotations

import json
import os
from typing import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_api_key
from app.database import get_db
from app.models.user import User
from app.schemas.schemas import (
    ChatCompletionRequest,
    ModelListResponse,
    ChatFileReference,
)
from app.services.chat_completion_service import (
    create_openai_chat_completion,
    create_openai_chat_completion_stream,
)
from app.services.model_service import list_models
from app.services.rag_service import list_rag_files
from app.services.openwebui_files import (
    enrich_request_from_openwebui,
    log_incoming_payload_summary,
    sanitize_raw_for_validation,
    resolve_owui_chat_id,
)
from app.services.token_utils import estimate_message_tokens, estimate_text_tokens
import logging
from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)
router = APIRouter(tags=["OpenAI Compatible"])


async def _record_stream_tokens(
    stream: AsyncIterator[str],
    api_key_id: str | None,
    messages: list,
) -> AsyncIterator[str]:
    """Pass through SSE chunks and record token usage when the stream ends."""
    total_tokens = 0
    completion_parts: list[str] = []

    async for chunk in stream:
        if chunk.startswith("data: ") and "[DONE]" not in chunk:
            try:
                payload = json.loads(chunk[6:].strip())
                usage = payload.get("usage") or {}
                if usage.get("total_tokens"):
                    total_tokens = int(usage["total_tokens"])
                delta = (payload.get("choices") or [{}])[0].get("delta") or {}
                content = delta.get("content")
                if content:
                    completion_parts.append(content)
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        yield chunk

    if api_key_id:
        if not total_tokens:
            prompt_tokens = sum(estimate_message_tokens(m) for m in messages)
            completion_tokens = estimate_text_tokens("".join(completion_parts))
            total_tokens = prompt_tokens + completion_tokens
        if total_tokens > 0:
            from app.core.rate_limit import record_tokens
            await record_tokens(api_key_id, total_tokens)


@router.get("/models", response_model=ModelListResponse)
async def openai_list_models(
    user: User = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
):
    data = await list_models(db)
    return ModelListResponse(data=data)


@router.post("/chat/completions")
async def openai_chat_completions(
    request: Request,
    user: User = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
):
    raw = await request.json()
    body = ChatCompletionRequest.model_validate(sanitize_raw_for_validation(raw))
    chat_id = resolve_owui_chat_id(dict(request.headers), body)
    log_incoming_payload_summary(raw, chat_id=chat_id)
    body = await enrich_request_from_openwebui(raw, body, chat_id=chat_id)

    # Auto-attach fallback: RAG files uploaded directly to this gateway
    try:
        if settings.ALLOW_AUTO_ATTACH_RECENT_UPLOADS and not body.files:
            candidates = await list_rag_files(db, user.id)
            from datetime import datetime, timezone

            now = datetime.now(timezone.utc)
            window = getattr(settings, "AUTO_ATTACH_TIME_WINDOW_SECONDS", 300)
            recent = [
                c for c in candidates
                if c.get("status") in ("ready", "uploaded")
                and isinstance(c.get("created_at"), datetime)
                and (now - c["created_at"]).total_seconds() <= window
            ]
            if recent:
                recent_sorted = sorted(recent, key=lambda r: r["created_at"], reverse=True)
                chosen = recent_sorted[0]
                logger.info(
                    "Auto-attaching recent RAG upload %s for user %s",
                    chosen.get("id"), user.id,
                )
                body = body.model_copy(
                    update={"files": [ChatFileReference(id=str(chosen.get("id")))]}
                )
    except Exception:
        logger.exception("Failed while attempting auto-attach recent upload")

    if body.stream:
        api_key_id = getattr(request.state, "api_key_id", None)
        openai_messages = [
            {"role": m.role, "content": m.content if isinstance(m.content, str) else str(m.content)}
            for m in body.messages
        ]
        return StreamingResponse(
            _record_stream_tokens(
                create_openai_chat_completion_stream(body, user, db),
                api_key_id,
                openai_messages,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    result = await create_openai_chat_completion(body, user, db)

    api_key_id = getattr(request.state, "api_key_id", None)
    total_tokens = (result.get("usage") or {}).get("total_tokens", 0)
    if api_key_id and total_tokens:
        from app.core.rate_limit import record_tokens
        await record_tokens(api_key_id, total_tokens)

    return result


@router.get("/openapi.json", include_in_schema=False)
async def openai_spec():
    """Serve the handcrafted OpenAPI spec."""
    spec_path = os.path.join(os.path.dirname(__file__), "..", "..", "openapi.json")
    try:
        with open(os.path.abspath(spec_path)) as f:
            return JSONResponse(json.load(f))
    except FileNotFoundError:
        return JSONResponse({"error": "spec not found"}, status_code=404)
