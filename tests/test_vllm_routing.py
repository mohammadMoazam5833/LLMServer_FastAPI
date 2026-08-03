"""Unit tests for per-model vLLM base_url routing."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.core.security import encrypt_api_key
from app.runtime.vllm_routing import (
    resolve_upstream_api_key,
    resolve_vllm_base_url,
    upstream_api_key_fingerprint,
    upstream_auth_headers,
)
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


def test_upstream_auth_headers_empty():
    assert upstream_auth_headers(None) == {}
    assert upstream_auth_headers("  ") == {}


def test_upstream_auth_headers_both_schemes():
    h = upstream_auth_headers("secret-key")
    assert h["Authorization"] == "Bearer secret-key"
    assert h["X-API-Key"] == "secret-key"


def test_resolve_upstream_api_key_from_connection(monkeypatch):
    monkeypatch.setattr("app.runtime.vllm_routing.settings.VLLM_API_KEY", "env-fallback")
    raw = "conn-secret"
    conn = SimpleNamespace(
        is_active=True,
        api_key_encrypted=encrypt_api_key(raw),
    )
    model = SimpleNamespace(connection=conn)
    assert resolve_upstream_api_key(model) == raw


def test_resolve_upstream_api_key_falls_back_to_env(monkeypatch):
    monkeypatch.setattr("app.runtime.vllm_routing.settings.VLLM_API_KEY", "env-key")
    model = SimpleNamespace(connection=None)
    assert resolve_upstream_api_key(model) == "env-key"
    assert resolve_upstream_api_key(None) == "env-key"


def test_resolve_upstream_api_key_ignores_inactive_connection(monkeypatch):
    monkeypatch.setattr("app.runtime.vllm_routing.settings.VLLM_API_KEY", "env-key")
    conn = SimpleNamespace(
        is_active=False,
        api_key_encrypted=encrypt_api_key("should-not-use"),
    )
    model = SimpleNamespace(connection=conn)
    assert resolve_upstream_api_key(model) == "env-key"


def test_prepare_upstream_rewrites_model(monkeypatch):
    from app.api.code_bot import router as code_bot

    class FakeModel:
        id = "code-bot-v1"
        model_path = "qwen3-coder-30b"
        base_url = "http://llm-vllm-a:8003/v1"
        is_active = True
        connection = None
        connection_id = None
        fallback_model_ids = []

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


def test_prepare_upstream_chain_includes_auth(monkeypatch):
    from app.api.code_bot import router as code_bot

    class FakeModel:
        id = "m1"
        model_path = "served"
        base_url = "http://vllm:8003/v1"
        is_active = True
        connection = SimpleNamespace(
            is_active=True,
            base_url="http://vllm:8003/v1",
            api_key_encrypted=encrypt_api_key("upstream-secret"),
        )
        connection_id = "c1"
        fallback_model_ids = []

    async def fake_load(_db, _ref):
        return FakeModel()

    monkeypatch.setattr(code_bot, "load_active_model", fake_load)

    chain = asyncio.run(
        code_bot._prepare_upstream_chain(
            db=None,
            body={"model": "m1", "messages": []},
        )
    )
    assert len(chain) == 1
    base, body, mid, auth = chain[0]
    assert base == "http://vllm:8003/v1"
    assert body["model"] == "served"
    assert mid == "m1"
    assert auth["Authorization"] == "Bearer upstream-secret"
    assert auth["X-API-Key"] == "upstream-secret"


def test_prepare_upstream_unknown_model_uses_default(monkeypatch):
    from app.api.code_bot import router as code_bot

    async def fake_load(_db, _ref):
        return None

    monkeypatch.setattr(code_bot, "load_active_model", fake_load)
    monkeypatch.setattr(
        "app.runtime.vllm_routing.settings.VLLM_BASE_URL",
        "http://default:8003/v1",
    )
    monkeypatch.setattr(
        "app.runtime.vllm_routing.settings.VLLM_API_KEY",
        "default-upstream",
    )

    base, body = asyncio.run(
        code_bot._prepare_upstream(
            db=None,
            body={"model": "unknown-model", "stream": False},
        )
    )
    assert base == "http://default:8003/v1"
    assert body["model"] == "unknown-model"

    chain = asyncio.run(
        code_bot._prepare_upstream_chain(
            db=None,
            body={"model": "unknown-model", "stream": False},
        )
    )
    assert chain[0][3]["Authorization"] == "Bearer default-upstream"


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
    monkeypatch.setattr(
        "app.runtime.vllm_routing.settings.VLLM_API_KEY",
        "",
    )

    a = SimpleNamespace(id="m1", base_url="http://a:1/v1", model_path="x", connection=None)
    b = SimpleNamespace(id="m1", base_url="http://b:2/v1", model_path="x", connection=None)
    c = SimpleNamespace(id="m1", base_url="http://a:1/v1", model_path="x", connection=None)

    ga = GeneratorFactory.get(a)
    gb = GeneratorFactory.get(b)
    gc = GeneratorFactory.get(c)

    assert ga is not gb
    assert ga is gc
    assert len(created) == 2
    GeneratorFactory._cache.clear()


def test_generator_factory_cache_key_includes_api_key(monkeypatch):
    GeneratorFactory._cache.clear()
    created = []

    class FakeGen:
        def __init__(self, config):
            created.append(config)

        async def aclose(self):
            pass

    monkeypatch.setattr(
        "app.runtime.generator_factory.VLLMHttpGenerator",
        FakeGen,
    )
    monkeypatch.setattr(
        "app.runtime.vllm_routing.settings.VLLM_API_KEY",
        "",
    )

    conn_a = SimpleNamespace(
        is_active=True,
        base_url="http://a:1/v1",
        api_key_encrypted=encrypt_api_key("key-a"),
    )
    conn_b = SimpleNamespace(
        is_active=True,
        base_url="http://a:1/v1",
        api_key_encrypted=encrypt_api_key("key-b"),
    )
    a = SimpleNamespace(
        id="m1",
        base_url="http://a:1/v1",
        model_path="x",
        connection_id="c1",
        connection=conn_a,
    )
    b = SimpleNamespace(
        id="m1",
        base_url="http://a:1/v1",
        model_path="x",
        connection_id="c1",
        connection=conn_b,
    )

    ga = GeneratorFactory.get(a)
    gb = GeneratorFactory.get(b)
    assert ga is not gb
    assert len(created) == 2
    assert upstream_api_key_fingerprint("key-a") != upstream_api_key_fingerprint("key-b")
    GeneratorFactory._cache.clear()
