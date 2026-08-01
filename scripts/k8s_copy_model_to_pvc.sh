#!/usr/bin/env bash
# Stream local Qwen weights into team-b/model-copy pod PVC (/models).
#
# Prereq:
#   kubectl apply -f k8s/team-b/40-model-pvc.yaml
#   kubectl -n team-b wait --for=condition=Ready pod/model-copy --timeout=180s
#
# Usage:
#   ./scripts/k8s_copy_model_to_pvc.sh
#   MODEL_DIR=/path/to/Qwen3-Coder-30B-A3B-Instruct ./scripts/k8s_copy_model_to_pvc.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAMESPACE="${NAMESPACE:-team-b}"
POD="${POD:-model-copy}"
MODEL_DIR="${MODEL_DIR:-/home/moazemi-gc/extra_space/models/Qwen3-Coder-30B-A3B-Instruct}"
MODEL_NAME="$(basename "${MODEL_DIR}")"

if [[ ! -d "${MODEL_DIR}" ]]; then
  echo "Model dir not found: ${MODEL_DIR}" >&2
  exit 1
fi

echo "==> Waiting for ${NAMESPACE}/${POD}"
kubectl -n "${NAMESPACE}" wait --for=condition=Ready "pod/${POD}" --timeout=300s

echo "==> Streaming $(du -sh "${MODEL_DIR}" | awk '{print $1}') -> ${POD}:/models/${MODEL_NAME}"
# Create destination dir, then untar stream
kubectl -n "${NAMESPACE}" exec "${POD}" -- mkdir -p "/models/${MODEL_NAME}"
tar -C "$(dirname "${MODEL_DIR}")" -cf - "${MODEL_NAME}" \
  | kubectl -n "${NAMESPACE}" exec -i "${POD}" -- tar -C /models -xf -

echo "==> Verify"
kubectl -n "${NAMESPACE}" exec "${POD}" -- du -sh "/models/${MODEL_NAME}"
kubectl -n "${NAMESPACE}" exec "${POD}" -- ls "/models/${MODEL_NAME}" | head
echo "==> Done"
