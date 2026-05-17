from typing import AsyncIterator
from .base import BaseLLMProvider


class HuggingFaceProvider(BaseLLMProvider):
    """
    Wraps VLLMHttpGenerator — which already talks to vLLM's OpenAI-compatible endpoint.
    Fully async; no threading required.
    """

    def __init__(self, config):
        from app.runtime.generator_factory import GeneratorFactory
        self._gen = GeneratorFactory.get(config)

    async def generate(self, messages: list[dict], **kwargs) -> dict:
        return await self._gen.generate(messages, **kwargs)

    async def generate_stream(self, messages: list[dict], **kwargs) -> AsyncIterator[str]:
        async for token in self._gen.generate_stream(messages, **kwargs):
            yield token
