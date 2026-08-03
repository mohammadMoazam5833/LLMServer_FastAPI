# استقرار llm_fastapi روی Kubernetes (بسته تحویل)

این پوشه فقط برای **طرف مقابل / کلاستر دیگر** است.
شامل gateway + OCR اختیاری از Docker Hub + Postgres + Redis.
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

## ۲.۵) Air-gap / mirror (بدون دسترسی کلاستر به Docker Hub)

اگر نودهای Kubernetes به اینترنت/Hub دسترسی ندارند، ایمیج‌ها را روی یک ماشین آنلاین بکشید،
به‌صورت tar منتقل کنید، و روی workerها import کنید (یا داخل registry داخلی push کنید).

### الف) روی ماشین آنلاین (با Docker)

```bash
cd handoff/k8s-deploy
chmod +x mirror-images.sh
./mirror-images.sh
# خروجی پیش‌فرض: handoff/k8s-deploy/offline-images/*.tar + manifest_*.txt
# بدون OCR: INCLUDE_OCR=0 ./mirror-images.sh
```

ایمیج‌های پیش‌فرض اسکریپت:
| سرویس | ایمیج |
|--------|--------|
| Gateway | `mohammadmoazami007007/llm_proxy:latest` |
| OCR | `mohammadmoazami007007/llmocr:latest` |
| Postgres | `postgres:16-alpine` |
| Redis | `redis:7-alpine` |

### ب) انتقال و import روی worker (containerd / k8s)

```bash
# مثال: کپی tarها به هر worker که pod ممکن است schedule شود
scp offline-images/*.tar USER@worker:/tmp/llm-images/

ssh USER@worker 'sudo mkdir -p /tmp/llm-images && cd /tmp/llm-images && \
  for f in *.tar; do sudo ctr -n k8s.io images import "$f"; done && \
  sudo ctr -n k8s.io images ls | grep -E "llm_proxy|llmocr|postgres|redis"'
```

اگر runtime نود Docker است:
```bash
for f in /tmp/llm-images/*.tar; do docker load -i "$f"; done
```

در Deploymentها برای حالت offline از `imagePullPolicy: IfNotPresent` استفاده کنید
(یا `Never` اگر فقط import محلی مجاز است). در این بسته gateway/OCR الان `Always` دارند —
برای air-gap آن را به `IfNotPresent` تغییر دهید.

### ج) Registry داخلی (ترجیح برای production)

```bash
# روی ماشین آنلاین بعد از pull:
REG=registry.company.local/llm
for src in \
  mohammadmoazami007007/llm_proxy:latest \
  mohammadmoazami007007/llmocr:latest \
  postgres:16-alpine \
  redis:7-alpine
do
  name="${src##*/}"   # llm_proxy:latest / postgres:16-alpine / ...
  docker tag "$src" "${REG}/${name}"
  docker push "${REG}/${name}"
done
```

بعد در `kustomization.yaml` بخش `images:` را به registry خودتان عوض کنید، مثلاً:
```yaml
images:
  - name: llm_proxy
    newName: registry.company.local/llm/llm_proxy
    newTag: latest
  - name: llmocr
    newName: registry.company.local/llm/llmocr
    newTag: latest
  - name: postgres
    newName: registry.company.local/llm/postgres
    newTag: 16-alpine
  - name: redis
    newName: registry.company.local/llm/redis
    newTag: 7-alpine
```

برای pin کردن نسخه، به‌جای tag از digest استفاده کنید (پایدارتر از `latest`):
```yaml
  - name: llm_proxy
    newName: mohammadmoazami007007/llm_proxy
    digest: sha256:331f1bc3a574cb724996de117bf8deb1ace7ae71ba7ab4cabfab31c587c95683
```
Digest را از `manifest_*.txt` خروجی `mirror-images.sh` یا از `docker image inspect` بردارید.

**توجه:** vLLM ایمیج جداست و باید از قبل روی کلاستر شما باشد؛ این اسکریپت آن را mirror نمی‌کند.

---

## ۳) قبل از apply

```bash
cd handoff/k8s-deploy
cp 10-postgres-secret.yaml.example 10-postgres-secret.yaml
cp 31-gateway-secret.yaml.example 31-gateway-secret.yaml
```

پسورد و `SECRET_KEY` را عوض کنید.
در `30-gateway-configmap.yaml` مقدار `VLLM_BASE_URL` را به vLLM خودتان بگذارید.

`OCR_SERVICE_URL` پیش‌فرض `http://ocr:8010/api/v1/ocr` است (سرویس داخل کلاستر).
اگر OCR نمی‌خواهید: خط `- 40-ocr.yaml` را از `kustomization.yaml` بردارید و `OCR_SERVICE_URL` را خالی بگذارید.
برای GPU، در `40-ocr.yaml` مقدار `nvidia.com/gpu` / MIG / `nodeSelector` را با کلاستر خودتان هماهنگ کنید.

اگر vLLM شما با `--api-key` / `VLLM_API_KEY` محافظت شده:
- در Admin → Connection همان کلید را بگذارید (ترجیح)، **یا**
- در `31-gateway-secret.yaml` فیلد `VLLM_API_KEY` را پر کنید (پیش‌فرض کلاستر).

بدون این کار، چت با خطای `401 API key required` از vLLM شکست می‌خورد.

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

### First boot روی Postgres خالی

با `AUTO_CREATE_TABLES=false` گیت‌وی دیگر به‌خاطر نبود جدول کرش نمی‌کند، ولی **جداول را خودش نمی‌سازد**.
Migrationهای فعلی بیشتر ALTER هستند (فرض: اسکیما از قبل هست).

روی دیتابیس خالی یک‌بار یکی از این دو را انجام دهید:

**الف) یک‌بار create_all (ساده‌تر):**
```bash
# موقتاً در ConfigMap:
#   AUTO_CREATE_TABLES: "true"
kubectl -n team-b rollout restart deploy/gateway
kubectl -n team-b rollout status deploy/gateway
kubectl -n team-b exec deploy/gateway -- alembic stamp head   # یا upgrade head
# بعد دوباره AUTO_CREATE_TABLES=false و restart
```

**ب) اگر جداول از قبل هستند:** فقط `alembic upgrade head`.

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
| `40-ocr.yaml` | OCR (اختیاری؛ نیاز به GPU) |
| `mirror-images.sh` | Pull+save ایمیج‌ها برای air-gap |
| `*-secret.yaml.example` | الگوی secret |
| `33-imagepullsecret.example.yaml` | فقط اگر Hub خصوصی شد |
