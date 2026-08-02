# استقرار llm_fastapi روی Kubernetes (بسته تحویل)

این پوشه فقط برای **طرف مقابل / کلاستر دیگر** است.
شامل gateway از Docker Hub + Postgres + Redis.
**vLLM روی کلاستر شما باید از قبل موجود باشد** — ایمیج vLLM داخل این بسته نیست.

---

## ۱) ایمیج‌هایی که باید pull شوند

| سرویس | ایمیج | منبع |
|--------|--------|------|
| Gateway | `mohammadmoazami007007/llm_proxy:latest` | Docker Hub (ما) |
| OCR (اختیاری) | `mohammadmoazami007007/llmocr:latest` | Docker Hub (ما) |
| Postgres | `postgres:16-alpine` | Docker Hub رسمی |
| Redis | `redis:7-alpine` | Docker Hub رسمی |
| vLLM | مال خودتان | از قبل روی کلاستر |

لینک Hub:
- https://hub.docker.com/r/mohammadmoazami007007/llm_proxy
- https://hub.docker.com/r/mohammadmoazami007007/llmocr

---

## ۲) چطور Docker Hub را بدهید

ریپوها **Public** هستند — فقط نام ایمیج کافی است؛ یوزر/پسورد لازم نیست.

```bash
docker pull mohammadmoazami007007/llm_proxy:latest
docker pull mohammadmoazami007007/llmocr:latest   # اختیاری
```

اگر بعداً Private شدند: Access Token فقط Read + `imagePullSecrets`.

---

## ۳) قبل از apply

```bash
cd handoff/k8s-deploy
cp 10-postgres-secret.yaml.example 10-postgres-secret.yaml
cp 31-gateway-secret.yaml.example 31-gateway-secret.yaml
```

پسورد و `SECRET_KEY` را عوض کنید.
در `30-gateway-configmap.yaml` مقدار `VLLM_BASE_URL` را به vLLM خودتان بگذارید.

---

## ۴) استقرار

```bash
kubectl create namespace team-b   # اگر نیست
kubectl apply -k handoff/k8s-deploy/
kubectl -n team-b get pods -w
kubectl -n team-b exec deploy/gateway -- alembic upgrade head
kubectl -n team-b port-forward svc/gateway 8001:8001
curl -s http://127.0.0.1:8001/health
```

ادمین: `http://127.0.0.1:8001/admin` → Connection به vLLM + Model.

---

## ۵) فایل‌ها

| فایل | نقش |
|------|------|
| `README.md` | همین راهنما |
| `kustomization.yaml` | apply یکجا |
| `11-postgres-statefulset.yaml` | Postgres |
| `20-redis.yaml` | Redis |
| `30-gateway-configmap.yaml` | تنظیمات غیرمحرمانه |
| `32-gateway-deployment.yaml` | Gateway |
| `*-secret.yaml.example` | الگوی secret |
| `33-imagepullsecret.example.yaml` | فقط اگر Hub خصوصی شد |
