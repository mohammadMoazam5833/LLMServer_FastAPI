from typing import AsyncIterator
import openai
from .base import BaseLLMProvider


class OpenAIProvider(BaseLLMProvider):
    def __init__(self, config):
        self.model_id = config.model_path
        self.api_key = (config.metadata_ or {}).get("api_key")

    async def generate(self, messages: list[dict], **kwargs) -> dict:
        client = openai.AsyncOpenAI(api_key=self.api_key)
        response = await client.chat.completions.create(
            model=self.model_id,
            messages=messages,
            stream=False,
            **kwargs,
        )
        return {"text": response.choices[0].message.content, "usage": {}}

    async def generate_stream(self, messages: list[dict], **kwargs) -> AsyncIterator[str]:
        client = openai.AsyncOpenAI(api_key=self.api_key)
        stream = await client.chat.completions.create(
            model=self.model_id,
            messages=messages,
            stream=True,
            **kwargs,
        )
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
