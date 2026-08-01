#!/usr/bin/env bash
# Dump host Postgres (llm_server) for later restore into the K8s StatefulSet.
#
# Usage:
#   ./scripts/k8s_pg_dump_host.sh
#   ./scripts/k8s_pg_dump_host.sh /path/to/outdir
#
# Reads DATABASE_URL from .env when present; falls back to local socket defaults.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-${ROOT}/backups}"
mkdir -p "${OUT_DIR}"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT_FILE="${OUT_DIR}/llm_server_${STAMP}.dump"

if [[ -f "${ROOT}/.env" ]]; then
  # shellcheck disable=SC1091
  set -a
  # Only import DATABASE_URL-related lines safely
  DATABASE_URL="$(grep -E '^DATABASE_URL=' "${ROOT}/.env" | tail -1 | cut -d= -f2-)"
  set +a
fi

PGHOST="${PGHOST:-127.0.0.1}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-postgres}"
PGDATABASE="${PGDATABASE:-llm_server}"

if [[ -n "${DATABASE_URL:-}" ]]; then
  # postgresql+asyncpg://user:pass@host:port/db
  _url="${DATABASE_URL#postgresql+asyncpg://}"
  _url="${_url#postgresql://}"
  PGUSER="$(python3 - <<PY
from urllib.parse import unquote
u = """${_url}"""
user = u.split(":", 1)[0]
print(unquote(user))
PY
)"
  PGPASSWORD="$(python3 - <<PY
from urllib.parse import unquote
u = """${_url}"""
rest = u.split(":", 1)[1]
password = rest.rsplit("@", 1)[0]
print(unquote(password))
PY
)"
  export PGPASSWORD
  hostport_db="$(python3 - <<PY
u = """${_url}"""
print(u.rsplit("@", 1)[1])
PY
)"
  # host:port/db
  PGHOST="$(echo "${hostport_db}" | cut -d: -f1)"
  PGPORT="$(echo "${hostport_db}" | cut -d: -f2 | cut -d/ -f1)"
  PGDATABASE="$(echo "${hostport_db}" | cut -d/ -f2 | cut -d? -f1)"
fi

echo "==> Dumping ${PGUSER}@${PGHOST}:${PGPORT}/${PGDATABASE}"
pg_dump -Fc -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDATABASE}" -f "${OUT_FILE}"
echo "==> Wrote ${OUT_FILE}"
ls -lh "${OUT_FILE}"
