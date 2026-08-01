#!/usr/bin/env bash
# One-time (per machine) global gitignore for Agent Canvas / dev workspaces.
# Covers ALL git repos — node_modules etc. ignored even without per-repo .gitignore.
#
# Usage: ./scripts/setup_agent_canvas_global_gitignore.sh
set -euo pipefail

GLOBAL_IGNORE="${AGENT_CANVAS_GLOBAL_GITIGNORE:-${HOME}/.config/llm_fastapi/gitignore_global}"
mkdir -p "$(dirname "${GLOBAL_IGNORE}")"

if [[ ! -f "${GLOBAL_IGNORE}" ]]; then
  cat > "${GLOBAL_IGNORE}" <<'EOF'
# Global gitignore for Agent Canvas / local dev (llm_fastapi)
node_modules/
dist/
build/
.vite/
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/
.ruff_cache/
*.log
.DS_Store
.env
.env.*
!.env.example
coverage/
.venv/
venv/
EOF
  echo "==> Created ${GLOBAL_IGNORE}"
else
  echo "==> Already exists: ${GLOBAL_IGNORE}"
fi

current="$(git config --global --get core.excludesfile 2>/dev/null || true)"
if [[ -z "${current}" ]]; then
  git config --global core.excludesfile "${GLOBAL_IGNORE}"
  echo "==> Set git config --global core.excludesfile=${GLOBAL_IGNORE}"
elif [[ "${current}" != "${GLOBAL_IGNORE}" ]]; then
  echo "==> core.excludesfile already set to: ${current}"
  echo "    (not changed — merge ${GLOBAL_IGNORE} manually if needed)"
else
  echo "==> Global gitignore already active"
fi
