"""
OpenAI-compatible public endpoints.
Auth: X-API-Key header (or Bearer <key>).
Mounted at: /v1/
"""
from __future__ import annotations

import json
import os

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_api_key
from app.database import get_db
from app.models.user import User
from app.schemas.schemas import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ModelListResponse,
)
from app.services.chat_completion_service import (
    create_openai_chat_completion,
    create_openai_chat_completion_stream,
)
from app.services.model_service import list_models
from app.config import get_settings

settings = get_settings()
router = APIRouter(tags=["OpenAI Compatible"])


@router.get("/models", response_model=ModelListResponse)
async def openai_list_models(
    user: User = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
):
    data = await list_models(db)
    return ModelListResponse(data=data)


@router.post("/chat/completions")
async def openai_chat_completions(
    body: ChatCompletionRequest,
    request: Request,
    user: User = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
):
    if body.stream:
        return StreamingResponse(
            create_openai_chat_completion_stream(body, user, db),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",   # disable nginx buffering for SSE
            },
        )

    result = await create_openai_chat_completion(body, user, db)

    # ثبت مصرف توکن برای سهمیه‌ی ماهانه (در صورت وجود usage)
    api_key_id = getattr(request.state, "api_key_id", None)
    total_tokens = (result.get("usage") or {}).get("total_tokens", 0)
    if api_key_id and total_tokens:
        from app.core.rate_limit import record_tokens
        await record_tokens(api_key_id, total_tokens)

    return result


@router.get("/openapi.json", include_in_schema=False)
async def openai_spec():
    """Serve the handcrafted OpenAPI spec."""
    from app.config import get_settings
    spec_path = os.path.join(os.path.dirname(__file__), "..", "..", "openapi.json")
    try:
        with open(os.path.abspath(spec_path)) as f:
            return JSONResponse(json.load(f))
    except FileNotFoundError:
        return JSONResponse({"error": "spec not found"}, status_code=404)
