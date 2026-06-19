# Load Testing Guide

Guide for Locust-based load testing of the OpenAI-compatible gateway (`/v1/chat/completions`).

## Before you run

### 1. Pre-flight checklist

```bash
# Gateway health
curl -s http://127.0.0.1:8001/health | jq .

# Models available
export LOCUST_API_KEY=your-api-key
curl -s -H "X-API-Key: $LOCUST_API_KEY" http://127.0.0.1:8001/v1/models | jq .

# Single chat smoke test
curl -s -H "X-API-Key: $LOCUST_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"qwen3-coder-30b-a3b-instruct","messages":[{"role":"user","content":"hi"}],"max_tokens":20}' \
  http://127.0.0.1:8001/v1/chat/completions | jq .
```

### 2. Rate limit (critical)

Default API keys have `rate_limit_per_minute = 60`. Twenty Locust users sharing **one key** will exceed this immediately and produce **429** errors (median ~8ms, no real LLM load).

**Option A — disable per-key limit in DB (recommended for dedicated test keys):**

```bash
python scripts/set_load_test_rate_limit.py --limit 0
# or only one key:
python scripts/set_load_test_rate_limit.py --limit 0 --name openwebui
```

**Option B — gateway env flag (dev only):**

```bash
LOAD_TEST_DISABLE_RATE_LIMIT=true uvicorn app.main:app --host 0.0.0.0 --port 8001
```

### 3. Locust environment

| Variable | Required | Description |
|----------|----------|-------------|
| `LOCUST_API_KEY` | yes | Raw API key (`X-API-Key`) |
| `LOCUST_MODEL` | no | Model id; auto-fetched from `/v1/models` if unset |

---

## Running Locust

### Profile: 15–20 concurrent users (target)

```bash
export LOCUST_API_KEY=sk-your-key

locust -f locustfile.py --host http://127.0.0.1:8001 \
  --users 20 \
  --spawn-rate 4 \
  --run-time 5m \
  --headless \
  --html locust_report.html
```

`locustfile.py` settings:

- `wait_time = between(3, 10)` — realistic think time between turns
- `max_tokens = 50` — short answers for throughput measurement
- **non-stream only** — avoids stream client noise in baseline tests
- model auto-resolved from `/v1/models`

### Distributed workers (optional)

```bash
# master
locust -f locustfile.py --master --host http://127.0.0.1:8001

# workers (e.g. 8 processes)
locust -f locustfile.py --worker --master-host=127.0.0.1
```

Workers only distribute virtual users across Locust processes. They do **not** add capacity to the gateway or vLLM.

---

## Interpreting results

| Signal | Meaning |
|--------|---------|
| Median ~8ms + many **429** | Rate limit hit; requests never reached vLLM |
| **404** on chat | Wrong `model` id (e.g. `gpt-4` not in DB) |
| Median 100–500ms, 0% fail | Healthy short-response load (low `max_tokens`) |
| p95 > 30s, timeouts | vLLM queue or GPU saturation — tune vLLM or reduce concurrency |
| `Stream ended prematurely` | Stream under pressure; use non-stream for baseline |

### Baseline comparison (this repo)

| Run | Users | Fail rate | Chat median | Notes |
|-----|-------|-----------|-------------|-------|
| Broken (2026-06-19) | 20 | **97.3%** | 8ms | 654×429, 73×404 (`gpt-4`), 0 chat success |
| Fixed (2026-06-19) | 20 | **0%** | 180ms | 815 chat OK, p95 290ms, rate limit disabled |

---

## Gateway tuning (15–20 concurrent)

| Component | Recommendation |
|-----------|----------------|
| Uvicorn | `uvicorn app.main:app --workers 2-4 --host 0.0.0.0 --port 8001` (no `--reload` during tests) |
| DB pool | `pool_size=20`, `max_overflow=30` in [`app/database.py`](../app/database.py) |
| httpx → vLLM | `max_connections=50` in [`app/runtime/vllm_http_generator.py`](../app/runtime/vllm_http_generator.py) |
| Production rate limit | Per-key 120–300 req/min, not 60, if many users share patterns |

---

## vLLM tuning (real LLM bottleneck)

For **longer responses** (`max_tokens` 512–4096) or true 15–20 in-flight generations:

```bash
# Example vLLM serve flags (adjust to your GPU VRAM)
vllm serve /path/to/Qwen3-Coder-30B-A3B-Instruct \
  --port 8003 \
  --max-num-seqs 16 \
  --gpu-memory-utilization 0.90
```

| Parameter | Effect |
|-----------|--------|
| `max-num-seqs` | Max concurrent sequences; raise for more parallelism (uses more VRAM) |
| `gpu-memory-utilization` | Fraction of GPU memory vLLM may use |
| Lower `max_tokens` in Locust | Reduces per-request GPU time |

If p95 latency grows above your SLA under 20 users with realistic `max_tokens`, increase `max-num-seqs` cautiously or add a second vLLM replica behind a load balancer.

---

## Files

| File | Purpose |
|------|---------|
| [`locustfile.py`](../locustfile.py) | Locust scenarios |
| [`scripts/set_load_test_rate_limit.py`](../scripts/set_load_test_rate_limit.py) | DB helper for rate limits |
| `locust_report_fixed.html` | Example successful 5m / 20-user report |

---

## Security note

Never commit API keys in `locustfile.py`. Use `LOCUST_API_KEY` environment variable only.
