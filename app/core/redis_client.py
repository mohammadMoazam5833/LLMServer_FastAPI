"""
کلاینت مشترک Redis برای health check و ماژول‌های جانبی.
rate_limit از کلاینت async خودش استفاده می‌کند؛ این ماژول برای ping و attachment cache است.
"""
from __future__ import annotations

import logging

import redis.asyncio as aioredis

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

_client: aioredis.Redis | None = None


def get_async_client() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _client


async def ping() -> bool:
    """True اگر Redis پاسخ PING داد."""
    try:
        client = get_async_client()
        return (await client.ping()) is True
    except Exception as exc:
        logger.debug("Redis ping failed: %s", exc)
        return False


async def aclose() -> None:
    global _client
    if _client is not None:
        try:
            await _client.aclose()
        except Exception:
            pass
        _client = None
