"""
Direct vLLM access endpoints for Cline integration.
Auth: X-API-Key header (or Bearer <key>).
Mounted at: /code_bot/v1/

Acts as a lightweight reverse proxy to vLLM — no RAG, no context
processing, no conversation tracking.  Just auth + passthrough.
"""
from __future__ import annotations

import json
import logging
from typing import AsyncIterator

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_api_key
from app.database import get_db
from app.models.user import User
from app.config import get_settings
from app.services.token_utils import estimate_message_tokens, estimate_text_tokens

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(tags=["Code Bot Direct"])

VLLM_BASE = settings.VLLM_BASE_URL.rstrip("/")


async def _forward_headers(request: Request) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
    }
    for key in ("Authorization", "X-API-Key", "Cookie"):
        val = request.headers.get(key)
        if val:
            headers[key] = val
    return headers


def _extract_usage_from_payload(payload: dict) -> int:
    usage = payload.get("usage") or {}
    total = usage.get("total_tokens")
    if total:
        return int(total)
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    return prompt + completion


async def _stream_from_vllm(
    body: dict,
    headers: dict,
    api_key_id: str | None = None,
) -> AsyncIterator[bytes]:
    """Async generator that streams bytes from vLLM while keeping client alive."""
    total_tokens = 0
    completion_parts: list[str] = []

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(settings.VLLM_REQUEST_TIMEOUT, connect=10.0),
    ) as client:
        async with client.stream(
            "POST",
            f"{VLLM_BASE}/chat/completions",
            json=body,
            headers=headers,
        ) as resp:
            if resp.status_code != 200:
                error_body = await resp.aread()
                yield json.dumps({"error": error_body.decode()}).encode()
                return
            async for chunk in resp.aiter_bytes():
                yield chunk
                if not api_key_id:
                    continue
                try:
                    text = chunk.decode("utf-8", errors="ignore")
                    for line in text.splitlines():
                        if not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if not data_str or data_str == "[DONE]":
                            continue
                        payload = json.loads(data_str)
                        usage_tokens = _extract_usage_from_payload(payload)
                        if usage_tokens:
                            total_tokens = usage_tokens
                        delta = (payload.get("choices") or [{}])[0].get("delta") or {}
                        content = delta.get("content")
                        if content:
                            completion_parts.append(content)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass

    if api_key_id:
        if not total_tokens:
            messages = body.get("messages") or []
            prompt_tokens = sum(estimate_message_tokens(m) for m in messages)
            completion_tokens = estimate_text_tokens("".join(completion_parts))
            total_tokens = prompt_tokens + completion_tokens
        if total_tokens > 0:
            from app.core.rate_limit import record_tokens
            await record_tokens(api_key_id, total_tokens)


@router.get("/models")
async def list_models(
    request: Request,
    user: User = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Proxy GET /v1/models to vLLM."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{VLLM_BASE}/models",
                headers=await _forward_headers(request),
            )
            resp.raise_for_status()
            return JSONResponse(content=resp.json())
    except httpx.HTTPStatusError as e:
        return JSONResponse(
            status_code=e.response.status_code,
            content={"error": f"vLLM error: {e.response.text}"},
        )
    except Exception as e:
        logger.exception("Failed to proxy models request to vLLM")
        return JSONResponse(
            status_code=502,
            content={"error": f"Failed to reach vLLM: {str(e)}"},
        )


@router.post("/chat/completions")
async def chat_completions(
    request: Request,
    user: User = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Direct passthrough to vLLM /v1/chat/completions.

    No RAG, no flattening, no conversation tracking — pure vLLM.
    Supports both streaming and non-streaming responses.
    """
    try:
        body = await request.json()
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"error": f"Invalid JSON body: {str(e)}"},
        )

    is_stream = body.get("stream", False)
    headers = await _forward_headers(request)
    api_key_id = getattr(request.state, "api_key_id", None)

    if is_stream:
        return StreamingResponse(
            _stream_from_vllm(body, headers, api_key_id=api_key_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.VLLM_REQUEST_TIMEOUT, connect=10.0),
        ) as client:
            resp = await client.post(
                f"{VLLM_BASE}/chat/completions",
                json=body,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        return JSONResponse(
            status_code=e.response.status_code,
            content={"error": f"vLLM error: {e.response.text}"},
        )
    except Exception as e:
        logger.exception("Failed to proxy chat/completions request to vLLM")
        return JSONResponse(
            status_code=502,
            content={"error": f"vLLM proxy error: {str(e)}"},
        )

    if api_key_id:
        total_tokens = _extract_usage_from_payload(data)
        if total_tokens > 0:
            from app.core.rate_limit import record_tokens
            await record_tokens(api_key_id, total_tokens)

    return JSONResponse(content=data)
