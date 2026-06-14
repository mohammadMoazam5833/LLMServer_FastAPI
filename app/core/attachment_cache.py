"""
کش Redis برای ضمائم دیده‌شده در هر مکالمه OpenWebUI (per-turn file scoping).

کلید: owui:attach:{conversation_key}
مقدار: JSON list از source/image fingerprints
TTL: REDIS_CHAT_TTL (پیش‌فرض ۷ روز)

اگر Redis در دسترس نباشد، به حافظه‌ی in-process برمی‌گردد (fail-open).
"""
from __future__ import annotations

import json
import logging

import redis

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

_KEY_PREFIX = "owui:attach:"
_memory_fallback: dict[str, set[str]] = {}
_redis_available: bool | None = None

_client: redis.Redis | None = None


def _redis_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _client


def _use_redis() -> bool:
    global _redis_available
    if _redis_available is False:
        return False
    try:
        _redis_client().ping()
        _redis_available = True
        return True
    except Exception:
        _redis_available = False
        return False


def _redis_key(conversation_key: str) -> str:
    return f"{_KEY_PREFIX}{conversation_key}"


def get_seen_attachments(conversation_key: str) -> set[str] | None:
    """مقدار ذخیره‌شده یا None اگر کلید وجود نداشته باشد."""
    if not conversation_key:
        return None
    if _use_redis():
        try:
            raw = _redis_client().get(_redis_key(conversation_key))
            if raw is None:
                return None
            items = json.loads(raw)
            return set(items) if isinstance(items, list) else set()
        except Exception as exc:
            logger.warning("⚠️  Attachment cache read failed (Redis): %s", exc)
    return _memory_fallback.get(conversation_key)


def set_seen_attachments(conversation_key: str, attachments: set[str]) -> None:
    if not conversation_key:
        return
    if _use_redis():
        try:
            key = _redis_key(conversation_key)
            _redis_client().set(key, json.dumps(sorted(attachments)), ex=settings.REDIS_CHAT_TTL)
            return
        except Exception as exc:
            logger.warning("⚠️  Attachment cache write failed (Redis): %s", exc)
    _memory_fallback[conversation_key] = set(attachments)


def bootstrap_seen_attachments(conversation_key: str, attachments: set[str]) -> None:
    if get_seen_attachments(conversation_key) is None:
        set_seen_attachments(conversation_key, attachments)


def delete_seen_attachments(conversation_key: str) -> None:
    if not conversation_key:
        return
    _memory_fallback.pop(conversation_key, None)
    if _use_redis():
        try:
            _redis_client().delete(_redis_key(conversation_key))
        except Exception as exc:
            logger.warning("⚠️  Attachment cache delete failed (Redis): %s", exc)


def reset_memory_fallback() -> None:
    """فقط برای تست."""
    _memory_fallback.clear()
    global _redis_available
    _redis_available = None


def ping() -> bool:
    return _use_redis()
