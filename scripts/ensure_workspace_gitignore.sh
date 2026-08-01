#!/usr/bin/env bash
# Ensure a git repo has Agent-Canvas-friendly .gitignore entries.
# Merges missing patterns only — never removes user rules.
#
# Usage:
#   ./scripts/ensure_workspace_gitignore.sh /path/to/workspace
#   ./scripts/ensure_workspace_gitignore.sh /path/a /path/b
set -euo pipefail

DEFAULT_PATTERNS=(
  'node_modules/'
  'dist/'
  'build/'
  '.vite/'
  '__pycache__/'
  '*.pyc'
  '.pytest_cache/'
  '.mypy_cache/'
  '.ruff_cache/'
  '*.log'
  '.DS_Store'
  '.env'
  '.env.*'
  '!.env.example'
  'coverage/'
  '.coverage'
  'htmlcov/'
  '*.egg-info/'
  '.venv/'
  'venv/'
)

ensure_one() {
  local workspace="$1"
  [[ -d "${workspace}" ]] || return 0

  local git_root
  if ! git_root="$(git -C "${workspace}" rev-parse --show-toplevel 2>/dev/null)"; then
    return 0
  fi

  local ignore_file="${git_root}/.gitignore"
  local added=0
  touch "${ignore_file}"

  if ! grep -q '^# --- agent-canvas defaults ---' "${ignore_file}" 2>/dev/null; then
    {
      echo ''
      echo '# --- agent-canvas defaults ---'
      echo '# Added by llm_fastapi/scripts/ensure_workspace_gitignore.sh'
    } >> "${ignore_file}"
    added=1
  fi

  local pattern line
  for pattern in "${DEFAULT_PATTERNS[@]}"; do
    if ! grep -qxF "${pattern}" "${ignore_file}" 2>/dev/null; then
      echo "${pattern}" >> "${ignore_file}"
      added=1
    fi
  done

  if [[ "${added}" -eq 1 ]]; then
    echo "==> Updated .gitignore at ${git_root}"
  fi
}

if [[ "$#" -eq 0 ]]; then
  echo "Usage: $0 /path/to/workspace [...]" >&2
  exit 1
fi

for workspace in "$@"; do
  ensure_one "${workspace}"
done
