"""
Builds the LangChain LCEL conversation chain.
Uses ainvoke / astream throughout — no sync bridges.
"""
from __future__ import annotations

import logging
from typing import AsyncIterator

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableLambda

from app.langchain_integration.memory import create_redis_memory
from app.langchain_integration.model_wrapper import ChatProviderWrapper
from app.services.openwebui_tasks import filter_openwebui_internal_history

logger = logging.getLogger(__name__)


def create_conversation_chain(
    conversation_id: str,
    user_id: int,
    model_id: str,
    generator,
    system_prompt: str,
    **kwargs,
):
    """
    Returns (chain, memory, llm).
    chain: async-capable LCEL Runnable
    """
    memory = create_redis_memory(
        conversation_id=conversation_id,
        user_id=user_id,
        **kwargs,
    )
    llm = ChatProviderWrapper(generator=generator, model_id=model_id)

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{input}"),
    ])

    # ── async-aware history loader ─────────────────────────────────────────────
    async def _load_history(input_data: dict) -> list:
        vars_ = memory.load_memory_variables({"input": input_data["input"]})
        raw_history = vars_.get("chat_history", [])
        history = filter_openwebui_internal_history(raw_history)
        removed = len(raw_history) - len(history)
        if removed:
            logger.info("🧹 Filtered %d Open WebUI internal history messages", removed)
        if history:
            last = history[-1]
            preview = last.content[:40] if hasattr(last, "content") else str(last)[:40]
            logger.info("🧠 History len=%d | last: %s…", len(history), preview)
        return history

    chain = (
        {
            "input": lambda x: x["input"],
            "chat_history": RunnableLambda(_load_history),
        }
        | prompt
        | llm
    )
    return chain, memory, llm
