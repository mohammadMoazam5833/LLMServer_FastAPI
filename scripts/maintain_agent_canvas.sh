#!/usr/bin/env bash
# Agent Canvas state maintenance — safe to run on start or from cron.
#
# Usage:
#   ./scripts/maintain_agent_canvas.sh
#   AGENT_CANVAS_MAX_BASH_EVENTS=1000 ./scripts/maintain_agent_canvas.sh
set -euo pipefail

OH_CANVAS_SAFE_STATE_DIR="${OH_CANVAS_SAFE_STATE_DIR:-${HOME}/.agent-canvas}"
BASH_EVENTS_DIR="${OH_CANVAS_SAFE_STATE_DIR}/bash_events"
LOGS_DIR="${OH_CANVAS_SAFE_STATE_DIR}/logs"
MAX_BASH_EVENTS="${AGENT_CANVAS_MAX_BASH_EVENTS:-1500}"
BASH_EVENTS_MAX_AGE_MINUTES="${AGENT_CANVAS_BASH_EVENTS_MAX_AGE_MINUTES:-360}"
LOG_MAX_BYTES="${AGENT_CANVAS_LOG_MAX_BYTES:-20971520}" # 20 MiB

prune_bash_events() {
  [[ -d "${BASH_EVENTS_DIR}" ]] || return 0

  local before after removed
  before="$(find "${BASH_EVENTS_DIR}" -type f 2>/dev/null | wc -l | tr -d ' ')"
  [[ "${before}" -eq 0 ]] && return 0

  find "${BASH_EVENTS_DIR}" -type f -mmin "+${BASH_EVENTS_MAX_AGE_MINUTES}" -delete 2>/dev/null || true

  after="$(find "${BASH_EVENTS_DIR}" -type f 2>/dev/null | wc -l | tr -d ' ')"
  if [[ "${after}" -gt "${MAX_BASH_EVENTS}" ]]; then
    find "${BASH_EVENTS_DIR}" -type f -printf '%T@ %p\n' 2>/dev/null \
      | sort -n | head -n -"${MAX_BASH_EVENTS}" | cut -d' ' -f2- \
      | xargs -r rm -f 2>/dev/null || true
    after="$(find "${BASH_EVENTS_DIR}" -type f 2>/dev/null | wc -l | tr -d ' ')"
  fi

  removed=$((before - after))
  if [[ "${removed}" -gt 0 ]]; then
    echo "==> Pruned ${removed} bash_events (${before} → ${after})"
  fi
}

rotate_logs() {
  [[ -d "${LOGS_DIR}" ]] || return 0

  local log size
  while IFS= read -r -d '' log; do
    size="$(stat -c '%s' "${log}" 2>/dev/null || echo 0)"
    if [[ "${size}" -gt "${LOG_MAX_BYTES}" ]]; then
      tail -c "${LOG_MAX_BYTES}" "${log}" > "${log}.tmp" && mv "${log}.tmp" "${log}"
      echo "==> Truncated log $(basename "${log}") (${size} → ${LOG_MAX_BYTES} bytes)"
    fi
  done < <(find "${LOGS_DIR}" -maxdepth 1 -type f -name '*.log' -print0 2>/dev/null)

  find "${LOGS_DIR}" -maxdepth 1 -type f -name '*.log' -mtime +14 -delete 2>/dev/null || true
}

prune_bash_events
rotate_logs

# Re-apply .gitignore defaults for all tracked workspace paths (cron-safe).
WORKSPACES_CONFIG="${HOME}/.config/llm_fastapi/agent_canvas_workspaces.txt"
if [[ -f "${WORKSPACES_CONFIG}" ]]; then
  mapfile -t _canvas_workspaces < <(grep -v '^[[:space:]]*#' "${WORKSPACES_CONFIG}" | grep -v '^[[:space:]]*$' || true)
  if [[ "${#_canvas_workspaces[@]}" -gt 0 ]]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    bash "${SCRIPT_DIR}/ensure_workspace_gitignore.sh" "${_canvas_workspaces[@]}" 2>/dev/null || true
  fi
fi
