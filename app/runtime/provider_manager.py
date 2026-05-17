from app.runtime.providers.base import BaseLLMProvider


class ProviderManager:
    @staticmethod
    def get_provider(config) -> BaseLLMProvider:
        provider_type = config.provider.lower()

        if provider_type == "local":
            from app.runtime.providers.hf_provider import HuggingFaceProvider
            return HuggingFaceProvider(config)

        if provider_type == "openai":
            from app.runtime.providers.openai_provider import OpenAIProvider
            return OpenAIProvider(config)

        raise ValueError(f"Unsupported provider: {provider_type!r}")
