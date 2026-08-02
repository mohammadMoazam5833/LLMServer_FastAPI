"""LiteLLM-style model fallback helpers."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx

from app.runtime.fallback import (
    generate_with_fallback,
    is_retryable_upstream_error,
    normalize_fallback_ids,
)


def test_normalize_fallback_ids_dedupes_and_drops_self():
    assert normalize_fallback_ids(["b", "b", "a", "", "primary"], self_id="primary") == ["b", "a"]


def test_retryable_connect_and_5xx():
    assert is_retryable_upstream_error(httpx.ConnectError("boom"))
    req = httpx.Request("POST", "http://x/v1/chat/completions")
    resp = httpx.Response(503, request=req)
    assert is_retryable_upstream_error(httpx.HTTPStatusError("x", request=req, response=resp))
    resp400 = httpx.Response(400, request=req)
    assert not is_retryable_upstream_error(httpx.HTTPStatusError("x", request=req, response=resp400))
    assert is_retryable_upstream_error(RuntimeError("Model 'x' has no usable api_base"))


def test_generate_with_fallback_switches_on_connect_error(monkeypatch):
    primary = SimpleNamespace(
        id="primary",
        model_path="served-a",
        provider="vllm",
        fallback_model_ids=["backup"],
        connection_id="c1",
        connection=SimpleNamespace(base_url="http://dead:1/v1", is_active=True),
        base_url="http://dead:1/v1",
    )
    backup = SimpleNamespace(
        id="backup",
        model_path="served-b",
        provider="vllm",
        fallback_model_ids=[],
        connection_id="c2",
        connection=SimpleNamespace(base_url="http://ok:2/v1", is_active=True),
        base_url="http://ok:2/v1",
        is_active=True,
    )

    async def fake_load(_db, mid):
        return backup if mid == "backup" else None

    monkeypatch.setattr("app.runtime.fallback.load_active_model", fake_load)
    monkeypatch.setattr(
        "app.runtime.fallback.resolve_vllm_base_url",
        lambda m, base_url=None: (getattr(m, "base_url", "") or "").rstrip("/"),
    )

    calls: list[str] = []

    class FakeGen:
        def __init__(self, model_id: str):
            self.model_id = model_id

        async def generate(self, messages, **kwargs):
            calls.append(self.model_id)
            if self.model_id == "primary":
                raise httpx.ConnectError("refused")
            return {"text": "ok", "usage": {}}

    monkeypatch.setattr(
        "app.runtime.fallback.ProviderManager.get_provider",
        lambda cfg: FakeGen(cfg.id),
    )

    result, used = asyncio.run(
        generate_with_fallback(
            MagicMock(),
            primary,
            [{"role": "user", "content": "hi"}],
            max_tokens=16,
            temperature=0.1,
        )
    )
    assert result["text"] == "ok"
    assert used.id == "backup"
    assert calls == ["primary", "backup"]


def test_generate_with_fallback_does_not_retry_client_error(monkeypatch):
    primary = SimpleNamespace(
        id="primary",
        model_path="served-a",
        provider="vllm",
        fallback_model_ids=["backup"],
        connection_id="c1",
        connection=SimpleNamespace(base_url="http://a/v1", is_active=True),
        base_url="http://a/v1",
    )

    monkeypatch.setattr(
        "app.runtime.fallback.resolve_vllm_base_url",
        lambda m, base_url=None: "http://a/v1",
    )

    async def fake_load(_db, mid):
        return SimpleNamespace(
            id="backup",
            base_url="http://b/v1",
            connection_id="c2",
            connection=SimpleNamespace(base_url="http://b/v1", is_active=True),
            is_active=True,
            model_path="b",
            provider="vllm",
            fallback_model_ids=[],
        )

    monkeypatch.setattr("app.runtime.fallback.load_active_model", fake_load)

    req = httpx.Request("POST", "http://a/v1/chat/completions")
    resp = httpx.Response(400, request=req, text="bad request")

    class FakeGen:
        async def generate(self, messages, **kwargs):
            raise httpx.HTTPStatusError("bad", request=req, response=resp)

    monkeypatch.setattr(
        "app.runtime.fallback.ProviderManager.get_provider",
        lambda cfg: FakeGen(),
    )

    try:
        asyncio.run(
            generate_with_fallback(
                MagicMock(),
                primary,
                [{"role": "user", "content": "hi"}],
                max_tokens=8,
                temperature=0.0,
            )
        )
        raise AssertionError("expected HTTPStatusError")
    except httpx.HTTPStatusError:
        pass
