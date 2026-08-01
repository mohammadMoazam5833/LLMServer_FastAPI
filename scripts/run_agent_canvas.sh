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
OH_SECRET_KEY_FILE="${OH_SECRET_KEY_FILE:-${HOME}/.openhands/agent-canvas/secret-key.txt}"
LOCAL_BACKEND_API_KEY_FILE="${LOCAL_BACKEND_API_KEY_FILE:-${HOME}/.openhands/agent-canvas/api-key.txt}"

CODE_BOT_MODEL="${CODE_BOT_MODEL:-openai/qwen3-coder-30b}"
CODE_BOT_BASE_URL="${CODE_BOT_BASE_URL:-http://${CANVAS_HOST}:${GATEWAY_PORT}/code_bot/v1}"
CODE_BOT_API_KEY_FILE="${CODE_BOT_API_KEY_FILE:-${HOME}/.config/llm_fastapi/code_bot_api_key}"

if [[ -z "${CODE_BOT_API_KEY:-}" && -f "${CODE_BOT_API_KEY_FILE}" ]]; then
  CODE_BOT_API_KEY="$(tr -d '\n\r' < "${CODE_BOT_API_KEY_FILE}")"
fi
if [[ -n "${CODE_BOT_API_KEY:-}" ]]; then
  export CODE_BOT_API_KEY
  export OPENAI_API_KEY="${CODE_BOT_API_KEY}"
fi

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

# agent-server needs OH_SECRET_KEY to encrypt/decrypt API keys and MCP secrets.
# agent-canvas normally reads ~/.openhands/agent-canvas/secret-key.txt, but if
# agent-server is started outside that spawn chain (e.g. orphan uvx after DNS
# failure) it runs without the key and conversations fail with HTTP 503.
if [[ -z "${OH_SECRET_KEY:-}" && -f "${OH_SECRET_KEY_FILE}" ]]; then
  OH_SECRET_KEY="$(tr -d '\n\r' < "${OH_SECRET_KEY_FILE}")"
fi
if [[ -z "${OH_SECRET_KEY:-}" ]]; then
  OH_SECRET_KEY="$(openssl rand -hex 32)"
  printf '%s\n' "${OH_SECRET_KEY}" > "${OH_SECRET_KEY_FILE}"
  chmod 600 "${OH_SECRET_KEY_FILE}"
  echo "==> Created ${OH_SECRET_KEY_FILE}"
fi
export OH_SECRET_KEY

if [[ -z "${LOCAL_BACKEND_API_KEY:-}" && -f "${LOCAL_BACKEND_API_KEY_FILE}" ]]; then
  LOCAL_BACKEND_API_KEY="$(tr -d '\n\r' < "${LOCAL_BACKEND_API_KEY_FILE}")"
fi
if [[ -n "${LOCAL_BACKEND_API_KEY:-}" ]]; then
  export LOCAL_BACKEND_API_KEY
fi

if ! curl -sf "http://127.0.0.1:${GATEWAY_PORT}/health" >/dev/null 2>&1; then
  echo "WARN: Gateway not healthy on :${GATEWAY_PORT} — start llm_fastapi first." >&2
fi

if ss -tln 2>/dev/null | grep -q ":${CANVAS_PORT} "; then
  echo "WARN: Port ${CANVAS_PORT} already in use." >&2
fi

mkdir -p "${OH_CANVAS_SAFE_STATE_DIR}"
export OH_CANVAS_SAFE_STATE_DIR

# agent-server auto-purges bash event files when retention is set (background loop).
# UI polls bash websocket ~every 10s → thousands of small files without this.
export OH_BASH_EVENTS_RETENTION_SECONDS="${OH_BASH_EVENTS_RETENTION_SECONDS:-7200}"
export OH_WORKSPACE_PATH="${OH_WORKSPACE_PATH:-${AGENT_CANVAS_WORKSPACE}}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "${SCRIPT_DIR}/maintain_agent_canvas.sh" || true

# Auto .gitignore for default workspace + any saved workspace paths.
WORKSPACES_CONFIG="${HOME}/.config/llm_fastapi/agent_canvas_workspaces.txt"
mkdir -p "$(dirname "${WORKSPACES_CONFIG}")"
touch "${WORKSPACES_CONFIG}"
if ! grep -qxF "${AGENT_CANVAS_WORKSPACE}" "${WORKSPACES_CONFIG}" 2>/dev/null; then
  echo "${AGENT_CANVAS_WORKSPACE}" >> "${WORKSPACES_CONFIG}"
