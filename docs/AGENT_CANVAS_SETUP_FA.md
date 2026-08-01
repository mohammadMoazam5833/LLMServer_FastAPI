# راه‌اندازی Agent Canvas (local) + Code Bot

جایگزین ساده‌تر OpenHands برای کار روی `LLM_SERVER` — بدون Docker sandbox و بدون دردسر permission.

برای توضیح معماری (Canvas vs agent-server vs OpenHands Docker): [AGENT_CANVAS_VS_AGENT_SERVER_FA.md](AGENT_CANVAS_VS_AGENT_SERVER_FA.md)

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
./scripts/stop_openhands.sh
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
| UI کند / سیستم سنگین | `bash_events` و polling UI — نگه‌داری خودکار (پایین) |
| workspace با هزاران git change | از `LLM_SERVER` استفاده کنید، نه پوشهٔ `agent canvas` |

---

## نگه‌داری خودکار (جلوگیری از کندی تکراری)

مشکل کندی معمولاً از **CPU ضعیف** نیست — از انباشت هزاران فایل کوچک `bash_events` و اسکن git روی workspace سنگین است.

اسکریپت `run_agent_canvas.sh` الان این کارها را **هر بار استارت** انجام می‌دهد:

- `OH_BASH_EVENTS_RETENTION_SECONDS=7200` — agent-server خودش فایل‌های قدیمی bash را پاک می‌کند
- `maintain_agent_canvas.sh` — prune فوری + کوتاه کردن لاگ‌های بزرگ

### cron (اختیاری، پیشنهاد می‌شود)

```bash
chmod +x ~/llm_fastapi/scripts/maintain_agent_canvas.sh
crontab -e
# هر ۲ ساعت:
0 */2 * * * /home/moazemi-gc/llm_fastapi/scripts/maintain_agent_canvas.sh >> ~/.agent-canvas/logs/maintenance.log 2>&1
```

### workspace

همیشه **Open Workspace → `/home/moazemi-gc/LLM_SERVER`** بزنید. پوشهٔ `agent canvas` هزاران تغییر git دارد و UI هر ~۱۰ ثانیه آن را اسکن می‌کند.

### `.gitignore` خودکار

`run_agent_canvas.sh` هر بار استارت، الگوهای استاندارد (`node_modules/`، `dist/`، …) را به `.gitignore` **ریشهٔ git** workspace اضافه می‌کند (فقط خطوط جدید — چیزی حذف نمی‌شود).

workspaceهای اضافه را در این فایل ثبت کنید (یک مسیر در هر خط):

```text
~/.config/llm_fastapi/agent_canvas_workspaces.txt
```

مثال:

```text
/home/moazemi-gc/LLM_SERVER
/home/moazemi-gc/agent canvas
/home/moazemi-gc/agent canvas/suran-panel
```

**یک‌بار برای همهٔ repoها (پیشنهاد قوی):**

```bash
chmod +x ~/llm_fastapi/scripts/setup_agent_canvas_global_gitignore.sh
~/llm_fastapi/scripts/setup_agent_canvas_global_gitignore.sh
```

این `git config --global core.excludesfile` را تنظیم می‌کند تا `node_modules` و … حتی بدون `.gitignore` محلی ignore شوند.

### ری‌استارت برای اعمال retention

اگر Agent Canvas الان بالا است، یک‌بار ری‌استارت کنید تا `OH_BASH_EVENTS_RETENTION_SECONDS` فعال شود:

```bash
pkill -f 'agent-canvas --port 8002' || true
pkill -f 'agent-server --host 127.0.0.1 --port 18000' || true
cd ~/llm_fastapi && ./scripts/run_agent_canvas.sh
```

