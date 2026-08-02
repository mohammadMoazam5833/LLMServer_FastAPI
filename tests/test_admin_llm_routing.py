"""LiteLLM-aligned routing / connection resolution tests."""
from __future__ import annotations

from types import SimpleNamespace

from app.runtime.vllm_routing import resolve_vllm_base_url


def test_resolve_active_connection_wins(monkeypatch):
    monkeypatch.setattr(
        "app.runtime.vllm_routing.settings.VLLM_BASE_URL",
        "http://default:8003/v1",
    )
    conn = SimpleNamespace(base_url="http://from-connection:8003/v1/", is_active=True)
    model = SimpleNamespace(base_url="http://stale:1/v1", connection_id="c1", connection=conn)
    assert resolve_vllm_base_url(model) == "http://from-connection:8003/v1"


def test_resolve_inactive_connection_fail_closed(monkeypatch):
    monkeypatch.setattr(
        "app.runtime.vllm_routing.settings.VLLM_BASE_URL",
        "http://default:8003/v1",
    )
    conn = SimpleNamespace(base_url="http://from-connection:8003/v1", is_active=False)
    model = SimpleNamespace(base_url="http://stale:1/v1", connection_id="c1", connection=conn)
    assert resolve_vllm_base_url(model) == ""


def test_resolve_unbound_legacy_uses_model_then_env(monkeypatch):
    monkeypatch.setattr(
        "app.runtime.vllm_routing.settings.VLLM_BASE_URL",
        "http://default:8003/v1",
    )
    model = SimpleNamespace(base_url="http://legacy:9/v1/", connection_id=None, connection=None)
    assert resolve_vllm_base_url(model) == "http://legacy:9/v1"
    model2 = SimpleNamespace(base_url=None, connection_id=None, connection=None)
    assert resolve_vllm_base_url(model2) == "http://default:8003/v1"
