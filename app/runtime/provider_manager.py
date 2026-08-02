from app.runtime.providers.base import BaseLLMProvider


# LiteLLM-style providers that speak OpenAI-compatible HTTP (incl. vLLM / Ollama /v1).
_OPENAI_COMPAT_HTTP = {
    "local",
    "vllm",
    "ollama",
    "openai_compatible",
    "hosted_vllm",
}


class ProviderManager:
    @staticmethod
    def get_provider(config) -> BaseLLMProvider:
        provider_type = (config.provider or "local").lower()

        if provider_type in _OPENAI_COMPAT_HTTP:
            from app.runtime.providers.hf_provider import HuggingFaceProvider
            return HuggingFaceProvider(config)

        if provider_type == "openai":
            # Custom api_base (LiteLLM openai + api_base) → same HTTP generator as vLLM.
            from app.runtime.vllm_routing import resolve_vllm_base_url
            base = resolve_vllm_base_url(config)
            if base and "api.openai.com" not in base:
                from app.runtime.providers.hf_provider import HuggingFaceProvider
                return HuggingFaceProvider(config)
            from app.runtime.providers.openai_provider import OpenAIProvider
            return OpenAIProvider(config)

        raise ValueError(f"Unsupported provider: {provider_type!r}")
