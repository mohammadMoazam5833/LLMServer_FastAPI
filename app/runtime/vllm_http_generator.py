from __future__ import annotations

import json
import logging
from typing import AsyncIterator, Any, Dict, List

import httpx

from app.config import get_settings
from app.services.token_utils import estimate_message_tokens
from app.runtime.vllm_routing import resolve_vllm_base_url

settings = get_settings()
logger = logging.getLogger(__name__)


class VLLMHttpGenerator:
    def __init__(self, config: Any):
        self.base_url = resolve_vllm_base_url(config)
        self.model = config.model_path
        logger.info(
            "🌐 VLLMHttpGenerator ready | model_id=%s | served=%s | base_url=%s",
            getattr(config, "id", "?"),
            self.model,
            self.base_url,
        )
        
        # ۱. حل مشکل تایم‌اوت: اگر مقدار تنظیمات خیلی کم یا نامعتبر بود، حداقل ۱۸۰ ثانیه اعمال می‌شود
        config_timeout = getattr(settings, "VLLM_REQUEST_TIMEOUT", 180.0)
        request_timeout = config_timeout if (config_timeout and config_timeout >= 120.0) else 180.0
        
        # مقدار اختصاصی برای زمان خواندن (Read) به دلیل سنگین بودن پردازش اولیه مدل ۳۰ میلیاردی
        self._timeout = httpx.Timeout(
            timeout=request_timeout,
            connect=10.0,
            read=request_timeout,
            write=10.0
        )
        
        # کلاینت اشتراکی به همراه مدیریت بهینه کانکشن‌ها (Pool Limits)
        self._client = httpx.AsyncClient(
            timeout=self._timeout,
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=10)
        )

    # ── Non-streaming ──────────────────────────────────────────────────────────
    async def generate(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: int = 1024,
        temperature: float = 0.7,
        **kwargs,
    ) -> Dict[str, Any]:
        msg_count = len(messages)
        total_input_chars = sum(len(m.get("content", "") or "") for m in messages)
        estimated_input_tokens = sum(estimate_message_tokens(m) for m in messages)
        
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
            **kwargs
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
            finish_reason = data["choices"][0].get("finish_reason", "unknown")
            usage = data.get("usage", {})
            
            logger.info(
                "✅ vLLM non-stream response | content_len=%d chars | finish_reason=%s | usage=%s",
                len(content), finish_reason, usage
            )
            return {
                "text": content,
                "usage": usage,
            }
        except httpx.HTTPStatusError as e:
            logger.error("❌ vLLM HTTP error %d: %s", e.response.status_code, e.response.text)
            raise
        except httpx.TimeoutException as e:
            logger.error("❌ vLLM timeout during non-stream generation: %s", e)
            raise
        except Exception as e:
            logger.error("❌ vLLM generate error: %s", e)
            raise

    # ── Streaming ──────────────────────────────────────────────────────────────
    async def generate_stream(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: int = 1024,
        temperature: float = 0.7,
        **kwargs,
    ) -> AsyncIterator[str]:
        msg_count = len(messages)
        total_input_chars = sum(len(m.get("content", "") or "") for m in messages)
        estimated_input_tokens = sum(estimate_message_tokens(m) for m in messages)
        
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
            **kwargs
        }
        
        logger.info(
            "🔗 vLLM stream START | model=%s | max_tokens=%d | temp=%.2f | msgs=%d | input_chars=%d | input_tokens~=%d",
            self.model, max_tokens, temperature, msg_count, total_input_chars, estimated_input_tokens
        )
        
        chunk_count = 0
        total_chars = 0
        last_token = ""
        last_data: Dict[str, Any] = {}  # حل باگ اسکوپ متغیر

        try:
            async with self._client.stream(
                "POST", f"{self.base_url}/chat/completions", json=payload
            ) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    logger.error("❌ vLLM stream HTTP %d: %s", response.status_code, body.decode(errors="ignore"))
                    response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                        
                    raw = line[6:].strip()
                    if raw == "[DONE]":
                        finish_reason = last_data.get("choices", [{}])[0].get("finish_reason", "unknown")
                        log_fn = logger.warning if finish_reason == "length" else logger.info
                        log_fn(
                            "🏁 vLLM stream DONE | chunks=%d | total_chars=%d | last_token_len=%d | finish_reason=%s",
                            chunk_count, total_chars, len(last_token), finish_reason,
                        )
                        if finish_reason == "length":
                            logger.warning(
                                "⚠️  پاسخ ناقص شد — سقف max_tokens پر شد. در OpenWebUI مقدار max_tokens را "
                                "افزایش دهید یا CHAT_MIN_OUTPUT_TOKENS را در .env بالاتر ببرید."
                            )
                        break
                        
                    try:
                        last_data = json.loads(raw)
                        delta = last_data.get("choices", [{}])[0].get("delta", {})
                        if "content" in delta:
                            chunk_count += 1
                            token = delta["content"]
                            total_chars += len(token)
                            last_token = token
                            yield token
                    except json.JSONDecodeError:
                        logger.warning("⚠️  JSON parse error on chunk: %s", raw[:200])

        except httpx.RemoteProtocolError as e:
            logger.error("🚨 vLLM connection closed prematurely | chunks=%d | total_chars=%d | err=%s", chunk_count, total_chars, e)
            raise
        except httpx.TimeoutException as e:
            # ۲. رفع باگ اصلی: خطا را دوباره بالا می‌فرستیم تا کلاینت با استریم خالی فریب نخورد
            logger.error("🚨 vLLM timeout during streaming | chunks=%d | total_chars=%d | err=%s", chunk_count, total_chars, e)
            raise
        except Exception as e:
            logger.error("🚨 vLLM stream exception: %s - %s | chunks=%d | total_chars=%d", type(e).__name__, e, chunk_count, total_chars)
            raise
        finally:
            logger.info("🔌 vLLM stream pipeline closed | final_chunks=%d | final_chars=%d", chunk_count, total_chars)

    async def aclose(self):
        """Call on app shutdown to close the shared HTTP client."""
        await self._client.aclose()