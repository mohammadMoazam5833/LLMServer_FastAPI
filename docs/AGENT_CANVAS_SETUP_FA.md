# راه‌اندازی Agent Canvas (local) + Code Bot

جایگزین ساده‌تر OpenHands برای کار روی `LLM_SERVER` — بدون Docker sandbox و بدون دردسر permission.

---

## پیش‌نیازها

| مورد | دستور بررسی |
|------|-------------|
| Node.js 22+ | `node --version` |
| Gateway | `curl http://127.0.0.1:8001/health` |
| vLLM | `curl http://127.0.0.1:8003/v1/models` |
| Workspace | `/home/moazemi-gc/LLM_SERVER` |

### پورت‌ها

| سرویس | پورت |
|--------|------|
| OpenWebUI | 3000 |
| OpenHands (قدیمی) | 3001 |
| Gateway / code_bot | 8001 |
| **Agent Canvas** | **8002** |
| vLLM | 8003 |

OpenHands می‌تواند هم‌زمان بالا باشد — تداخل پورت ندارد.

---

## راه‌اندازی

```bash
cd ~/llm_fastapi
chmod +x scripts/run_agent_canvas.sh
./scripts/run_agent_canvas.sh
```

مرورگر: **http://127.0.0.1:8002**

---

## تنظیم LLM (یک‌بار در UI)

`Settings → LLM`:

| فیلد | مقدار |
|------|--------|
| Base URL | `http://127.0.0.1:8001/code_bot/v1` |
| API Key | همان key شما (`sk-...`) |
| Model | `openai//home/moazemi-gc/extra_space/models/Qwen3-Coder-30B-A3B-Instruct` |

---

## شروع کار

1. **Open Workspace** → `/home/moazemi-gc/LLM_SERVER`
2. conversation جدید بزنید
3. agent مستقیم روی فایل‌های host کار می‌کند (بدون mount Docker)

---

## متغیرهای env (اختیاری)

```bash
AGENT_CANVAS_WORKSPACE=/path/to/project \
CANVAS_PORT=8002 \
./scripts/run_agent_canvas.sh
```

---

## تفاوت با OpenHands

| | OpenHands (`run_openhands.sh`) | Agent Canvas (`run_agent_canvas.sh`) |
|--|-------------------------------|--------------------------------------|
| Sandbox Docker | بله | خیر (local) |
| Permission / ACL | دردسر دارد | ندارد |
| انتخاب پوشه | env دستی | Open Workspace در UI |
| آفلاین | بله* | بله* |

\* با gateway + vLLM روی همان ماشین

---

## خاموش کردن OpenHands (اختیاری)

اگر فقط Agent Canvas می‌خواهید:

```bash
docker stop openhands-app
```

---

## عیب‌یابی

| مشکل | راه‌حل |
|------|--------|
| `agent-canvas: command not found` | اسکریپت خودش `npm install -g` می‌زند |
| `EACCES` روی `~/.openhands/profiles` | `~/.openhands` مالک root است (از Docker). اسکریپت با Docker خودکار fix می‌کند؛ یا: `docker run --rm -v ~/.openhands:/data alpine chown -R $(id -u):$(id -g) /data` |
| پورت 8002 اشغال | `CANVAS_PORT=8004 ./scripts/run_agent_canvas.sh` |
| LLM 502 | gateway و vLLM را چک کنید |
| مدل پاسخ نمی‌دهد | نام model در UI را دقیقاً مثل vLLM بگذارید |
