#!/usr/bin/env bash
# Sync gateway API key into Agent Canvas / agent-server settings + open conversations.
#
# Usage:
#   CODE_BOT_API_KEY='sk-...' ./scripts/sync_agent_canvas_llm_key.sh
#   # or store once:
#   mkdir -p ~/.config/llm_fastapi
#   echo 'sk-...' > ~/.config/llm_fastapi/code_bot_api_key
#   chmod 600 ~/.config/llm_fastapi/code_bot_api_key
#   ./scripts/sync_agent_canvas_llm_key.sh
set -euo pipefail

KEY_FILE="${CODE_BOT_API_KEY_FILE:-${HOME}/.config/llm_fastapi/code_bot_api_key}"
SETTINGS="${HOME}/.openhands/settings.json"
STATE_DIR="${OH_CANVAS_SAFE_STATE_DIR:-${HOME}/.agent-canvas}"

if [[ -z "${CODE_BOT_API_KEY:-}" && -f "${KEY_FILE}" ]]; then
  CODE_BOT_API_KEY="$(tr -d '\n\r' < "${KEY_FILE}")"
fi

if [[ -z "${CODE_BOT_API_KEY:-}" ]]; then
  echo "ERROR: Set CODE_BOT_API_KEY or create ${KEY_FILE}" >&2
  exit 1
fi

python3 - "${CODE_BOT_API_KEY}" "${SETTINGS}" "${STATE_DIR}" <<'PY'
import json
import sys
from pathlib import Path

api_key, settings_path, state_dir = sys.argv[1:4]
settings_path = Path(settings_path)
state_dir = Path(state_dir)

def patch_llm(llm: dict) -> bool:
    if not isinstance(llm, dict):
        return False
    if llm.get("api_key") == api_key:
        return False
    llm["api_key"] = api_key
    llm.setdefault("auth_type", "api_key")
    return True

changed = 0

if settings_path.is_file():
    data = json.loads(settings_path.read_text())
    agent = data.setdefault("agent_settings", {})
    if patch_llm(agent.setdefault("llm", {})):
        changed += 1
    profiles = agent.get("llm_profiles", {}).get("profiles", {})
    if isinstance(profiles, dict):
        for prof in profiles.values():
            if isinstance(prof, dict) and patch_llm(prof):
                changed += 1
    settings_path.write_text(json.dumps(data, ensure_ascii=False))
    print(f"updated {settings_path}")

for base in state_dir.glob("dev_conversations/*/base_state.json"):
    data = json.loads(base.read_text())
    llm = data.get("agent", {}).get("llm", {})
    if patch_llm(llm):
        base.write_text(json.dumps(data, ensure_ascii=False))
        print(f"updated {base}")
        changed += 1

if changed == 0:
    print("LLM api_key already in sync")
else:
    print(f"synced api_key in {changed} place(s)")
PY
