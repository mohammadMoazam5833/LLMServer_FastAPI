# گزارش فنی پروژه llm_fastapi

**نسخه:** 1.0 · ژوئن ۲۰۲۶  
**مخاطب:** ارائه داخلی شرکت  
**مستند معماری کامل:** [ARCHITECTURE.md](./ARCHITECTURE.md)

---

## ۱. خلاصه اجرایی

`llm_fastapi` یک **Gateway چت و RAG** ناهمزمان است که بین کلاینت‌ها (OpenWebUI، Cline، اپ داخلی) و سرور inference محلی (vLLM + Qwen3-Coder-30B) قرار می‌گیرد.

**قابلیت‌های اصلی:**

- API سازگار با OpenAI برای OpenWebUI
- RAG با embedding معنایی (فارسی + انگلیسی)
- مدیریت فایل per-turn برای OpenWebUI (PDF، سند، عکس)
- OCR تصاویر via microservice (مدل متنی vision ندارد)
- احراز هویت JWT + API Key + rate limit/quota
- استریم SSE برای چت

**وضعیت:** ۸۷ تست واحد سبز · مسیر OpenWebUI با فایل و OCR پایدار

---

## ۲. معماری در یک نگاه

```
┌─────────────┐     ┌──────────────────┐     ┌─────────┐
│ OpenWebUI   │────►│ llm_fastapi      │────►│ vLLM    │
│ Cline       │     │ :8000 (gateway)  │     │ :8003   │
│ Frontend    │     └────────┬─────────┘     └─────────┘
└─────────────┘              │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
         PostgreSQL      Redis         OCR :8010
```

**لایه‌ها:**

1. **API Routers** — auth، internal، openai، code_bot
2. **Services** — chat orchestration، RAG، OWUI bridge، scoping
3. **Runtime** — LangChain (مسیر داخلی)، vLLM HTTP client
4. **External** — PostgreSQL، Redis، vLLM، OCR، OpenWebUI File API

---

## ۳. مسیرهای API

| Prefix | Auth | کاربرد |
|--------|------|--------|
| `/api/v1/auth/` | — | Login، Refresh JWT |
| `/api/v1/` | JWT | چت داخلی + RAG upload + مکالمات |
| `/v1/` | API Key | OpenWebUI (اصلی) |
| `/code_bot/v1/` | API Key | Cline — proxy خام vLLM |

---

## ۴. جریان‌های کاری

### ۴.۱ OpenWebUI (مسیر B — پرکاربرد)

1. OpenWebUI کل تاریخچه + فایل‌ها را می‌فرستد
2. `enrich_request_from_openwebui` — واکشی PDF اگر inline نباشد
3. `resolve_turn_file_scope` — فقط فایل‌های **این نوبت** مجاز
4. `filter_sources` — حذف فایل‌های قدیمی؛ strip base64 تصویر
5. `current_turn_images` → OCR microservice
6. تزریق متن OCR + trim توکن → vLLM stream

### ۴.۲ چت داخلی (مسیر A)

JWT → RAG retrieve → LangChain chain → Redis memory (k=4) → vLLM → ذخیره در PostgreSQL

### ۴.۳ Code Bot (مسیر C)

API Key → مستقیم vLLM — بدون RAG، بدون memory

### ۴.۴ آپلود RAG (مسیر D)

JWT → ذخیره فایل → extract (pypdf/easyocr) → chunk → sentence-transformers embed → PostgreSQL

---

## ۵. کتابخانه‌ها

| دسته | کتابخانه |
|------|----------|
| Web | FastAPI, Uvicorn |
| DB | SQLAlchemy 2.0, asyncpg, Alembic |
| Auth | passlib, python-jose |
| LLM | langchain-*, httpx |
| Cache | redis |
| ML/RAG | sentence-transformers, pypdf, easyocr |
| Config | pydantic-settings |
| Test | pytest |

---

## ۶. توابع کلیدی

### orchestration

- `create_openai_chat_completion_stream` — نقطه ورود OpenWebUI
- `_to_openai_messages_async` — pipeline scoping + OCR + hints
- `_prepare` — مدل، RAG، budget

### OpenWebUI integration

- `resolve_turn_file_scope` — تصمیم فایل‌های مجاز
- `current_turn_images` — تشخیص تصویر همین نوبت
- `filter_sources` — فیلتر `<source>` + حذف base64
- `enrich_request_from_openwebui` — پل فایل OWUI

### RAG

- `create_rag_file`, `ingest_rag_file`, `retrieve_context`
- `embed_text` / `embed_texts` — sentence-transformers

### Inference

- `VLLMHttpGenerator.generate` / `generate_stream`

---

## ۷. مدل داده

- `users_user` — کاربران (legacy Django table name)
- `api_keys_apikey` — کلید API + rate limit + quota
- `llm_llmmodel` — مدل‌های قابل استفاده
- `llm_conversation` + `llm_message` — تاریخچه چت داخلی
- `rag_file` + `rag_chunk` — فایل‌های RAG (embedding در metadata JSON)

---

## ۸. رفع مشکلات اخیر (OpenWebUI)

| مشکل | راه‌حل |
|------|--------|
| OCR کار نمی‌کرد | `current_turn_images` بدون Redis + fallback |
| مدل روی PDF قدیمی تمرکز می‌کرد | `last-msg-image-focused` scoping |
| دو سند، یکی به مدل می‌رسید | رفع `_name_matches` برای نام خالی |
| base64 به مدل متنی | `strip_image_bodies=True` همیشه |

لاگ تشخیصی: `📎 Sources | raw_in_msg → kept_for_model`

---

## ۹. نقاط قوت

- Async end-to-end
- جداسازی مسیرها (داخلی / OWUI / proxy)
- Scoping هوشمند برای OWUI
- OCR ایزوله + cache
- Rate limit و quota فعال روی API Key
- پوشش تست ۸۷ سناریو

---

## ۱۰. ریسک‌ها و بدهی فنی

| مورد | توضیح |
|------|--------|
| `AUTO_CREATE_TABLES` | فقط dev — production از Alembic |
| `SECRET_KEY` پیش‌فرض | باید در production تغییر کند |
| Redis fail-open | rate limit غیرفعال اگر Redis down |
| OWUI بدون chat_id | collision در attachment cache |
| کد comment شده | در `chat_completion_service.py` |

---

## ۱۱. متغیرهای محیطی مهم

```
VLLM_BASE_URL=http://127.0.0.1:8003/v1
OCR_SERVICE_URL=http://127.0.0.1:8010/api/v1/ocr
OPENWEBUI_BASE_URL=http://127.0.0.1:3000
CHAT_MAX_CONTEXT_TOKENS=65536
CHAT_MIN_OUTPUT_TOKENS=4096
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=redis://localhost:6379/0
RAG_EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

---

## ۱۲. نمودارها

فایل‌های Mermaid در `docs/diagrams/`:

- `layered-architecture.mmd` — معماری لایه‌ای
- `workflow-internal.mmd` — مسیر A
- `workflow-openai.mmd` — مسیر B (OpenWebUI)
- `workflow-codebot.mmd` — مسیر C
- `workflow-rag.mmd` — مسیر D
- `lifespan.mmd` — startup/shutdown
- `erd.mmd` — مدل داده
- `vllm-generator.mmd` — بهبودهای vLLM client

---

## ۱۳. اجرا

```bash
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Health: `GET /health` — وضعیت Redis

---

*برای جزئیات فنی کامل و نمودارهای تعاملی، [ARCHITECTURE.md](./ARCHITECTURE.md) را ببینید.*
