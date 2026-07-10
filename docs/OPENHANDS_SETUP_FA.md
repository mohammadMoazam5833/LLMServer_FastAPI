# راه‌اندازی پایدار OpenHands + Code Bot

راهنمای تیم برای اجرای OpenHands روی سرور GPU با مدل محلی (`llm_fastapi` → vLLM).

---

## مشکلاتی که پیش آمد

### ۱. خطای Sandbox (`Sandbox entered error state`)

| علت | توضیح |
|-----|--------|
| env شبکه نبود | `OH_WEB_URL` و `SANDBOX_CONTAINER_URL_PATTERN` در `docker run` اولیه تنظیم نشده بود |
| `host.docker.internal` | OpenHands از داخل container به `host.docker.internal:PORT` وصل می‌شد — روی Linux اغلب کار نمی‌کند |
| پورت 3000 اشغال | OpenWebUI روی 3000 است؛ OpenHands باید روی **3001** باشد |
| VPN tunnel | TUN v2ray (`172.18.0.1`) با subnet Docker (`172.18.0.0/16`) تداخل داشت و route sandbox را خراب می‌کرد |

### ۲. خطای MCP (`MCP Connection Failure`)

| علت | توضیح |
|-----|--------|
| agent-server در bridge | داخل agent-server، `127.0.0.1:3001` یعنی خود کانتینر، نه OpenHands |
| پورت webhook اشتباه | `SANDBOX_HOST_PORT` پیش‌فرض 3000 بود (OpenWebUI) نه 3001 |
| VPN | `host.docker.internal` با tunnel resolve نمی‌شد |

### ۳. LLM / Code Bot

| علت | توضیح |
|-----|--------|
| Base URL اشتباه در UI | `host.docker.internal` با `--network host` timeout می‌دهد |
| Custom Model اشتباه | مسیر مدل در فیلد Base URL گذاشته شده بود |

**نکته:** gateway (`:8001`) و vLLM (`:8003`) معمولاً سالم بودند؛ مشکل در **شبکه OpenHands** بود.

---

## چطور حل شد

| مشکل | راه‌حل |
|------|--------|
| Sandbox | `--network host` + `OH_WEB_URL` + `SANDBOX_CONTAINER_URL_PATTERN=http://HOST:3001/{port}` |
| پورت | OpenHands روی **3001** (uvicorn مستقیم روی host) |
| MCP | `AGENT_SERVER_USE_HOST_NETWORK=true` + `SANDBOX_HOST_PORT=3001` |
| LLM | `base_url=http://HOST:8001/code_bot/v1` در تنظیمات UI |
| VPN | خاموش هنگام تست؛ یا bypass `127.0.0.0/8` + `/etc/hosts` برای `host.docker.internal` |

---

## پیش‌نیازها (یک‌بار روی سرور)

```bash
# 1) Docker نصب و کاربر در گروه docker
docker info

# 2) Gateway و vLLM در حال اجرا
curl -s http://127.0.0.1:8001/health
curl -s http://127.0.0.1:8003/v1/models

# 3) webhook با VPN — یک‌بار روی سرور
grep -q 'host.docker.internal' /etc/hosts || \
  echo '127.0.0.1 host.docker.internal' | sudo tee -a /etc/hosts

# 4) تصویر agent-server (اولین بار)
docker pull ghcr.io/openhands/agent-server:1.27.0-python
docker pull docker.openhands.dev/openhands/openhands:1.8
```

### پورت‌ها

| سرویس | پورت | نقش |
|--------|------|-----|
| OpenWebUI | 3000 | چت وب (جدا) |
| **OpenHands** | **3001** | Agent IDE |
| **llm_fastapi** | **8001** | Gateway + `/code_bot/v1` |
| vLLM | 8003 | Inference |

---

## راه‌اندازی پایدار (نسخه درست)

### گام ۱ — متغیرها

```bash
cd /home/moazemi-gc/llm_fastapi

# IP سرور برای دسترسی تیم از LAN (خودکار یا دستی)
export OPENHANDS_HOST="${OPENHANDS_HOST:-$(hostname -I | awk '{print $1}')}"
# مثال: export OPENHANDS_HOST=172.16.40.188
```

