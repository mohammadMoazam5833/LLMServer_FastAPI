"""
Per-model gateway observability (LiteLLM-style request/latency/error/token stats).

Stored in Redis hashes (fail-open if Redis is down):
  metrics:model:{model_id}:{YYYY-MM-DD}
    requests, errors, fallbacks,
    latency_ms_sum, latency_ms_count,
    prompt_tokens, completion_tokens, total_tokens
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import redis.asyncio as aioredis

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

_redis: aioredis.Redis | None = None
_KEY_PREFIX = "metrics:model:"
_TTL_SECONDS = 60 * 60 * 24 * 45  # ~45 days


def _client() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


def _day_key(model_id: str, day: date | None = None) -> str:
    d = day or datetime.now(timezone.utc).date()
    mid = (model_id or "unknown").strip() or "unknown"
    return f"{_KEY_PREFIX}{mid}:{d.isoformat()}"


async def record_model_request(
    *,
    model_id: str,
    latency_ms: float,
    ok: bool,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    used_fallback: bool = False,
) -> None:
    """Increment per-model daily counters. Never raises to callers."""
    if not model_id:
        return
    try:
        client = _client()
        key = _day_key(model_id)
        pipe = client.pipeline()
        pipe.hincrby(key, "requests", 1)
        if not ok:
            pipe.hincrby(key, "errors", 1)
        if used_fallback:
            pipe.hincrby(key, "fallbacks", 1)
        ms = max(0, int(round(latency_ms)))
        pipe.hincrby(key, "latency_ms_sum", ms)
        pipe.hincrby(key, "latency_ms_count", 1)
        if prompt_tokens > 0:
            pipe.hincrby(key, "prompt_tokens", int(prompt_tokens))
        if completion_tokens > 0:
            pipe.hincrby(key, "completion_tokens", int(completion_tokens))
        if total_tokens > 0:
            pipe.hincrby(key, "total_tokens", int(total_tokens))
        pipe.expire(key, _TTL_SECONDS)
        await pipe.execute()
    except Exception as exc:  # fail-open
        logger.warning("⚠️  Model metrics recording skipped (Redis error): %s", exc)


async def record_fallback_success(model_id: str) -> None:
    """Count a successful failover onto a backup deployment for the client model."""
    if not model_id:
        return
    try:
        client = _client()
        key = _day_key(model_id)
        pipe = client.pipeline()
        pipe.hincrby(key, "fallbacks", 1)
        pipe.expire(key, _TTL_SECONDS)
        await pipe.execute()
    except Exception as exc:
        logger.warning("⚠️  Fallback metric skipped (Redis error): %s", exc)


def _as_int(raw: Any) -> int:
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


def _row_from_hash(model_id: str, data: dict[str, str]) -> dict[str, Any]:
    requests = _as_int(data.get("requests"))
    errors = _as_int(data.get("errors"))
    latency_sum = _as_int(data.get("latency_ms_sum"))
    latency_count = _as_int(data.get("latency_ms_count"))
    avg_latency = round(latency_sum / latency_count, 1) if latency_count else 0.0
    error_rate = round((errors / requests) * 100.0, 2) if requests else 0.0
    return {
        "model_id": model_id,
        "requests": requests,
        "errors": errors,
        "fallbacks": _as_int(data.get("fallbacks")),
        "error_rate": error_rate,
        "avg_latency_ms": avg_latency,
        "latency_ms_sum": latency_sum,
        "latency_ms_count": latency_count,
        "prompt_tokens": _as_int(data.get("prompt_tokens")),
        "completion_tokens": _as_int(data.get("completion_tokens")),
        "total_tokens": _as_int(data.get("total_tokens")),
    }


def _empty_summary(days: int, day_list: list[date]) -> dict[str, Any]:
    return {
        "days": days,
        "from_date": day_list[-1].isoformat(),
        "to_date": day_list[0].isoformat(),
        "models": [],
        "totals": {
            "model_id": "_total",
            "requests": 0,
            "errors": 0,
            "fallbacks": 0,
            "error_rate": 0.0,
            "avg_latency_ms": 0.0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }


async def summarize_model_metrics(days: int = 7) -> dict[str, Any]:
    """Aggregate per-model stats over the last N UTC days (inclusive of today)."""
    days = max(1, min(int(days or 7), 45))
    today = datetime.now(timezone.utc).date()
    day_list = [today - timedelta(days=i) for i in range(days)]
    by_model: dict[str, dict[str, Any]] = {}

    try:
        client = _client()
        for day in day_list:
            pattern = f"{_KEY_PREFIX}*:{day.isoformat()}"
            async for key in client.scan_iter(match=pattern, count=200):
                if not key.startswith(_KEY_PREFIX):
                    continue
                rest = key[len(_KEY_PREFIX) :]
                if ":" not in rest:
                    continue
                model_id, _day = rest.rsplit(":", 1)
                data = await client.hgetall(key)
                if not data:
                    continue
                row = _row_from_hash(model_id, data)
                acc = by_model.get(model_id)
                if acc is None:
                    by_model[model_id] = row
                    continue
                for k in (
                    "requests",
                    "errors",
                    "fallbacks",
                    "latency_ms_sum",
                    "latency_ms_count",
                    "prompt_tokens",
                    "completion_tokens",
                    "total_tokens",
                ):
                    acc[k] += row[k]
    except Exception as exc:
        logger.warning("⚠️  Model metrics read skipped (Redis error): %s", exc)
        return _empty_summary(days, day_list)

    models: list[dict[str, Any]] = []
    totals = {
        "requests": 0,
        "errors": 0,
        "fallbacks": 0,
        "latency_ms_sum": 0,
        "latency_ms_count": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    for _mid, acc in by_model.items():
        lat_n = acc.pop("latency_ms_count", 0)
        lat_sum = acc.pop("latency_ms_sum", 0)
        acc["avg_latency_ms"] = round(lat_sum / lat_n, 1) if lat_n else 0.0
        acc["error_rate"] = (
            round((acc["errors"] / acc["requests"]) * 100.0, 2) if acc["requests"] else 0.0
        )
        models.append(acc)
        for k in ("requests", "errors", "fallbacks", "prompt_tokens", "completion_tokens", "total_tokens"):
            totals[k] += acc[k]
        totals["latency_ms_sum"] += lat_sum
        totals["latency_ms_count"] += lat_n

    models.sort(key=lambda r: r["requests"], reverse=True)
    total_row = {
        "model_id": "_total",
        "requests": totals["requests"],
        "errors": totals["errors"],
        "fallbacks": totals["fallbacks"],
        "error_rate": (
            round((totals["errors"] / totals["requests"]) * 100.0, 2)
            if totals["requests"]
            else 0.0
        ),
        "avg_latency_ms": (
            round(totals["latency_ms_sum"] / totals["latency_ms_count"], 1)
            if totals["latency_ms_count"]
            else 0.0
        ),
        "prompt_tokens": totals["prompt_tokens"],
        "completion_tokens": totals["completion_tokens"],
        "total_tokens": totals["total_tokens"],
    }
    return {
        "days": days,
        "from_date": day_list[-1].isoformat(),
        "to_date": day_list[0].isoformat(),
        "models": models,
        "totals": total_row,
    }


async def prometheus_text(days: int = 1) -> str:
    """Export counters in Prometheus exposition format."""
    summary = await summarize_model_metrics(days=days)
    lines = [
        "# HELP llm_gateway_requests_total Chat completion requests by model",
        "# TYPE llm_gateway_requests_total counter",
        "# HELP llm_gateway_errors_total Failed chat completion requests by model",
        "# TYPE llm_gateway_errors_total counter",
        "# HELP llm_gateway_fallbacks_total Requests that succeeded via fallback",
        "# TYPE llm_gateway_fallbacks_total counter",
        "# HELP llm_gateway_tokens_total Tokens consumed by model",
        "# TYPE llm_gateway_tokens_total counter",
        "# HELP llm_gateway_latency_ms_avg Average request latency in milliseconds",
        "# TYPE llm_gateway_latency_ms_avg gauge",
    ]
    for row in summary["models"]:
        mid = row["model_id"].replace("\\", "\\\\").replace('"', '\\"')
        labels = f'model="{mid}"'
        lines.append(f'llm_gateway_requests_total{{{labels}}} {row["requests"]}')
        lines.append(f'llm_gateway_errors_total{{{labels}}} {row["errors"]}')
        lines.append(f'llm_gateway_fallbacks_total{{{labels}}} {row["fallbacks"]}')
        lines.append(f'llm_gateway_tokens_total{{{labels}}} {row["total_tokens"]}')
        lines.append(f'llm_gateway_latency_ms_avg{{{labels}}} {row["avg_latency_ms"]}')
    lines.append("")
    return "\n".join(lines)


async def aclose() -> None:
    global _redis
    if _redis is not None:
        try:
            await _redis.aclose()
        except Exception:
            pass
        _redis = None
