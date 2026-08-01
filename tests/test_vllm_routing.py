"""Unit tests for per-model vLLM base_url routing."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.runtime.vllm_routing import resolve_vllm_base_url
from app.runtime.generator_factory import GeneratorFactory


def test_resolve_falls_back_to_settings(monkeypatch):
    monkeypatch.setattr(
        "app.runtime.vllm_routing.settings.VLLM_BASE_URL",
        "http://default-vllm:8003/v1/",
    )
    assert resolve_vllm_base_url(None) == "http://default-vllm:8003/v1"
    assert resolve_vllm_base_url(SimpleNamespace(base_url=None)) == "http://default-vllm:8003/v1"
    assert resolve_vllm_base_url(SimpleNamespace(base_url="  ")) == "http://default-vllm:8003/v1"


def test_resolve_prefers_model_base_url(monkeypatch):
    monkeypatch.setattr(
        "app.runtime.vllm_routing.settings.VLLM_BASE_URL",
        "http://default-vllm:8003/v1",
    )
    model = SimpleNamespace(base_url="http://llm-vllm-b:8003/v1/")
    assert resolve_vllm_base_url(model) == "http://llm-vllm-b:8003/v1"


def test_resolve_explicit_arg_wins(monkeypatch):
    monkeypatch.setattr(
        "app.runtime.vllm_routing.settings.VLLM_BASE_URL",
        "http://default-vllm:8003/v1",
    )
    model = SimpleNamespace(base_url="http://from-model:1/v1")
    assert (
        resolve_vllm_base_url(model, base_url="http://explicit:9/v1/")
        == "http://explicit:9/v1"
    )


def test_prepare_upstream_rewrites_model(monkeypatch):
    from app.api.code_bot import router as code_bot

    class FakeModel:
        id = "code-bot-v1"
        model_path = "qwen3-coder-30b"
        base_url = "http://llm-vllm-a:8003/v1"
        is_active = True

    async def fake_load(_db, ref):
        assert ref == "code-bot-v1"
        return FakeModel()

    monkeypatch.setattr(code_bot, "load_active_model", fake_load)

    base, body = asyncio.run(
        code_bot._prepare_upstream(
            db=None,
            body={"model": "code-bot-v1", "messages": [{"role": "user", "content": "hi"}]},
        )
    )
    assert base == "http://llm-vllm-a:8003/v1"
    assert body["model"] == "qwen3-coder-30b"


def test_prepare_upstream_unknown_model_uses_default(monkeypatch):
    from app.api.code_bot import router as code_bot

    async def fake_load(_db, _ref):
        return None

    monkeypatch.setattr(code_bot, "load_active_model", fake_load)
    monkeypatch.setattr(
        "app.runtime.vllm_routing.settings.VLLM_BASE_URL",
        "http://default:8003/v1",
    )

    base, body = asyncio.run(
        code_bot._prepare_upstream(
            db=None,
            body={"model": "unknown-model", "stream": False},
        )
    )
    assert base == "http://default:8003/v1"
    assert body["model"] == "unknown-model"


def test_generator_factory_cache_key_includes_base_url(monkeypatch):
    GeneratorFactory._cache.clear()

    created = []

    class FakeGen:
        def __init__(self, config):
            created.append(config)
            self.config = config

        async def aclose(self):
            pass

    monkeypatch.setattr(
        "app.runtime.generator_factory.VLLMHttpGenerator",
        FakeGen,
    )
    monkeypatch.setattr(
        "app.runtime.vllm_routing.settings.VLLM_BASE_URL",
        "http://default:8003/v1",
    )

    a = SimpleNamespace(id="m1", base_url="http://a:1/v1", model_path="x")
    b = SimpleNamespace(id="m1", base_url="http://b:2/v1", model_path="x")
    c = SimpleNamespace(id="m1", base_url="http://a:1/v1", model_path="x")

    ga = GeneratorFactory.get(a)
    gb = GeneratorFactory.get(b)
    gc = GeneratorFactory.get(c)

    assert ga is not gb
    assert ga is gc
    assert len(created) == 2
    GeneratorFactory._cache.clear()
