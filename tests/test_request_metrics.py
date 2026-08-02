"""Unit tests for per-model request metrics helpers."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from app.core import request_metrics as rm


def test_row_from_hash_computes_avg_and_error_rate():
    row = rm._row_from_hash(
        "qwen",
        {
            "requests": "10",
            "errors": "2",
            "fallbacks": "1",
            "latency_ms_sum": "1000",
            "latency_ms_count": "10",
            "prompt_tokens": "100",
            "completion_tokens": "50",
            "total_tokens": "150",
        },
    )
    assert row["model_id"] == "qwen"
    assert row["avg_latency_ms"] == 100.0
    assert row["error_rate"] == 20.0
    assert row["total_tokens"] == 150


def test_summarize_aggregates_multi_day(monkeypatch):
    today = datetime.now(timezone.utc).date().isoformat()

    class FakeRedis:
        async def scan_iter(self, match=None, count=200):
            if today in (match or ""):
                yield f"metrics:model:m1:{today}"
                yield f"metrics:model:m2:{today}"

        async def hgetall(self, key):
            if key.endswith(":m1:" + today) or key.endswith("m1:" + today) or ":m1:" in key:
                return {
                    "requests": "4",
                    "errors": "1",
                    "fallbacks": "0",
                    "latency_ms_sum": "400",
                    "latency_ms_count": "4",
                    "prompt_tokens": "40",
                    "completion_tokens": "10",
                    "total_tokens": "50",
                }
            return {
                "requests": "6",
                "errors": "0",
                "fallbacks": "2",
                "latency_ms_sum": "600",
                "latency_ms_count": "6",
                "prompt_tokens": "60",
                "completion_tokens": "20",
                "total_tokens": "80",
            }

    monkeypatch.setattr(rm, "_client", lambda: FakeRedis())
    summary = asyncio.run(rm.summarize_model_metrics(days=1))
    assert summary["totals"]["requests"] == 10
    assert summary["totals"]["errors"] == 1
    assert summary["totals"]["fallbacks"] == 2
    assert summary["totals"]["total_tokens"] == 130
    assert abs(summary["totals"]["avg_latency_ms"] - 100.0) < 0.1
    assert len(summary["models"]) == 2


def test_record_model_request_pipeline(monkeypatch):
    executed = {}

    class FakePipe:
        def hincrby(self, *a, **k):
            return self

        def expire(self, *a, **k):
            return self

        async def execute(self):
            executed["ok"] = True

    class FakeRedis:
        def pipeline(self):
            return FakePipe()

    monkeypatch.setattr(rm, "_client", lambda: FakeRedis())
    asyncio.run(
        rm.record_model_request(
            model_id="x",
            latency_ms=12.4,
            ok=True,
            total_tokens=9,
        )
    )
    assert executed["ok"] is True


def test_prometheus_text_includes_model(monkeypatch):
    async def fake_summary(days=1):
        return {
            "days": days,
            "from_date": "2026-08-01",
            "to_date": "2026-08-01",
            "models": [
                {
                    "model_id": "qwen",
                    "requests": 3,
                    "errors": 1,
                    "fallbacks": 0,
                    "avg_latency_ms": 12.5,
                    "total_tokens": 99,
                }
            ],
            "totals": {},
        }

    monkeypatch.setattr(rm, "summarize_model_metrics", fake_summary)
    text = asyncio.run(rm.prometheus_text(days=1))
    assert 'llm_gateway_requests_total{model="qwen"} 3' in text
    assert 'llm_gateway_tokens_total{model="qwen"} 99' in text
