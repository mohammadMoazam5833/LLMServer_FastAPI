"""
ChatService — async-native replacement for the Django version.

Improvements:
  - All DB writes are async (SQLAlchemy async session)
  - chain.ainvoke / chain.astream used directly
  - No threading, no asyncio.run() bridges
"""
from __future__ import annotations

import logging
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.langchain_integration.chain_manager import ChainManager
from app.models.llm import Conversation, Message

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(
        self,
        generator,
        model_id: str,
        conversation: Conversation,
        user_id: int,
        db: AsyncSession,
        system_prompt: str | None = None,
        **kwargs,
    ):
        self.conversation = conversation
        self.user_id = user_id
        self.db = db
        self._generator = generator
        self._model_id = model_id
        self._kwargs = kwargs
        self._system_prompt = system_prompt or conversation.system_prompt or "You are a helpful coding assistant."

    async def _get_chain(self):
        return await ChainManager.get(
            conversation_id=str(self.conversation.id),
            user_id=self.user_id,
            model_id=self._model_id,
            generator=self._generator,
            system_prompt=self._system_prompt,
            **self._kwargs,
        )

    async def _save_message(self, role: str, content: str):
        msg = Message(
            conversation_id=self.conversation.id,
            role=role,
            content=content,
        )
        self.db.add(msg)
        await self.db.flush()  # write without committing (caller commits)

    # ── Non-streaming ──────────────────────────────────────────────────────────
    async def chat(self, user_message: str, max_new_tokens: int) -> dict:
        await self._save_message(Message.ROLE_USER, user_message)

        chain, memory, _ = await self._get_chain()
        config = {"configurable": {"max_tokens": int(max_new_tokens)}}

        try:
            response = await chain.ainvoke({"input": user_message}, config=config)
            content = response.content if hasattr(response, "content") else str(response)

            await self._save_message(Message.ROLE_ASSISTANT, content)
            memory.save_context({"input": user_message}, {"output": content})

            logger.info("✅ chat done | conv=%s | len=%d", self.conversation.id, len(content))
            return {"text": content}
        except Exception as e:
            logger.error("❌ chat error: %s", e)
            raise

    # ── Streaming ──────────────────────────────────────────────────────────────
    async def stream(self, user_message: str, max_new_tokens: int) -> AsyncIterator[str]:
        await self._save_message(Message.ROLE_USER, user_message)

        chain, memory, _ = await self._get_chain()
        config = {"configurable": {"max_tokens": int(max_new_tokens)}}
        full_content = ""

        logger.info("📡 stream start | conv=%s | max_tokens=%d", self.conversation.id, max_new_tokens)

        try:
            async for chunk in chain.astream({"input": user_message}, config=config):
                token = chunk.content if hasattr(chunk, "content") else str(chunk)
                full_content += token
                yield token

            if full_content:
                await self._save_message(Message.ROLE_ASSISTANT, full_content)
                memory.save_context({"input": user_message}, {"output": full_content})
                logger.info("✅ stream done | conv=%s | chars=%d", self.conversation.id, len(full_content))

        except GeneratorExit:
            logger.warning("⚠️  client disconnected at char %d", len(full_content))
            if full_content:
                await self._save_message(
                    Message.ROLE_ASSISTANT,
                    full_content + "\n\n[قطع شده توسط کاربر]"
                )
        except Exception as e:
            logger.error("🔥 stream error: %s", e)
            raise
