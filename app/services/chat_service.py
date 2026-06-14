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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.langchain_integration.chain_manager import ChainManager
from app.models.llm import Conversation, Message
from app.services.token_utils import estimate_text_tokens

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
        tokens = estimate_text_tokens(content)
        msg = Message(
            conversation_id=self.conversation.id,
            role=role,
            content=content,
            prompt_tokens=tokens if role == Message.ROLE_USER else 0,
            completion_tokens=tokens if role == Message.ROLE_ASSISTANT else 0,
        )
        self.db.add(msg)
        await self.db.flush()  # write without committing (caller commits)

    async def _hydrate_memory(self, memory) -> None:
        """
        اگر حافظه‌ی Redis خالی باشد (مثلاً پس از eviction چین یا انقضای TTL)، تاریخچه‌ی
        مکالمه از PostgreSQL بازیابی و درون حافظه بارگذاری می‌شود تا مدل بافت قبلی را از دست ندهد.
        Redis منبع حقیقت است؛ اگر داده داشت، هیچ بازنویسی‌ای انجام نمی‌شود.
        """
        try:
            if memory.chat_memory.messages:
                return
        except Exception as exc:  # دسترسی به Redis ناموفق بود؛ بی‌صدا رد می‌شویم
            logger.warning("⚠️  Could not read Redis memory for hydration: %s", exc)
            return

        result = await self.db.execute(
            select(Message)
            .where(
                Message.conversation_id == self.conversation.id,
                Message.role != Message.ROLE_SYSTEM,
            )
            .order_by(Message.created_at)
        )
        history = result.scalars().all()
        if not history:
            return

        pending_user: str | None = None
        pairs = 0
        for m in history:
            if m.role == Message.ROLE_USER:
                pending_user = m.content
            elif m.role == Message.ROLE_ASSISTANT and pending_user is not None:
                memory.save_context({"input": pending_user}, {"output": m.content})
                pending_user = None
                pairs += 1
        if pairs:
            logger.info("💧 Hydrated %d turn(s) into Redis memory from DB | conv=%s", pairs, self.conversation.id)

    # ── Non-streaming ──────────────────────────────────────────────────────────
    async def chat(self, user_message: str, max_new_tokens: int) -> dict:
        chain, memory, _ = await self._get_chain()
        await self._hydrate_memory(memory)
        await self._save_message(Message.ROLE_USER, user_message)

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
        chain, memory, _ = await self._get_chain()
        await self._hydrate_memory(memory)
        await self._save_message(Message.ROLE_USER, user_message)

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