### گام ۲ — اجرای اسکریپت

```bash
chmod +x scripts/run_openhands.sh
./scripts/run_openhands.sh
```

**پوشهٔ کاری agent:** به‌طور پیش‌فرض کل ریپو `llm_fastapi` به `/workspace` داخل sandbox mount می‌شود. agent همان‌جا فایل می‌سازد و ویرایش می‌کند.

```bash
# پوشهٔ دیگر (مثلاً home یا پروژهٔ جدا)
OPENHANDS_WORKSPACE=/home/moazemi-gc/projects/myapp ./scripts/run_openhands.sh

# چند mount (پروژه + داده فقط‌خواندنی)
export SANDBOX_VOLUMES="/home/moazemi-gc/llm_fastapi:/workspace:rw,/data/big:/data:ro"
```

**هشدار:** agent می‌تواند فایل‌های mount‌شده را **حذف یا تغییر** دهد. برای تیم بهتر است هر نفر زیرپوشهٔ خودش را mount کند:

```bash
OPENHANDS_WORKSPACE=/home/shared/openhands/workspaces/alice ./scripts/run_openhands.sh
```

`SANDBOX_USER_ID=$(id -u)` از ایجاد فایل root-owned روی host جلوگیری می‌کند.

### گام ۳ — تنظیم LLM در UI (یک‌بار per user یا در settings سرور)

برو به `http://OPENHANDS_HOST:3001` → Settings → LLM → Advanced:

| فیلد | مقدار |
|------|--------|
| Custom Model | `openai//home/moazemi-gc/extra_space/models/Qwen3-Coder-30B-A3B-Instruct` |
| Base URL | `http://OPENHANDS_HOST:8001/code_bot/v1` |
| API Key | کلید API از gateway (هر کاربر یا کلید مشترک تیم) |

برای دسترسی **فقط از خود سرور**: `127.0.0.1` به‌جای IP.

### گام ۴ — تست

```bash
# UI
curl -s -o /dev/null -w "%{http_code}\n" "http://${OPENHANDS_HOST}:3001/"

# Code bot
curl -s "http://127.0.0.1:8001/code_bot/v1/models" -H "X-API-Key: YOUR_KEY"

# MCP endpoint (405 = سالم)
curl -s -o /dev/null -w "%{http_code}\n" "http://${OPENHANDS_HOST}:3001/mcp/mcp"
```

در UI: task ساده `echo hello` — نباید Sandbox یا MCP error ببینید.

---

## VPN / v2ray (کاربران سرور)

هنگام کار با OpenHands روی **همان ماشین**:

1. **Tunnel mode را خاموش کنید** (یا subnet TUN را از `172.18.x` عوض کنید)
2. در System proxy exceptions اضافه کنید:
   ```
   localhost,127.0.0.0/8,172.16.0.0/12,172.17.0.0/16,10.0.0.0/8,192.168.0.0/16
   ```
3. Cursor/اینترنت می‌تواند VPN داشته باشد؛ OpenHands محلی از `127.0.0.1` / IP LAN استفاده می‌کند

---

## عیب‌یابی سریع

| خطا | کار |
|-----|-----|
| Sandbox error | `./scripts/run_openhands.sh` دوباره؛ VPN tunnel off |
| MCP failure | `AGENT_SERVER_USE_HOST_NETWORK=true` در اسکریپت؛ container جدید |
| LLM timeout | Base URL را `http://IP:8001/code_bot/v1` بزنید نه `host.docker.internal` |
| 401 LLM | API Key درست در UI |
| 429 LLM | `rate_limit_per_minute` کلید در DB |

```bash
docker logs openhands-app --tail 50
docker ps | grep oh-agent-server
```

---

## فایل‌های مرتبط

- [`scripts/run_openhands.sh`](../scripts/run_openhands.sh) — راه‌اندازی استاندارد
- [`app/api/code_bot/router.py`](../app/api/code_bot/router.py) — پروکسی vLLM برای agent
- `~/.openhands/settings.json` — تنظیمات LLM ذخیره‌شده
