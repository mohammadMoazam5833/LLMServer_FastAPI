#!/usr/bin/env bash
# Stop legacy OpenHands Docker stack (UI + oh-agent-server sandboxes).
# Agent Canvas on :8002 / :18000 is unaffected.
#
# Usage: ./scripts/stop_openhands.sh
set -euo pipefail

echo "==> Stopping OpenHands Docker stack"

if docker ps -a --format '{{.Names}}' | grep -qx 'openhands-app'; then
  docker stop openhands-app 2>/dev/null || true
  echo "    stopped openhands-app"
else
  echo "    openhands-app not running"
fi

while IFS= read -r name; do
  [[ -z "${name}" ]] && continue
  docker rm -f "${name}" 2>/dev/null || true
  echo "    removed ${name}"
done < <(docker ps -a --format '{{.Names}}' | grep -E '^oh-agent-server' || true)

echo "==> Done. Ports 3001 and 8000 should be free."
echo "    Agent Canvas: http://127.0.0.1:8002"
