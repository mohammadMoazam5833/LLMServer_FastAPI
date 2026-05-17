"""
ChatProviderWrapper — async-native LangChain BaseChatModel.

Django version used threading + queue to bridge async→sync.
Here we implement _agenerate / _astream directly, so LangChain calls the
provider with native async — no threads, no asyncio.run().
"""
from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Iterator, List, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    BaseMessage,
    SystemMessage,
    AIMessage,
    HumanMessage,
    AIMessageChunk,
)
from langchain_core.outputs import ChatResult, ChatGeneration, ChatGenerationChunk

logger = logging.getLogger(__name__)


def _to_openai_messages(messages: List[BaseMessage]) -> list[dict]:
    """Convert LangChain message objects to OpenAI-style dicts."""
    result = []
    for m in messages:
        if isinstance(m, SystemMessage):
            role = "system"
        elif isinstance(m, AIMessage):
            role = "assistant"
        else:
            role = "user"
        result.append({"role": role, "content": m.content})
    return result


def _extract_max_tokens(kwargs: dict) -> int:
    """
    Pull max_tokens from kwargs or the LangChain configurable dict.
    Falls back to a generous default.
    """
    if "max_tokens" in kwargs:
        return int(kwargs["max_tokens"])

    config = kwargs.get("config") or {}
    val = config.get("configurable", {}).get("max_tokens")
    if val is not None:
        return int(val)

    logger.warning("⚠️  max_tokens not provided, defaulting to 4096")
    return 4096


class ChatProviderWrapper(BaseChatModel):
    """
    Wraps any BaseLLMProvider (vLLM / OpenAI / HuggingFace) as a
    LangChain chat model.

    _generate  → sync fallback (rarely used; delegates to async via asyncio)
    _agenerate → async non-streaming  ✅ preferred
    _stream    → sync streaming fallback
    _astream   → async streaming       ✅ preferred
    """

    generator: Any       # BaseLLMProvider instance
    model_id: str

    class Config:
        arbitrary_types_allowed = True

    @property
    def _llm_type(self) -> str:
        return "custom_async_chat"

    # ── Sync stubs (required by ABC) ───────────────────────────────────────────
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager=None,
        **kwargs,
    ) -> ChatResult:
        """
        Sync path — only called if LangChain invokes without await.
        We delegate to the async path via asyncio.
        """
        import asyncio
        return asyncio.get_event_loop().run_until_complete(
            self._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)
        )

    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager=None,
        **kwargs,
    ) -> Iterator[ChatGenerationChunk]:
        """Sync streaming fallback — delegates to async via asyncio."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        gen = self._astream(messages, stop=stop, run_manager=run_manager, **kwargs)
        while True:
            try:
                chunk = loop.run_until_complete(gen.__anext__())
                yield chunk
            except StopAsyncIteration:
                break

    # ── Async implementations ──────────────────────────────────────────────────
    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager=None,
        **kwargs,
    ) -> ChatResult:
        max_tokens = _extract_max_tokens(kwargs)
        converted = _to_openai_messages(messages)

        try:
            response = await self.generator.generate(converted, max_tokens=max_tokens)
            content = response.get("text", "")
            msg = AIMessage(content=content)
            return ChatResult(generations=[ChatGeneration(message=msg)])
        except Exception as e:
            logger.error("❌ _agenerate error: %s", e)
            raise

    async def _astream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager=None,
        **kwargs,
    ) -> AsyncIterator[ChatGenerationChunk]:
        max_tokens = _extract_max_tokens(kwargs)
        converted = _to_openai_messages(messages)

        try:
            async for token in self.generator.generate_stream(converted, max_tokens=max_tokens):
                chunk = ChatGenerationChunk(message=AIMessageChunk(content=str(token)))
                if run_manager:
                    await run_manager.on_llm_new_token(str(token), chunk=chunk)
                yield chunk
        except Exception as e:
            logger.error("❌ _astream error: %s", e)
            raise
