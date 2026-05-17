from abc import ABC, abstractmethod
from typing import AsyncIterator


class BaseLLMProvider(ABC):
    @abstractmethod
    async def generate(self, messages: list[dict], **kwargs) -> dict:
        """Return {'text': str, 'usage': dict}"""

    @abstractmethod
    async def generate_stream(self, messages: list[dict], **kwargs) -> AsyncIterator[str]:
        """Yield string tokens one by one."""
