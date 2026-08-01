#!/usr/bin/env bash
# Export local llm_proxy image for offline load onto a Kubernetes worker
# (no registry). Production should use k8s_push_gateway_image.sh instead.
#
# On this machine:
#   ./scripts/k8s_save_gateway_image.sh
#   # scp backups/llm_proxy_*.tar user@worker-s01:/tmp/
#
# On worker-s01 (containerd):
#   sudo ctr -n k8s.io images import /tmp/llm_proxy_XXXX.tar
#   sudo ctr -n k8s.io images ls | grep llm_proxy
#
# On worker-s01 (docker runtime, if used):
#   docker load -i /tmp/llm_proxy_XXXX.tar
#
# Then pin gateway to that node (see k8s/team-b/32-gateway-deployment.yaml
# nodeName comment) and keep imagePullPolicy: IfNotPresent.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-${ROOT}/backups}"
mkdir -p "${OUT_DIR}"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT_FILE="${OUT_DIR}/llm_proxy_${STAMP}.tar"
SRC_IMAGE="${SRC_IMAGE:-llm_proxy:latest}"

if ! docker image inspect "${SRC_IMAGE}" >/dev/null 2>&1; then
  echo "==> Image ${SRC_IMAGE} missing — building from Dockerfile"
  docker build -t "${SRC_IMAGE}" "${ROOT}"
fi

echo "==> Saving ${SRC_IMAGE} -> ${OUT_FILE}"
docker save "${SRC_IMAGE}" -o "${OUT_FILE}"
ls -lh "${OUT_FILE}"
echo "==> Copy to worker and import, e.g.:"
echo "    scp ${OUT_FILE} USER@worker-s01:/tmp/"
echo "    ssh USER@worker-s01 'sudo ctr -n k8s.io images import /tmp/$(basename "${OUT_FILE}")'"
