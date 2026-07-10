#!/usr/bin/env bash
# Agent Canvas — local backend (no Docker sandbox), Cursor-like workspace access.
#
# Usage:
#   ./scripts/run_agent_canvas.sh
#   AGENT_CANVAS_WORKSPACE=/path/to/project ./scripts/run_agent_canvas.sh
#
# UI:  http://${CANVAS_HOST}:${CANVAS_PORT}
# LLM: http://${CANVAS_HOST}:${GATEWAY_PORT}/code_bot/v1
set -euo pipefail

CANVAS_HOST="${CANVAS_HOST:-127.0.0.1}"
CANVAS_PORT="${CANVAS_PORT:-8002}"
GATEWAY_PORT="${GATEWAY_PORT:-8001}"
AGENT_CANVAS_WORKSPACE="${AGENT_CANVAS_WORKSPACE:-/home/moazemi-gc/LLM_SERVER}"
# ~/.openhands ممکن است root-owned باشد (از Docker) — state جدا
OH_CANVAS_SAFE_STATE_DIR="${OH_CANVAS_SAFE_STATE_DIR:-${HOME}/.agent-canvas}"

CODE_BOT_MODEL="${CODE_BOT_MODEL:-openai//home/moazemi-gc/extra_space/models/Qwen3-Coder-30B-A3B-Instruct}"
CODE_BOT_BASE_URL="${CODE_BOT_BASE_URL:-http://${CANVAS_HOST}:${GATEWAY_PORT}/code_bot/v1}"

echo "==> Agent Canvas (local, no sandbox)"
echo "    UI:        http://${CANVAS_HOST}:${CANVAS_PORT}"
echo "    Workspace: ${AGENT_CANVAS_WORKSPACE}"
echo "    Code bot:  ${CODE_BOT_BASE_URL}"
echo "    State dir: ${OH_CANVAS_SAFE_STATE_DIR}"

if [[ ! -d "${AGENT_CANVAS_WORKSPACE}" ]]; then
  echo "ERROR: Workspace not found: ${AGENT_CANVAS_WORKSPACE}" >&2
  exit 1
fi

if ! command -v node >/dev/null 2>&1; then
  echo "ERROR: Node.js not found (need 22+)." >&2
  exit 1
fi

node_major="$(node --version | sed 's/^v//' | cut -d. -f1)"
if [[ "${node_major}" -lt 22 ]]; then
  echo "ERROR: Node.js 22+ required (found $(node --version))." >&2
  exit 1
fi

if ! command -v agent-canvas >/dev/null 2>&1; then
  echo "==> Installing @openhands/agent-canvas globally..."
  npm install -g @openhands/agent-canvas
fi

fix_openhands_permissions() {
  local oh="${HOME}/.openhands"
  [[ -d "${oh}" ]] || return 0
  [[ -w "${oh}" ]] && return 0

  echo "==> Fixing ~/.openhands ownership (was root from Docker OpenHands)..."
  if docker info >/dev/null 2>&1; then
    docker run --rm -v "${oh}:/data" alpine chown -R "$(id -u):$(id -g)" /data
  else
    echo "ERROR: ~/.openhands not writable. Run:" >&2
    echo "  sudo chown -R \$(id -un):\$(id -gn) ~/.openhands" >&2
    exit 1
  fi
}

fix_openhands_permissions
mkdir -p "${HOME}/.openhands/profiles" "${HOME}/.openhands/auth" "${HOME}/.openhands/agent-canvas"

if ! curl -sf "http://127.0.0.1:${GATEWAY_PORT}/health" >/dev/null 2>&1; then
  echo "WARN: Gateway not healthy on :${GATEWAY_PORT} — start llm_fastapi first." >&2
fi

if ss -tln 2>/dev/null | grep -q ":${CANVAS_PORT} "; then
  echo "WARN: Port ${CANVAS_PORT} already in use." >&2
fi

mkdir -p "${OH_CANVAS_SAFE_STATE_DIR}"
export OH_CANVAS_SAFE_STATE_DIR

# پورت‌های داخلی — جلوگیری از تداخل با OpenHands (3001) و agent-server (8000)
export OH_CANVAS_SAFE_VITE_PORT="${OH_CANVAS_SAFE_VITE_PORT:-3010}"
export OH_CANVAS_SAFE_BACKEND_PORT="${OH_CANVAS_SAFE_BACKEND_PORT:-18000}"
export OH_CANVAS_SAFE_AUTOMATION_PORT="${OH_CANVAS_SAFE_AUTOMATION_PORT:-18001}"

echo ""
echo "After UI opens:"
echo "  1. Open Workspace → ${AGENT_CANVAS_WORKSPACE}"
echo "  2. Settings → LLM:"
echo "       Base URL: ${CODE_BOT_BASE_URL}"
echo "       Model:    ${CODE_BOT_MODEL}"
echo ""

cd "${AGENT_CANVAS_WORKSPACE}"
exec agent-canvas --port "${CANVAS_PORT}"
