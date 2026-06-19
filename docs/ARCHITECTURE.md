# معماری و جریان کاری — llm_fastapi

مستند مهندسی نرم‌افزار برای Gateway چت و RAG. نمودارهای منبع در `docs/diagrams/` قرار دارند.

---

## خلاصه پروژه

**llm_fastapi** یک **LLM API Gateway** ناهمزمان (async) بر پایه FastAPI است که:

- سه سطح سرویس‌دهی مجزا دارد (JWT داخلی، OpenAI-compatible، Code Bot proxy)
- به vLLM محلی (پورت ۸۰۰۳) متصل می‌شود
- PostgreSQL + Redis به‌عنوان لایه داده استفاده می‌کند
- OpenWebUI را با scoping فایل per-turn و OCR برای تصاویر پشتیبانی می‌کند

پروژه از یک Django monolith مهاجرت کرده؛ رد پای آن در نام جداول (`users_user`, `api_keys_apikey`) باقی است.

---

## Stack فناوری

| لایه | فناوری |
|------|--------|
| Web | FastAPI + Uvicorn (ASGI، کاملاً async) |
| ORM | SQLAlchemy 2.0 async + asyncpg → PostgreSQL |
| Auth | JWT (`python-jose`) + SHA-256 API Key + legacy Django PBKDF2 |
| LLM Orchestration | LangChain LCEL (مسیر داخلی `/api/v1`) |
| Chat Memory | Redis — LangChain buffer window `k=4` |
| LLM Inference | vLLM (OpenAI-compatible HTTP) |
| RAG Embedding | `sentence-transformers` (paraphrase-multilingual-MiniLM-L12-v2) |
| RAG Extract | pypdf + easyocr (fallback) + OCR microservice برای چت |
| HTTP Client | httpx (async, connection pooling) |
| Cache | Redis — rate limit, quota, attachment delta, OCR cache |

---

## معماری لایه‌بندی شده

```mermaid
flowchart TB
    subgraph clients [Clients]
        UI[Internal Frontend\nJWT Auth]
        WebUI[Open WebUI\nAPI Key]
        Cline[Cline Code Bot\nAPI Key]
    end

    subgraph gateway [FastAPI Gateway — default port 8000]
        CORS[CORS Middleware]
        subgraph routes [Routers]
            R1["/api/v1/auth\nno auth"]
            R2["/api/v1/*\nJWT Bearer"]
            R3["/v1/*\nAPI Key OpenAI-compat"]
            R4["/code_bot/v1/*\nAPI Key proxy"]
        end
        subgraph deps [Dependencies]
            D1[get_current_user\nJWT decode]
            D2[require_api_key\nSHA-256 + rate limit]
        end
    end

    subgraph services [Services Layer]
        SVC1[chat_completion_service]
        SVC2[chat_service]
        SVC3[rag_service]
        SVC4[model_service]
        SVC5[openwebui_content\nper-turn file scoping]
        SVC6[openwebui_files\nOWUI file bridge]
        SVC7[embedding_service]
        SVC8[token_utils]
        SVC9[openwebui_tasks]
    end

    subgraph runtime [Runtime Layer]
        subgraph chain [LangChain — internal path]
            CM[ChainManager\nTTL cache]
            CH[chain.py LCEL]
            MEM[memory.py Redis k=4]
            MW[model_wrapper.py]
        end
        PM[provider_manager]
        GF[generator_factory\nhttpx pool]
        VG[vllm_http_generator]
    end

    subgraph external [External Services]
        PG[(PostgreSQL)]
        RD[(Redis\nmemory + rate limit + attach cache)]
        VLLM[vLLM :8003]
        OCR[OCR Microservice :8010]
        OWUI[OpenWebUI File API :3000]
        FS[Local FS\nRAG uploads]
    end

    clients --> CORS --> routes
    R1 --> D1
    R2 --> D1 --> SVC1
    R3 --> D2 --> SVC1
    R4 --> D2 --> VLLM

    SVC1 --> SVC2
    SVC1 --> SVC3
    SVC1 --> SVC5
    SVC1 --> SVC6
    SVC1 --> SVC9
    SVC3 --> SVC7
    SVC3 --> PG
    SVC3 --> OCR
    SVC3 --> FS
    SVC6 --> OWUI

    SVC2 --> CH --> MEM --> RD
    SVC2 --> PG
    SVC1 --> PM --> GF --> VG --> VLLM
    SVC2 --> CM --> CH --> MW --> PM
```

**منبع:** `docs/diagrams/layered-architecture.mmd`

---

## پورت‌ها و سرویس‌های خارجی

