"""
OpenAI-compatible public endpoints.
Auth: X-API-Key header (or Bearer <key>).
Mounted at: /v1/
"""
from __future__ import annotations

import json
import os
import time
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
from app.core.request_metrics import record_model_request
import logging
from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)
router = APIRouter(tags=["OpenAI Compatible"])


def _usage_parts(usage: dict | None) -> tuple[int, int, int]:
    usage = usage or {}
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    total = int(usage.get("total_tokens") or 0)
    if not total and (prompt or completion):
        total = prompt + completion
    return prompt, completion, total


async def _record_stream_tokens(
    stream: AsyncIterator[str],
    api_key_id: str | None,
    messages: list,
    *,
    model_id: str,
    started: float,
) -> AsyncIterator[str]:
    """Pass through SSE chunks and record token usage + latency when the stream ends."""
    total_tokens = 0
    prompt_tokens = 0
    completion_tokens = 0
    completion_parts: list[str] = []
    ok = True

    try:
        async for chunk in stream:
            if chunk.startswith("data: ") and "[DONE]" not in chunk:
                try:
                    payload = json.loads(chunk[6:].strip())
                    usage = payload.get("usage") or {}
                    if usage:
                        p, c, t = _usage_parts(usage)
                        if t:
                            total_tokens = t
                        if p:
                            prompt_tokens = p
                        if c:
                            completion_tokens = c
                    delta = (payload.get("choices") or [{}])[0].get("delta") or {}
                    content = delta.get("content")
                    if content:
                        completion_parts.append(content)
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass
            yield chunk
    except Exception:
        ok = False
        raise
    finally:
        latency_ms = (time.perf_counter() - started) * 1000.0
        if not total_tokens:
            prompt_tokens = sum(estimate_message_tokens(m) for m in messages)
            completion_tokens = estimate_text_tokens("".join(completion_parts))
            total_tokens = prompt_tokens + completion_tokens
        await record_model_request(
            model_id=model_id,
            latency_ms=latency_ms,
            ok=ok,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )
        if api_key_id and total_tokens > 0 and ok:
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

    model_id = body.model
    api_key_id = getattr(request.state, "api_key_id", None)

    if body.stream:
        openai_messages = [
            {"role": m.role, "content": m.content if isinstance(m.content, str) else str(m.content)}
            for m in body.messages
        ]
        started = time.perf_counter()
        return StreamingResponse(
            _record_stream_tokens(
                create_openai_chat_completion_stream(body, user, db),
                api_key_id,
                openai_messages,
                model_id=model_id,
                started=started,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    started = time.perf_counter()
    ok = True
    try:
        result = await create_openai_chat_completion(body, user, db)
    except Exception:
        ok = False
        latency_ms = (time.perf_counter() - started) * 1000.0
        await record_model_request(model_id=model_id, latency_ms=latency_ms, ok=False)
        raise

    latency_ms = (time.perf_counter() - started) * 1000.0
    prompt_tokens, completion_tokens, total_tokens = _usage_parts(result.get("usage"))
    await record_model_request(
        model_id=model_id,
        latency_ms=latency_ms,
        ok=ok,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    )

    if api_key_id and total_tokens:
        from app.core.rate_limit import record_tokens
        await record_tokens(api_key_id, total_tokens)

    return result


@router.get("/openapi.json", include_in_schema=False)
async def openai_spec():
    """Serve the handcrafted OpenAI spec."""
    spec_path = os.path.join(os.path.dirname(__file__), "..", "..", "openapi.json")
    try:
        with open(os.path.abspath(spec_path)) as f:
            return JSONResponse(json.load(f))
    except FileNotFoundError:
        return JSONResponse({"error": "spec not found"}, status_code=404)
