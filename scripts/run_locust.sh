#!/usr/bin/env bash
# Run standard 20-user / 5-minute Locust profile against the gateway.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -z "${LOCUST_API_KEY:-}" ]]; then
  echo "ERROR: export LOCUST_API_KEY=your-key first" >&2
  exit 1
fi

HOST="${LOCUST_HOST:-http://127.0.0.1:8001}"
USERS="${LOCUST_USERS:-20}"
SPAWN_RATE="${LOCUST_SPAWN_RATE:-4}"
RUN_TIME="${LOCUST_RUN_TIME:-5m}"
REPORT="${LOCUST_HTML:-locust_report.html}"

source venv/bin/activate
exec locust -f locustfile.py \
  --host "$HOST" \
  --users "$USERS" \
  --spawn-rate "$SPAWN_RATE" \
  --run-time "$RUN_TIME" \
  --headless \
  --html "$REPORT"
