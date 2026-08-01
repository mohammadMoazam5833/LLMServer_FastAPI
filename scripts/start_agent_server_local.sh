#!/usr/bin/env bash
# Start agent-server from uv cache when uvx cannot reach PyPI (offline / DNS issues).
# Called automatically by run_agent_canvas.sh if agent-server is not listening.
set -euo pipefail

OH_CANVAS_SAFE_STATE_DIR="${OH_CANVAS_SAFE_STATE_DIR:-${HOME}/.agent-canvas}"
OH_CANVAS_SAFE_BACKEND_PORT="${OH_CANVAS_SAFE_BACKEND_PORT:-18000}"
OH_SECRET_KEY_FILE="${OH_SECRET_KEY_FILE:-${HOME}/.openhands/agent-canvas/secret-key.txt}"
LOCAL_BACKEND_API_KEY_FILE="${LOCAL_BACKEND_API_KEY_FILE:-${HOME}/.openhands/agent-canvas/api-key.txt}"
UV_CACHE_DIR="${UV_CACHE_DIR:-${HOME}/.local/share/uv/cache}"
CANVAS_TOOLS="${CANVAS_TOOLS:-$(npm root -g 2>/dev/null)/@openhands/agent-canvas/tools}"

if ss -tln 2>/dev/null | grep -q ":${OH_CANVAS_SAFE_BACKEND_PORT} "; then
  echo "agent-server already listening on :${OH_CANVAS_SAFE_BACKEND_PORT}"
  exit 0
fi

AGENT_BIN="$(find "${UV_CACHE_DIR}/archive-v0" -path '*/bin/agent-server' -type f 2>/dev/null | head -1)"
if [[ -z "${AGENT_BIN}" || ! -x "${AGENT_BIN}" ]]; then
  echo "ERROR: No cached agent-server found under ${UV_CACHE_DIR}" >&2
  exit 1
fi

if [[ -z "${OH_SECRET_KEY:-}" && -f "${OH_SECRET_KEY_FILE}" ]]; then
  OH_SECRET_KEY="$(tr -d '\n\r' < "${OH_SECRET_KEY_FILE}")"
fi
if [[ -z "${OH_SECRET_KEY:-}" ]]; then
  echo "ERROR: OH_SECRET_KEY not set and ${OH_SECRET_KEY_FILE} missing" >&2
  exit 1
fi
export OH_SECRET_KEY

if [[ -z "${OH_SESSION_API_KEYS_0:-}" && -f "${LOCAL_BACKEND_API_KEY_FILE}" ]]; then
  OH_SESSION_API_KEYS_0="$(tr -d '\n\r' < "${LOCAL_BACKEND_API_KEY_FILE}")"
fi
export OH_SESSION_API_KEYS_0
export OPENHANDS_AUTOMATION_API_KEY="${OH_SESSION_API_KEYS_0}"
export OH_PERSISTENCE_DIR="${HOME}/.openhands"
export OH_CONVERSATIONS_PATH="${OH_CANVAS_SAFE_STATE_DIR}/dev_conversations"
export OH_BASH_EVENTS_DIR="${OH_CANVAS_SAFE_STATE_DIR}/bash_events"
export OH_BASH_EVENTS_RETENTION_SECONDS="${OH_BASH_EVENTS_RETENTION_SECONDS:-7200}"
export OH_WORKSPACE_PATH="${OH_WORKSPACE_PATH:-/home/moazemi-gc/LLM_SERVER}"
export TMUX_TMPDIR="${OH_CANVAS_SAFE_STATE_DIR}/tmux"
export PYTHONUTF8=1
export LOG_JSON=true
export OPENHANDS_SUPPRESS_BANNER=1
export AGENT_SERVER_URL="http://127.0.0.1:${OH_CANVAS_SAFE_BACKEND_PORT}"

mkdir -p "${OH_CANVAS_SAFE_STATE_DIR}/workspaces" "${TMUX_TMPDIR}"

echo "==> Starting cached agent-server: ${AGENT_BIN}"
cd "${OH_CANVAS_SAFE_STATE_DIR}/workspaces"
exec "${AGENT_BIN}" \
  --host 127.0.0.1 \
  --port "${OH_CANVAS_SAFE_BACKEND_PORT}" \
  --extra-python-path "${CANVAS_TOOLS}"
