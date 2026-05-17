from __future__ import annotations
import logging
from app.runtime.vllm_http_generator import VLLMHttpGenerator

logger = logging.getLogger(__name__)


class GeneratorFactory:
    """
    Caches one VLLMHttpGenerator per model id.
    The generator holds a shared httpx.AsyncClient for connection pooling.
    """
    _cache: dict[str, VLLMHttpGenerator] = {}

    @classmethod
    def get(cls, config) -> VLLMHttpGenerator:
        if config.id not in cls._cache:
            logger.info("🌐 Creating vLLM HTTP generator for model: %s", config.id)
            cls._cache[config.id] = VLLMHttpGenerator(config)
        return cls._cache[config.id]

    @classmethod
    async def close_all(cls):
        """Call on app shutdown to close all httpx clients."""
        for gen in cls._cache.values():
            await gen.aclose()
        cls._cache.clear()