fi
mapfile -t _canvas_workspaces < <(grep -v '^[[:space:]]*#' "${WORKSPACES_CONFIG}" | grep -v '^[[:space:]]*$' || true)
if [[ "${#_canvas_workspaces[@]}" -gt 0 ]]; then
  bash "${SCRIPT_DIR}/ensure_workspace_gitignore.sh" "${_canvas_workspaces[@]}" || true
fi

if [[ -n "${CODE_BOT_API_KEY:-}" ]]; then
  bash "${SCRIPT_DIR}/sync_agent_canvas_llm_key.sh" || true
fi

# پورت‌های داخلی — جلوگیری از تداخل با OpenHands (3001) و agent-server (8000)
export OH_CANVAS_SAFE_VITE_PORT="${OH_CANVAS_SAFE_VITE_PORT:-3010}"
export OH_CANVAS_SAFE_BACKEND_PORT="${OH_CANVAS_SAFE_BACKEND_PORT:-18000}"
export OH_CANVAS_SAFE_AUTOMATION_PORT="${OH_CANVAS_SAFE_AUTOMATION_PORT:-18001}"

echo ""
echo "After UI opens:"
echo "  1. Open Workspace → ${AGENT_CANVAS_WORKSPACE}"
echo "  2. Settings → LLM:"
echo "       Base URL: ${CODE_BOT_BASE_URL}"
echo "       API Key:  sk-... (or set ${CODE_BOT_API_KEY_FILE})"
echo "       Model:    ${CODE_BOT_MODEL}"
echo ""

# Persistent uv cache/tools (avoid sandbox /tmp eviction on each start)
export UV_CACHE_DIR="${UV_CACHE_DIR:-${HOME}/.local/share/uv/cache}"
export UV_TOOL_DIR="${UV_TOOL_DIR:-${HOME}/.local/share/uv/tools}"
mkdir -p "${UV_CACHE_DIR}" "${UV_TOOL_DIR}"

AGENT_SERVER_VERSION="${OH_AGENT_SERVER_VERSION:-1.29.0}"
export OH_AGENT_SERVER_VERSION="${AGENT_SERVER_VERSION}"

# Use offline uvx when a cached agent-server exists (avoids PyPI DNS failures after reboot).
if find "${UV_CACHE_DIR}/archive-v0" -path '*/bin/agent-server' -type f 2>/dev/null | grep -q .; then
  export UV_OFFLINE=1
  echo "==> Cached agent-server found — UV_OFFLINE=1"
fi

if command -v uv >/dev/null 2>&1; then
  if uv tool list 2>/dev/null | grep -q 'openhands-agent-server'; then
    echo "==> agent-server already installed (uv tools)."
    export UV_OFFLINE=1
  elif [[ "${UV_OFFLINE:-}" != "1" ]]; then
    echo "==> Pre-warming agent-server via uv (first run may take 1–2 min)..."
    if uv tool install "openhands-agent-server==${AGENT_SERVER_VERSION}" \
      --with "openhands-sdk==${AGENT_SERVER_VERSION}" \
      --with "openhands-tools==${AGENT_SERVER_VERSION}" \
      --with "openhands-workspace==${AGENT_SERVER_VERSION}"; then
      export UV_OFFLINE=1
    else
      echo "WARN: agent-server pre-warm failed; will try cached uvx offline." >&2
    fi
  fi
else
  echo "WARN: uv not found; agent-server installs on first use (slower startup)." >&2
fi

# Orphan agent-server (started without OH_SECRET_KEY) blocks a healthy restart.
if command -v ss >/dev/null 2>&1 && ss -tln 2>/dev/null | grep -q ":${OH_CANVAS_SAFE_BACKEND_PORT:-18000} "; then
  echo "WARN: Port ${OH_CANVAS_SAFE_BACKEND_PORT:-18000} in use — stop old agent-canvas/agent-server first." >&2
  echo "      pkill -f 'agent-canvas --port ${CANVAS_PORT}' ; pkill -f 'agent-server --host 127.0.0.1 --port ${OH_CANVAS_SAFE_BACKEND_PORT:-18000}'" >&2
fi

echo ""
echo "Note: First agent action may wait while agent-server starts on :${OH_CANVAS_SAFE_BACKEND_PORT}."
echo ""

# If agent-canvas uvx spawn fails (offline DNS), bootstrap from uv cache in background.
(
  sleep 90
  if ! curl -sf "http://127.0.0.1:${OH_CANVAS_SAFE_BACKEND_PORT}/health" >/dev/null 2>&1; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    nohup bash "${SCRIPT_DIR}/start_agent_server_local.sh" \
      >> "${OH_CANVAS_SAFE_STATE_DIR}/logs/agent-server-bootstrap.log" 2>&1 &
  fi
) &

cd "${AGENT_CANVAS_WORKSPACE}"
exec agent-canvas --port "${CANVAS_PORT}"
