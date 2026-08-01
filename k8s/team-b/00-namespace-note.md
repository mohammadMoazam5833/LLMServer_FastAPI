# Namespace

Namespace هدف: **`team-b`** (از قبل در کلاستر `my-cluster` وجود دارد).

این پوشه **namespace نمی‌سازد** — فقط منابع داخل `team-b` را تعریف می‌کند.

```bash
kubectl config set-context --current --namespace=team-b
kubectl apply -k k8s/team-b/
```

تا وقتی ادمین RBAC (Secret / Service / PVC / StatefulSet) را باز نکرده، `apply` با Forbidden مواجه می‌شود — مانیفست‌ها فقط آماده‌اند.
