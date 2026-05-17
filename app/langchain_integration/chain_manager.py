"""
ChainManager — async version.

Key differences from Django version:
  - Uses asyncio.Lock instead of threading.Lock
  - cleanup() is an async task scheduled via asyncio
  - No global_lock for lock-of-locks: asyncio is single-threaded,
    so a plain dict for locks is safe.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.langchain_integration.chain import create_conversation_chain

logger = logging.getLogger(__name__)


class _ChainEntry:
    __slots__ = ("chain", "memory", "llm", "last_used")

    def __init__(self, chain, memory, llm):
        self.chain = chain
        self.memory = memory
        self.llm = llm
        self.last_used = time.monotonic()


class ChainManager:
    """
    Per-conversation chain cache with asyncio-native locking.
    """
    _cache: dict[str, _ChainEntry] = {}
    _locks: dict[str, asyncio.Lock] = {}
    TTL: float = 1800.0   # seconds; chains idle longer than this are evicted

    # ── Internal helpers ───────────────────────────────────────────────────────
    @classmethod
    def _key(cls, conversation_id: str, user_id: int, model_id: str) -> str:
        return f"{user_id}:{conversation_id}:{model_id}"

    @classmethod
    def _get_lock(cls, key: str) -> asyncio.Lock:
        if key not in cls._locks:
            cls._locks[key] = asyncio.Lock()
        return cls._locks[key]

    # ── Public API ─────────────────────────────────────────────────────────────
    @classmethod
    async def get(
        cls,
        conversation_id: str,
        user_id: int,
        model_id: str,
        generator: Any,
        system_prompt: str,
        **kwargs,
    ) -> tuple:
        """
        Returns (chain, memory, llm) — loads from cache or creates new.
        Thread-safe per conversation via asyncio.Lock.
        """
        key = cls._key(conversation_id, user_id, model_id)
        lock = cls._get_lock(key)

        async with lock:
            if key in cls._cache:
                entry = cls._cache[key]
                entry.last_used = time.monotonic()
                return entry.chain, entry.memory, entry.llm

            logger.info("🔗 Creating new chain | conv=%s model=%s", conversation_id, model_id)
            chain, memory, llm = create_conversation_chain(
                conversation_id=conversation_id,
                user_id=user_id,
                model_id=model_id,
                generator=generator,
                system_prompt=system_prompt,
                **kwargs,
            )
            cls._cache[key] = _ChainEntry(chain, memory, llm)
            return chain, memory, llm

    @classmethod
    async def cleanup(cls) -> int:
        """
        Evict chains that haven't been used within TTL.
        Returns number of evicted entries.
        Returns 0 immediately without holding any lock if cache is empty.
        """
        if not cls._cache:
            return 0

        now = time.monotonic()
        stale = [k for k, e in cls._cache.items() if now - e.last_used > cls.TTL]
        for key in stale:
            cls._cache.pop(key, None)
            cls._locks.pop(key, None)

        if stale:
            logger.info("🧹 Evicted %d stale chains", len(stale))
        return len(stale)