| سرویس | پورت پیش‌فرض | نقش |
|--------|-------------|-----|
| llm_fastapi | 8000 (`main.py`) | Gateway — ممکن است در deploy روی 8001 |
| vLLM | 8003 | Inference (Qwen3-Coder-30B) |
| OpenWebUI | 3000 (container 8080) | UI + فایل‌ها |
| OCR microservice | 8010 | استخراج متن از تصویر |
| Redis | 6379 | Memory, rate limit, attachment cache |
| PostgreSQL | 5432 | Users, chats, RAG |

---

## جریان کاری — چهار مسیر اصلی

### مسیر A — چت داخلی با حافظه و RAG

`POST /api/v1/chat/completions` — JWT، LangChain، Redis memory، PostgreSQL.

```mermaid
sequenceDiagram
    participant Client
    participant Router as /api/v1/chat
    participant Auth as JWT Auth
    participant CCS as chat_completion_service
    participant RAG as rag_service
    participant CS as chat_service
    participant CM as ChainManager
    participant LC as LangChain LCEL
    participant Redis
    participant PG as PostgreSQL
    participant VG as vllm_http_generator
    participant VLLM as vLLM :8003

    Client->>Router: POST {messages, model, conversation_id?}
    Router->>Auth: validate Bearer token
    Auth-->>Router: User object
    Router->>CCS: create_chat_completion() or stream

    CCS->>CCS: is_openwebui_internal_task?
    alt OpenWebUI internal task
        CCS->>VG: direct call skip RAG+DB
        VG->>VLLM: POST /chat/completions
        VLLM-->>VG: response
        VG-->>CCS: text
        CCS-->>Client: JSON or SSE
    else Normal chat
        CCS->>RAG: retrieve_context(query, file_ids)
        RAG->>PG: semantic search on rag_chunk metadata
        RAG-->>CCS: context_text capped

        CCS->>PG: get or create Conversation
        CCS->>CS: chat(conversation, messages, context)
        CS->>PG: INSERT Message user
        CS->>CM: get_chain(conversation_id)
        CM-->>CS: LCEL chain cached or new
        CS->>LC: chain.ainvoke(input)
        LC->>Redis: load last 4 turns
        Redis-->>LC: history
        LC->>VG: generate(messages + history + RAG)
        VG->>VLLM: POST /v1/chat/completions
        VLLM-->>VG: {text, usage}
        VG-->>LC: response
        LC->>Redis: save turn
        LC-->>CS: assistant message
        CS->>PG: INSERT Message assistant
        CS-->>CCS: response + conversation_id
        CCS-->>Client: JSON {message, conversation_id, usage}
    end
```

**منبع:** `docs/diagrams/workflow-internal.mmd`

---

### مسیر B — OpenAI-Compatible (OpenWebUI)

`POST /v1/chat/completions` — API Key، بدون LangChain memory، با file scoping و OCR.

```mermaid
sequenceDiagram
    participant WebUI as OpenWebUI
    participant Router as /v1/chat
    participant Auth as API Key + rate limit
    participant OWF as openwebui_files
    participant OWC as openwebui_content
    participant CCS as chat_completion_service
    participant RAG as rag_service
    participant OCR as OCR :8010
    participant VG as vllm_http_generator
    participant VLLM as vLLM :8003

    WebUI->>Router: POST full history + files
    Router->>Auth: X-API-Key SHA-256 lookup
    Auth-->>Router: User

    Router->>OWF: enrich_request_from_openwebui
    OWF-->>Router: body with inline file content

    CCS->>OWC: resolve_turn_file_scope
    OWC-->>CCS: keep_files, allowed, reason

    CCS->>CCS: scope_message_content + filter_sources
    Note over CCS: strip image base64 from model input

    alt Images this turn
        CCS->>OWC: current_turn_images
        CCS->>OCR: POST image base64
        OCR-->>CCS: extracted text
        CCS->>CCS: inject OCR after user_query
    end

    alt files / RAG UUIDs
        CCS->>RAG: retrieve_context
        RAG-->>CCS: semantic chunks
        CCS->>CCS: inject into system prompt
    end

    CCS->>CCS: trim to CHAT_MAX_CONTEXT_TOKENS

    alt stream=false
        CCS->>VG: generate()
        VG->>VLLM: POST
        VLLM-->>VG: JSON
        VG-->>CCS: text + usage
        CCS-->>WebUI: JSON
    else stream=true
        CCS->>VG: generate_stream()
        VG->>VLLM: POST stream=true
        VLLM-->>VG: SSE chunks
        VG-->>CCS: AsyncIterator
        CCS-->>WebUI: EventSourceResponse
    end
```

