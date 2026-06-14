"""
محدودیت نرخ (rate limit) و سهمیه‌ی ماهانه‌ی توکن (quota) برای کلیدهای API.

پیاده‌سازی مبتنی بر Redis است:
  - rate limit: شمارنده‌ی پنجره‌ی ثابت یک‌دقیقه‌ای به ازای هر کلید.
  - quota: شمارنده‌ی ماهانه‌ی مصرف توکن به ازای هر کلید.

اگر Redis در دسترس نباشد، محدودیت‌ها به‌جای شکستن سرویس، با هشدار نادیده گرفته می‌شوند
(fail-open) تا یک خطای زیرساختی کل API را از کار نیندازد.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import redis.asyncio as aioredis
from fastapi import HTTPException, status

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

_redis: aioredis.Redis | None = None


def _client() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


def _month_key(api_key_id: str) -> str:
    now = datetime.now(timezone.utc)
    return f"quota:{api_key_id}:{now.year}-{now.month:02d}"


async def enforce_rate_limit(api_key_id: str, limit_per_minute: int) -> None:
    """در صورت عبور از سقف درخواست در دقیقه، خطای 429 می‌دهد."""
    if not api_key_id or limit_per_minute <= 0:
        return
    try:
        client = _client()
        window = int(time.time() // 60)
        key = f"ratelimit:{api_key_id}:{window}"
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, 90)
    except Exception as exc:  # fail-open
        logger.warning("⚠️  Rate-limit check skipped (Redis error): %s", exc)
        return

    if count > limit_per_minute:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please retry shortly.",
            headers={"Retry-After": "60"},
        )


async def enforce_quota(api_key_id: str, monthly_quota: int) -> None:
    """اگر مصرف ماهانه‌ی توکن از سهمیه گذشته باشد، خطای 429 می‌دهد."""
    if not api_key_id or monthly_quota <= 0:
        return
    try:
        client = _client()
        used_raw = await client.get(_month_key(api_key_id))
        used = int(used_raw) if used_raw else 0
    except Exception as exc:  # fail-open
        logger.warning("⚠️  Quota check skipped (Redis error): %s", exc)
        return

    if used >= monthly_quota:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Monthly token quota exceeded.",
        )


async def record_tokens(api_key_id: str, tokens: int) -> None:
    """مصرف توکن را به شمارنده‌ی ماهانه اضافه می‌کند (TTL حدود ۴۰ روز)."""
    if not api_key_id or tokens <= 0:
        return
    try:
        client = _client()
        key = _month_key(api_key_id)
        new_value = await client.incrby(key, int(tokens))
        if new_value == int(tokens):  # اولین نوشتن این ماه
            await client.expire(key, 60 * 60 * 24 * 40)
    except Exception as exc:  # fail-open
        logger.warning("⚠️  Token usage recording skipped (Redis error): %s", exc)


async def aclose() -> None:
    global _redis
    if _redis is not None:
        try:
            await _redis.aclose()
        except Exception:
            pass
        _redis = None
