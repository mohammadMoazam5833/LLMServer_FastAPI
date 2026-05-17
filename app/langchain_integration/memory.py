from langchain_redis import RedisChatMessageHistory
from langchain_classic.memory import ConversationBufferWindowMemory
from app.config import get_settings

settings = get_settings()


def create_redis_memory(
    conversation_id: str,
    user_id: int,
    **kwargs,  # absorbs unused model params forwarded from ChainManager.get()
) -> ConversationBufferWindowMemory:
    """
    Creates a Redis-backed sliding window memory (k=4 turns).
    Session key format: user:<uid>:conv:<conv_id>
    """
    session_id = f"user:{user_id}:conv:{conversation_id}"

    history = RedisChatMessageHistory(
        session_id=session_id,
        redis_url=settings.REDIS_URL,
        ttl=settings.REDIS_CHAT_TTL,
    )

    return ConversationBufferWindowMemory(
        chat_memory=history,
        k=4,
        return_messages=True,
        memory_key="chat_history",
        input_key="input",
        output_key="output",
    )
