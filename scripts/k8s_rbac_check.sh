#!/usr/bin/env bash
# Print whether current kube user can create the resources we need in team-b.
set -euo pipefail
NS="${1:-team-b}"

need=(
  "create secrets"
  "create configmaps"
  "create services"
  "create persistentvolumeclaims"
  "create statefulsets.apps"
  "create deployments.apps"
  "create pods/exec"
  "create pods/portforward"
)

echo "==> RBAC check in namespace ${NS} (user from current context)"
kubectl config current-context
ok=0
bad=0
for item in "${need[@]}"; do
  # shellcheck disable=SC2086
  if kubectl auth can-i ${item} -n "${NS}" >/dev/null 2>&1; then
    echo "  OK   ${item}"
    ok=$((ok + 1))
  else
    echo "  FAIL ${item}"
    bad=$((bad + 1))
  fi
done
echo "==> ${ok} ok, ${bad} missing"
[[ "${bad}" -eq 0 ]]
