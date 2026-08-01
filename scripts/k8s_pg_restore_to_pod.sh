#!/usr/bin/env bash
# Restore a pg_dump (-Fc) file into the in-cluster Postgres StatefulSet pod.
#
# Prerequisites: RBAC for pods/exec (and optionally port-forward).
#
# Usage:
#   ./scripts/k8s_pg_restore_to_pod.sh backups/llm_server_YYYYMMDD_HHMMSS.dump
#   NAMESPACE=team-b POD=postgres-0 ./scripts/k8s_pg_restore_to_pod.sh ./file.dump
set -euo pipefail

DUMP="${1:-}"
if [[ -z "${DUMP}" || ! -f "${DUMP}" ]]; then
  echo "Usage: $0 /path/to/llm_server.dump" >&2
  exit 1
fi

NAMESPACE="${NAMESPACE:-team-b}"
POD="${POD:-postgres-0}"
SECRET="${SECRET:-llm-postgres}"
REMOTE_PATH="/tmp/restore.dump"

echo "==> Checking pod ${NAMESPACE}/${POD}"
kubectl -n "${NAMESPACE}" get pod "${POD}" >/dev/null

PGUSER="$(kubectl -n "${NAMESPACE}" get secret "${SECRET}" -o jsonpath='{.data.POSTGRES_USER}' | base64 -d)"
PGDATABASE="$(kubectl -n "${NAMESPACE}" get secret "${SECRET}" -o jsonpath='{.data.POSTGRES_DB}' | base64 -d)"
export PGPASSWORD="$(kubectl -n "${NAMESPACE}" get secret "${SECRET}" -o jsonpath='{.data.POSTGRES_PASSWORD}' | base64 -d)"

echo "==> Copy dump into pod"
kubectl -n "${NAMESPACE}" cp "${DUMP}" "${POD}:${REMOTE_PATH}"

echo "==> Restoring into database ${PGDATABASE} (user ${PGUSER})"
kubectl -n "${NAMESPACE}" exec -i "${POD}" -- \
  env PGPASSWORD="${PGPASSWORD}" \
  pg_restore -U "${PGUSER}" -d "${PGDATABASE}" --clean --if-exists --no-owner --no-acl "${REMOTE_PATH}" \
  || true
# pg_restore returns non-zero on some benign warnings; verify connectivity:
kubectl -n "${NAMESPACE}" exec -i "${POD}" -- \
  env PGPASSWORD="${PGPASSWORD}" \
  psql -U "${PGUSER}" -d "${PGDATABASE}" -c '\dt' | head -40

kubectl -n "${NAMESPACE}" exec "${POD}" -- rm -f "${REMOTE_PATH}" || true
echo "==> Restore finished. Spot-check tables above."
