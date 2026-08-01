from __future__ import annotations
import logging
from app.runtime.vllm_http_generator import VLLMHttpGenerator

logger = logging.getLogger(__name__)


class GeneratorFactory:
    """
    Caches one VLLMHttpGenerator per model id + base_url.
    The generator holds a shared httpx.AsyncClient for connection pooling.
    """
    _cache: dict[str, VLLMHttpGenerator] = {}

    @classmethod
    def _cache_key(cls, config) -> str:
        from app.runtime.vllm_routing import resolve_vllm_base_url
        base = resolve_vllm_base_url(config)
        return f"{getattr(config, 'id', 'unknown')}@{base}"

    @classmethod
    def get(cls, config) -> VLLMHttpGenerator:
        key = cls._cache_key(config)
        if key not in cls._cache:
            logger.info("🌐 Creating vLLM HTTP generator for model: %s", key)
            cls._cache[key] = VLLMHttpGenerator(config)
        return cls._cache[key]

    @classmethod
    async def close_all(cls):
        """Call on app shutdown to close all httpx clients."""
        for gen in cls._cache.values():
            await gen.aclose()
        cls._cache.clear()
