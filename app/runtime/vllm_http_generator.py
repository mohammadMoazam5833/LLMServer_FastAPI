"""
Async HTTP client for a vLLM-served OpenAI-compatible endpoint.

Key improvement over Django version:
  - No threading hacks; generate() and generate_stream() are native async.
  - A single shared httpx.AsyncClient is created per generator instance.
"""
from __future__ import annotations

import json
import logging
from typing import AsyncIterator

import httpx

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class VLLMHttpGenerator:
    def __init__(self, config):
        self.base_url = settings.VLLM_BASE_URL
        self.model = config.model_path
        self._timeout = httpx.Timeout(settings.VLLM_REQUEST_TIMEOUT, connect=10.0)
        # Shared client — reused across requests for connection pooling
        self._client = httpx.AsyncClient(timeout=self._timeout)

    # ── Non-streaming ──────────────────────────────────────────────────────────
    async def generate(
        self,
        messages: list[dict],
        max_tokens: int = 1024,
        temperature: float = 0.7,
        **kwargs,
    ) -> dict:
        msg_count = len(messages)
        total_input_chars = sum(len(m.get("content", "") or "") for m in messages)
        estimated_input_tokens = total_input_chars // 3
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        logger.info(
            "📤 vLLM non-stream request | model=%s | max_tokens=%d | temp=%.2f | msgs=%d | input_chars=%d | input_tokens~=%d",
            self.model, max_tokens, temperature, msg_count, total_input_chars, estimated_input_tokens
        )

        try:
            response = await self._client.post(
                f"{self.base_url}/chat/completions", json=payload
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            content_len = len(content)
            finish_reason = data["choices"][0].get("finish_reason", "unknown")
            usage = data.get("usage", {})
            logger.info(
                "✅ vLLM non-stream response | content_len=%d chars | finish_reason=%s | usage=%s",
                content_len, finish_reason, usage
            )
            return {
                "text": content,
                "usage": usage,
            }
        except httpx.HTTPStatusError as e:
            logger.error("❌ vLLM HTTP error %d: %s", e.response.status_code, e.response.text)
            raise
        except Exception as e:
            logger.error("❌ vLLM generate error: %s", e)
            raise

    # ── Streaming ──────────────────────────────────────────────────────────────
    async def generate_stream(
        self,
        messages: list[dict],
        max_tokens: int = 1024,
        temperature: float = 0.7,
        **kwargs,
    ) -> AsyncIterator[str]:
        msg_count = len(messages)
        total_input_chars = sum(len(m.get("content", "") or "") for m in messages)
        estimated_input_tokens = total_input_chars // 3
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        logger.info(
            "🔗 vLLM stream START | model=%s | max_tokens=%d | temp=%.2f | msgs=%d | input_chars=%d | input_tokens~=%d",
            self.model, max_tokens, temperature, msg_count, total_input_chars, estimated_input_tokens
        )
        chunk_count = 0
        total_chars = 0
        last_token = ""

        try:
            async with self._client.stream(
                "POST", f"{self.base_url}/chat/completions", json=payload
            ) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    logger.error("❌ vLLM stream HTTP %d: %s", response.status_code, body)
                    return

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    raw = line[6:].strip()
                    if raw == "[DONE]":
                        finish_reason = data.get("choices", [{}])[0].get("finish_reason", "unknown") if 'data' in locals() else "unknown"
                        logger.info(
                            "🏁 vLLM stream DONE | chunks=%d | total_chars=%d | last_token_len=%d | finish_reason=%s",
                            chunk_count, total_chars, len(last_token), finish_reason
                        )
                        break
                    try:
                        data = json.loads(raw)
                        delta = data.get("choices", [{}])[0].get("delta", {})
                        if "content" in delta:
                            chunk_count += 1
                            token = delta["content"]
                            total_chars += len(token)
                            last_token = token
                            yield token
                    except json.JSONDecodeError:
                        logger.warning("⚠️  JSON parse error on chunk: %s", raw[:200])

        except httpx.RemoteProtocolError:
            logger.error("🚨 vLLM connection closed prematurely | chunks=%d | total_chars=%d", chunk_count, total_chars)
        except httpx.TimeoutException:
            logger.error("🚨 vLLM timeout | chunks=%d | total_chars=%d", chunk_count, total_chars)
        except Exception as e:
            logger.error("🚨 vLLM stream exception: %s - %s | chunks=%d | total_chars=%d", type(e).__name__, e, chunk_count, total_chars)
        finally:
            logger.info("🔌 vLLM stream pipeline closed | final_chunks=%d | final_chars=%d", chunk_count, total_chars)

    async def aclose(self):
        """Call on app shutdown to close the shared HTTP client."""
        await self._client.aclose()