**منبع:** `docs/diagrams/workflow-openai.mmd`

#### دلایل scoping (`resolve_turn_file_scope`)

| reason | معنی |
|--------|------|
| `request.files` | فایل صریح در payload |
| `last-msg-fresh-source` | `<source>` جدید در آخرین پیام |
| `last-msg-image-focused` | پرسش عکس‌محور — فقط تصاویر جدید |
| `new-images:N` | فقط عکس جدید، بدون PDF قدیمی |
| `conv-delta` | تفاوت با Redis attachment cache |
| `last-msg-inline-file` | PDF inline بدون تگ source |
| `carrier-merge` | merge از پیام حامل |
| `no-attach` | نوبت بدون فایل |

---

### مسیر C — Code Bot Proxy

`POST /code_bot/v1/chat/completions` — بدون RAG، بدون LangChain، مستقیم به vLLM.

```mermaid
flowchart LR
    Cline[Cline IDE] -->|POST /code_bot/v1/chat/completions\nAPI Key| Router[code_bot router]
    Router -->|require_api_key\nrate limit + quota| DB[(PostgreSQL\nkey lookup)]
    DB -->|User OK| Router
    Router -->|raw httpx POST| VLLM[vLLM :8003]
    VLLM -->|JSON response| Router
    Router -->|raw JSON| Cline
```

**منبع:** `docs/diagrams/workflow-codebot.mmd`

---

### مسیر D — RAG File Ingestion

`POST /api/v1/files` — JWT، ذخیره، chunk، embed، retrieve.

```mermaid
flowchart TD
    Upload[POST /api/v1/files\nJWT Auth] --> Save[Save to RAG_UPLOAD_DIR]
    Save --> DB1[INSERT rag_file]
    DB1 --> Q{process=true?}
    Q -->|yes| Extract[extract_text_async]
    Q -->|no| Done[status uploaded]
    Extract --> Type{file type}
    Type -->|PDF| PyPDF[pypdf]
    Type -->|Image| EasyOCR[easyocr local fallback]
    Type -->|Text| Direct[read file]
    PyPDF & EasyOCR & Direct --> Chunk[chunk_text overlap]
    Chunk --> Embed[embed_texts\nsentence-transformers]
    Embed --> DB2[INSERT rag_chunk\nembedding in metadata JSON]
    DB2 --> Done2[status ready for retrieve_context]
```

**منبع:** `docs/diagrams/workflow-rag.mmd`

---

## چرخه عمر برنامه (Lifespan)

```mermaid
sequenceDiagram
    participant Uvicorn
    participant App as FastAPI App
    participant PG as PostgreSQL
    participant BG as Background Task

    Note over Uvicorn,BG: STARTUP
    Uvicorn->>App: start lifespan
    App->>App: Redis ping health check
    alt AUTO_CREATE_TABLES=true
        App->>PG: Base.metadata.create_all
    end
    App->>BG: create_task chain_cleanup_loop every 600s

    Note over Uvicorn,BG: RUNNING
    loop every 10 minutes
        BG->>BG: ChainManager.cleanup idle chains
    end

    Note over Uvicorn,BG: SHUTDOWN
    Uvicorn->>App: shutdown signal
    App->>BG: cancel cleanup task
    App->>App: GeneratorFactory.close_all
    App->>App: close rate_limit + redis clients
    App->>PG: engine.dispose
```

**منبع:** `docs/diagrams/lifespan.mmd`

---

## مدل داده (ERD)

```mermaid
erDiagram
    users_user {
        int id PK
        string username
        string password
        bool is_active
        bool is_superuser
    }
    api_keys_apikey {
        int id PK
        int user_id FK
        string key_hash
        string name
        int rate_limit_per_minute
        int monthly_token_quota
        datetime created_at
    }
    llm_llmmodel {
        string id PK
        string model_path
        string provider
        int context_length
        bool is_active
        json metadata
    }
    llm_conversation {
        uuid id PK
        int user_id FK
        string model_id FK
        string title
        text system_prompt
        datetime created_at
    }
    llm_message {
        int id PK
        uuid conversation_id FK
        string role
        text content
        int prompt_tokens
        int completion_tokens
        json metadata
        datetime created_at
    }
    rag_file {
        uuid id PK
        int user_id FK
        string filename
        string path
        string status
        datetime created_at
    }
    rag_chunk {
        int id PK
        uuid file_id FK
        int chunk_index
        text content
        int token_count
        json metadata
    }

    users_user ||--o{ api_keys_apikey : has
    users_user ||--o{ llm_conversation : owns
    users_user ||--o{ rag_file : uploads
    llm_conversation ||--o{ llm_message : contains
    llm_llmmodel ||--o{ llm_conversation : uses
    rag_file ||--o{ rag_chunk : split_into
```

