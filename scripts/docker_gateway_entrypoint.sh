#!/usr/bin/env bash
# Bridge-network helper for llm_fastapi gateway.
#
# Host Postgres listens on 127.0.0.1 only, so TCP via host.docker.internal
# fails from compose bridge networks. We mount the host Unix socket and
# rewrite DATABASE_URL to use it (Postgres stays on host per plan).
set -euo pipefail

rewrite_database_url_to_unix_socket() {
  python3 - <<'PY'
import os
import re
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode, unquote, quote

url = os.environ.get("DATABASE_URL", "")
if not url:
    raise SystemExit(0)

# Already socket-based?
if "host=/var/run/postgresql" in url or url.startswith("postgresql+asyncpg:///") :
    print(url)
    raise SystemExit(0)

# SQLAlchemy style: postgresql+asyncpg://user:pass@host:port/db
m = re.match(
    r"^(postgresql\+asyncpg://)([^:/]+):([^@]*)@[^/]+/([^?]+)(.*)$",
    url,
)
if not m:
    print(url)
    raise SystemExit(0)

scheme, user, password, db, rest = m.groups()
# Keep any existing query except replace host=
q = rest[1:] if rest.startswith("?") else ""
params = dict(parse_qsl(q, keep_blank_values=True))
params["host"] = "/var/run/postgresql"
new_url = f"{scheme}{user}:{password}@/{db}?{urlencode(params)}"
print(new_url)
PY
}

if [[ -n "${DATABASE_URL:-}" ]]; then
  export DATABASE_URL="$(rewrite_database_url_to_unix_socket)"
fi

export REDIS_URL="${REDIS_URL:-redis://redis:6379/0}"
export VLLM_BASE_URL="${VLLM_BASE_URL:-http://host.docker.internal:8003/v1}"
export OCR_SERVICE_URL="${OCR_SERVICE_URL:-http://host.docker.internal:8010/api/v1/ocr}"

exec "$@"
