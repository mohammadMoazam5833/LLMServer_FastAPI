# LLM Server — FastAPI Migration

**مستندات معماری:** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · [گزارش فارسی](docs/PROJECT_REPORT_FA.md) · [Docker / K8s](docs/DOCKER_K8S_FA.md) · مانیفست‌ها: [`k8s/team-b/`](k8s/team-b/)

## چرا FastAPI؟

| مشکل در Django DRF | راه‌حل در FastAPI |
|---|---|
| `model_wrapper.py` از `threading + queue` برای bridge async→sync استفاده می‌کرد | `_agenerate` / `_astream` مستقیماً async پیاده‌سازی شده |
| تمام DB callها بلوکینگ (ORM سنکرون) | SQLAlchemy 2.0 async با `asyncpg` |
| Streaming در Django به درستی async نبود | `StreamingResponse` با `async generator` |
| هر request یک thread می‌گرفت | کاملاً coroutine-based، هزاران concurrent request |

---

## ساختار پروژه

```
llm_fastapi/
├── app/
│   ├── main.py                    ← FastAPI app + lifespan hooks
│   ├── config.py                  ← Pydantic Settings (جایگزین settings.py)
│   ├── database.py                ← Async SQLAlchemy engine + session
│   ├── models/                    ← SQLAlchemy ORM models
│   │   ├── user.py
│   │   ├── api_key.py
│   │   └── llm.py                 ← LLMModel, Conversation, Message
│   ├── schemas/
│   │   └── schemas.py             ← Pydantic v2 request/response schemas
│   ├── core/
│   │   └── security.py            ← JWT, password hash, API key utils
│   ├── api/
│   │   ├── deps.py                ← get_current_user, require_api_key
│   │   ├── auth/router.py         ← /api/v1/auth/login + /refresh
│   │   ├── internal/router.py     ← JWT-protected endpoints
│   │   └── openai/router.py       ← OpenAI-compatible public endpoints
│   ├── services/
│   │   ├── chat_service.py        ← Async ChatService (ainvoke/astream)
│   │   ├── chat_completion_service.py
│   │   ├── openwebui_content.py   ← per-turn file scoping
│   │   ├── openwebui_files.py     ← OpenWebUI file bridge
│   │   ├── rag_service.py
│   │   └── model_service.py       ← list_models, conversations, api keys
│   ├── runtime/
│   │   ├── vllm_http_generator.py ← Async httpx client for vLLM
│   │   ├── generator_factory.py   ← Cached generator instances
│   │   ├── provider_manager.py
│   │   └── providers/
│   │       ├── base.py
│   │       ├── hf_provider.py
│   │       └── openai_provider.py
│   └── langchain_integration/
│       ├── model_wrapper.py       ← ChatProviderWrapper (async _agenerate/_astream)
│       ├── chain.py               ← LCEL chain builder
│       ├── chain_manager.py       ← asyncio.Lock per conversation
│       └── memory.py              ← Redis memory
├── alembic/
│   ├── env.py                     ← Async Alembic config
│   └── versions/
├── alembic.ini
├── requirements.txt
└── .env.example
```

---

## نصب و راه‌اندازی

### 1. محیط مجازی و نصب وابستگی‌ها

```bash
python -m venv venv
source venv/bin/activate          # Linux/Mac
# venv\Scripts\activate           # Windows

pip install -r requirements.txt
```

### 2. فایل `.env`

```bash
cp .env.example .env
# SECRET_KEY را حتماً تغییر دهید:
python -c "import secrets; print(secrets.token_hex(64))"
```

### 3. Migration دیتابیس

```bash
# اولین بار: ساخت migration
alembic revision --autogenerate -m "initial"

# اعمال migration
alembic upgrade head
```

### 4. اجرا

```bash
# Development
python -m app.main

# یا با uvicorn مستقیم
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## Endpoints

### Auth (بدون JWT)
```
POST /api/v1/auth/login      { username, password } → { access_token, refresh_token }
POST /api/v1/auth/refresh    { refresh_token }      → { access_token, refresh_token }
```

### Internal (نیاز به JWT Bearer)
```
POST /api/v1/chat/completions
GET  /api/v1/models
GET  /api/v1/chats
GET  /api/v1/chats/{chat_id}
POST /api/v1/api-keys         ← ساخت API key جدید
```

### OpenAI-Compatible (نیاز به X-API-Key یا Bearer sk-...)
```
POST /v1/chat/completions     ← streaming پشتیبانی می‌کند
GET  /v1/models
GET  /v1/openapi.json
```

### Docs
```
GET /docs     ← Swagger UI
GET /redoc    ← ReDoc
```

### Architecture docs
```
docs/ARCHITECTURE.md          ← layered architecture + workflows (Mermaid)
docs/PROJECT_REPORT_FA.md     ← executive report (Persian)
docs/LOAD_TESTING.md          ← Locust load test guide + rate limit checklist
docs/OPENHANDS_SETUP_FA.md    ← OpenHands + code_bot stable setup (Persian)
docs/AGENT_CANVAS_SETUP_FA.md ← Agent Canvas local + code_bot (ساده‌تر، پیشنهادی)
docs/AGENT_CANVAS_VS_AGENT_SERVER_FA.md ← چرا Canvas و agent-server جدا هستند
docs/ADMIN_DASHBOARD_FA.md    ← داشبورد ادمین (کاربر، API key، مصرف توکن)
docs/diagrams/*.mmd           ← source diagrams for export
docs/VLLM_HTTP_GENERATOR.md   ← vLLM client improvements
```

---

## تفاوت‌های کلیدی در کد

### model_wrapper.py (مهم‌ترین بهبود)

**Django (قبل):** threading برای bridge کردن async به sync
```python
# ❌ هک خطرناک در Django
def run_async_stream():
    async def _consume():
        async for token in self.generator.generate_stream(...):
            q.put(token)
    asyncio.run(_consume())

t = threading.Thread(target=run_async_stream)
t.start()
while True:
    token = q.get(timeout=180)
```

**FastAPI (بعد):** native async
```python
# ✅ مستقیم و async
async def _astream(self, messages, **kwargs):
    async for token in self.generator.generate_stream(converted, max_tokens=max_t):
        chunk = ChatGenerationChunk(message=AIMessageChunk(content=token))
        yield chunk
```

### chain_manager.py

**Django:** `threading.Lock`  
**FastAPI:** `asyncio.Lock` — سبک‌تر، بدون overhead ترد

---

## ساخت superuser (برای Django admin نیازی نیست، مستقیم SQL)

```python
# یک اسکریپت Python برای ساخت کاربر اول
from app.database import AsyncSessionLocal
from app.models.user import User
from app.core.security import hash_password
import asyncio

async def create_user():
    async with AsyncSessionLocal() as db:
        user = User(
            username="admin",
            email="admin@example.com",
            password=hash_password("your_password"),
            is_staff=True,
            is_superuser=True,
        )
        db.add(user)
        await db.commit()

asyncio.run(create_user())
```