**منبع:** `docs/diagrams/erd.mmd`

Embedding بردارها در `rag_chunk.metadata_.embedding` (JSON) ذخیره می‌شوند، نه ستون جدا.

---

## ماژول‌ها و توابع کلیدی

### `chat_completion_service.py`

| تابع | نقش |
|------|-----|
| `create_openai_chat_completion_stream` | مسیر اصلی OpenWebUI (SSE) |
| `create_chat_completion` | مسیر داخلی JWT |
| `_to_openai_messages_async` | Scoping، OCR، merge، hints |
| `_prepare` | مدل، RAG، token budget |
| `_ocr_image_url` | فراخوانی OCR microservice |
| `_trim_messages_to_budget` | محدود به `CHAT_MAX_CONTEXT_TOKENS` |

### `openwebui_content.py`

| تابع | نقش |
|------|-----|
| `resolve_turn_file_scope` | `(keep_files, allowed, reason)` |
| `current_turn_images` | تصاویر همین نوبت (بدون Redis) |
| `filter_sources` | فیلتر `<source>` + strip base64 |
| `scope_message_content` | اعمال scoping روی یک پیام |
| `attachments_delta_for_conversation` | delta ضمائم در Redis |

### `openwebui_files.py`

| تابع | نقش |
|------|-----|
| `enrich_request_from_openwebui` | واکشی محتوای فایل از OWUI API |
| `resolve_owui_chat_id` | استخراج chat_id از header |

### `rag_service.py`

| تابع | نقش |
|------|-----|
| `create_rag_file` | آپلود فایل |
| `ingest_rag_file` | chunk + embed |
| `retrieve_context` | جستجوی semantic + lexical |
| `ocr_base64_image` | OCR via microservice + cache |

### `vllm_http_generator.py`

| تابع | نقش |
|------|-----|
| `generate` | Non-streaming به vLLM |
| `generate_stream` | SSE streaming |

---

## vllm_http_generator — بهبودها

```mermaid
flowchart LR
    subgraph before [Before]
        B1[fixed 300s timeout]
        B2[errors swallowed]
        B3[stream scope bug]
        B4[no connection pooling]
    end
    subgraph after [Current]
        A1["min 180s read timeout\nif config below 120s"]
        A2[errors re-raised with logging]
        A3[last_data bug fixed]
        A4["Limits max_connections=50\nkeepalive=10"]
    end
    before --> after
```

جزئیات: `docs/VLLM_HTTP_GENERATOR.md`

---

## نقاط قوت و ضعف معماری

### نقاط قوت

- کاملاً async — بدون blocking thread
- سه سطح سرویس با احراز هویت مستقل
- Provider abstraction — تعویض vLLM / OpenAI
- Singleton cache برای httpx clients و LangChain chains
- RAG semantic با sentence-transformers + fallback lexical
- Per-turn file scoping برای OpenWebUI (تاریخچه کامل در هر درخواست)
- OCR ایزوله — مدل متنی بدون vision
- Rate limit و quota روی API Key (`enforce_rate_limit`, `enforce_quota`)
- 87 unit test

### بدهی فنی / ریسک

- `create_all` در startup وقتی `AUTO_CREATE_TABLES=true` (dev) — production باید Alembic
- `DEFAULT_SECRET_KEY` در config — باید در production تغییر کند
- `DEBUG=True` پیش‌فرض
- کدهای comment شده زیاد در `chat_completion_service.py`
- Redis fail-open برای rate limit — اگر Redis down باشد محدودیت اعمال نمی‌شود
- OWUI بدون `chat_id` در header — collision risk در attachment cache

---

## مستندات مرتبط

- [PROJECT_REPORT_FA.md](./PROJECT_REPORT_FA.md) — گزارش اجرایی فارسی
- [LOAD_TESTING.md](./LOAD_TESTING.md) — راهنمای Locust و ظرفیت ۱۵–۲۰ کاربر
- [VLLM_HTTP_GENERATOR.md](./VLLM_HTTP_GENERATOR.md) — جزئیات کلاینت vLLM
- [../README.md](../README.md) — نصب و endpoints

---

## تولید PNG از نمودارها

```bash
# با mermaid-cli (اختیاری)
npx @mermaid-js/mermaid-cli -i docs/diagrams/layered-architecture.mmd -o docs/images/architecture-overview.png
```
