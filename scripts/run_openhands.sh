#!/usr/bin/env bash
# OpenHands stable setup: host network + MCP + sandbox (team/LAN ready).
#
# Usage:
#   ./scripts/run_openhands.sh
#   OPENHANDS_WORKSPACE=/path/to/project ./scripts/run_openhands.sh
#
# UI:  http://${OPENHANDS_HOST}:3001
# LLM: http://${OPENHANDS_HOST}:8001/code_bot/v1
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

OPENHANDS_HOST="${OPENHANDS_HOST:-127.0.0.1}"
OPENHANDS_PORT="${OPENHANDS_PORT:-3001}"
GATEWAY_PORT="${GATEWAY_PORT:-8001}"
# پوشهٔ host که agent باید ببیند
OPENHANDS_WORKSPACE="${OPENHANDS_WORKSPACE:-/home/moazemi-gc/LLM_SERVER}"
# OpenHands به‌طور پیش‌فرض /workspace/project را باز می‌کند
SANDBOX_MOUNT="${SANDBOX_MOUNT:-/workspace/project}"

_host_uid="$(id -u)"
SANDBOX_USER_ID="${SANDBOX_USER_ID:-${_host_uid}}"
if [[ "${SANDBOX_USER_ID}" == "0" ]]; then
  echo "WARN: SANDBOX_USER_ID=0 breaks workspace write access; using uid ${_host_uid}" >&2
  SANDBOX_USER_ID="${_host_uid}"
fi
IMAGE_APP="${OPENHANDS_IMAGE:-docker.openhands.dev/openhands/openhands:1.8}"
IMAGE_AGENT="${OPENHANDS_AGENT_IMAGE:-ghcr.io/openhands/agent-server:1.27.0-python}"

echo "==> OpenHands stable start"
echo "    HOST=${OPENHANDS_HOST}  UI_PORT=${OPENHANDS_PORT}  GATEWAY=${GATEWAY_PORT}"
echo "    WORKSPACE=${OPENHANDS_WORKSPACE} -> ${SANDBOX_MOUNT} (rw)"
echo "    SANDBOX_USER_ID=${SANDBOX_USER_ID}"

if [[ ! -d "${OPENHANDS_WORKSPACE}" ]]; then
  echo "ERROR: Workspace not found: ${OPENHANDS_WORKSPACE}" >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker daemon not running or no permission." >&2
  exit 1
fi

if ! curl -sf "http://127.0.0.1:${GATEWAY_PORT}/health" >/dev/null 2>&1; then
  echo "WARN: Gateway not healthy on :${GATEWAY_PORT} — start llm_fastapi first." >&2
fi

if ss -tln 2>/dev/null | grep -q ":${OPENHANDS_PORT} "; then
  echo "WARN: Port ${OPENHANDS_PORT} already in use — will replace openhands-app." >&2
fi

if ! grep -q 'host.docker.internal' /etc/hosts 2>/dev/null; then
  echo "TIP: For webhooks with VPN, run once:"
  echo "  echo '127.0.0.1 host.docker.internal' | sudo tee -a /etc/hosts"
fi

docker pull "${IMAGE_AGENT}" >/dev/null 2>&1 || true
docker pull "${IMAGE_APP}" >/dev/null 2>&1 || true

# sandboxهای قدیمی با host network پورت 8000 را نگه می‌دارند → 401 بعد از restart
stale="$(docker ps -aq --filter name=oh-agent-server 2>/dev/null || true)"
if [[ -n "${stale}" ]]; then
  echo "==> Removing stale sandboxes (free port 8000)"
  docker rm -f ${stale} >/dev/null 2>&1 || true
fi

docker rm -f openhands-app 2>/dev/null || true

docker run -d \
  --name openhands-app \
  --network host \
  --restart unless-stopped \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "${HOME}/.openhands:/.openhands" \
  -e MCP_ENABLED=true \
  -e DOCKER_HOST_ADDR=127.0.0.1 \
  -e OH_WEB_URL="http://${OPENHANDS_HOST}:${OPENHANDS_PORT}" \
  -e SANDBOX_CONTAINER_URL_PATTERN="http://${OPENHANDS_HOST}:{port}" \
  -e SANDBOX_RUNTIME_CONTAINER_IMAGE="${IMAGE_AGENT}" \
  -e SANDBOX_HOST_PORT="${OPENHANDS_PORT}" \
  -e AGENT_SERVER_USE_HOST_NETWORK=true \
  -e SANDBOX_USER_ID="${SANDBOX_USER_ID}" \
  -e SANDBOX_VOLUMES="${OPENHANDS_WORKSPACE}:${SANDBOX_MOUNT}:rw" \
  --entrypoint /app/.venv/bin/uvicorn \
  "${IMAGE_APP}" \
  openhands.server.listen:app --host 0.0.0.0 --port "${OPENHANDS_PORT}"

ready=false
for _ in $(seq 1 20); do
  if curl -sf "http://127.0.0.1:${OPENHANDS_PORT}/" >/dev/null; then
    ready=true
    break
  fi
  sleep 2
done

if [[ "${ready}" == "true" ]]; then
  echo ""
  echo "OK  OpenHands UI:  http://${OPENHANDS_HOST}:${OPENHANDS_PORT}"
  echo "    Code bot LLM:  http://${OPENHANDS_HOST}:${GATEWAY_PORT}/code_bot/v1"
  echo "    Agent cwd:     ${SANDBOX_MOUNT}"
  echo ""
  echo "LLM in UI (Advanced):"
  echo "  Custom Model: openai//home/moazemi-gc/extra_space/models/Qwen3-Coder-30B-A3B-Instruct"
  echo "  Base URL:     http://${OPENHANDS_HOST}:${GATEWAY_PORT}/code_bot/v1"
else
  echo "ERROR: OpenHands did not respond on port ${OPENHANDS_PORT}" >&2
  docker logs openhands-app --tail 30
  exit 1
fi
