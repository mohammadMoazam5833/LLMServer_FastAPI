---
name: LLM FastAPI Architecture
overview: بررسی کامل معماری و جریان کاری پروژه llm_fastapi در سطح مهندسی نرم‌افزار — شامل لایه‌بندی سیستم، مسیرهای API، چرخه عمر درخواست، و مدیریت وابستگی‌های خارجی.
todos: []
isProject: false
---

# معماری و جریان کاری پروژه llm_fastapi

## خلاصه پروژه

یک **LLM API Gateway** ناهمزمان (async) بر پایه FastAPI است که سه سطح سرویس‌دهی مجزا دارد، به یک سرور vLLM محلی متصل است، و از PostgreSQL + Redis به‌عنوان لایه داده استفاده می‌کند. پروژه از یک Django monolith مهاجرت کرده و رد پای آن در نام جداول (`users_user`, `api_keys_apikey`) هنوز باقیست.

---

## Stack فناوری

- **Web Framework:** FastAPI + Uvicorn (ASGI، کاملاً async)
- **ORM:** SQLAlchemy 2.0 async + asyncpg → PostgreSQL
- **Auth:** JWT (`python-jose`) + SHA-256 API Key + legacy Django PBKDF2
- **LLM Orchestration:** LangChain LCEL (برای مسیر داخلی)
- **Chat Memory:** Redis (LangChain buffer window k=4)
- **LLM Inference:** vLLM (OpenAI-compatible HTTP)
- **RAG:** sklearn HashingVectorizer + pypdf + easyocr
- **HTTP Client:** httpx (async, connection pooling)

---

## معماری لایه‌بندی شده

```mermaid
flowchart TB
    subgraph clients [Clients - لایه کلاینت]
        UI[Internal Frontend\nJWT Auth]
        WebUI[Open WebUI\nAPI Key]
        Cline[Cline Code Bot\nAPI Key]
    end

    subgraph gateway [FastAPI Gateway - پورت 8000]
        CORS[CORS Middleware]
        subgraph routes [Routers]
            R1["/api/v1/auth\nبدون احراز هویت"]
            R2["/api/v1/*\nJWT Bearer"]
            R3["/v1/*\nAPI Key - OpenAI Compatible"]
            R4["/code_bot/v1/*\nAPI Key - Proxy"]
        end
        subgraph deps [Dependencies - احراز هویت]
            D1[get_current_user\nJWT decode]
            D2[require_api_key\nSHA-256 lookup]
        end
    end

    subgraph services [Services - لایه سرویس]
        SVC1[chat_completion_service\nهماهنگ‌ساز اصلی]
        SVC2[chat_service\nمدیریت مکالمه]
        SVC3[rag_service\nبازیابی اسناد]
        SVC4[model_service\nمدیریت مدل‌ها]
        SVC5[openwebui_tasks\nشناسایی تسک‌های داخلی]
        SVC6[token_utils\nتخمین توکن فارسی-انگلیسی]
    end

    subgraph runtime [Runtime - لایه اجرا]
        subgraph chain [LangChain Pipeline]
            CM[ChainManager\nکش per-conversation با TTL]
            CH[chain.py\nLCEL Pipeline]
            MEM[memory.py\nRedis Buffer Window]
            MW[model_wrapper.py\nBaseChatModel]
        end
        PM[provider_manager\nfactory: local / openai]
        GF[generator_factory\nsingleton httpx clients]
        VG[vllm_http_generator\nAsync HTTP to vLLM]
    end

    subgraph external [External Services - سرویس‌های خارجی]
        PG[(PostgreSQL\nUsers, Keys, Chats, RAG)]
        RD[(Redis\nChat Memory)]
        VLLM[vLLM Server\nپورت 8003]
        OCR[OCR Microservice\nپورت 8010]
        FS[Local Filesystem\nRAG Files]
    end

    clients --> CORS --> routes
    R1 --> D1
    R2 --> D1 --> SVC1
    R3 --> D2 --> SVC1
    R4 --> D2 --> VLLM

    SVC1 --> SVC2
    SVC1 --> SVC3
    SVC1 --> SVC5
    SVC2 --> CH --> MEM --> RD
    SVC2 --> PG
    SVC3 --> PG
    SVC3 --> OCR
    SVC3 --> FS

    SVC1 --> PM --> GF --> VG --> VLLM
    SVC2 --> CM --> CH --> MW --> PM
```

---

## جریان کاری چهار مسیر اصلی

### مسیر A — چت داخلی با حافظه و RAG

این مسیر کامل‌ترین مسیر است. از JWT auth، LangChain chain، Redis memory، RAG، و PostgreSQL استفاده می‌کند.

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
    Router->>CCS: create_chat_completion()

    CCS->>CCS: is_openwebui_task? (title/tags/followup)
    alt Open WebUI internal task
        CCS->>VG: direct call, skip RAG+DB
        VG->>VLLM: POST /chat/completions
        VLLM-->>VG: response
        VG-->>CCS: text
        CCS-->>Client: JSON response
    else Normal chat
        CCS->>RAG: retrieve_context(query, user_files)
        RAG->>PG: SELECT chunks WHERE similarity > threshold
        RAG-->>CCS: context_text (token-capped)

        CCS->>PG: get or create Conversation
        CCS->>CS: chat(conversation, messages, context)
        CS->>PG: INSERT Message (role=user)
        CS->>CM: get_chain(conversation_id)
        CM-->>CS: LCEL chain (cached or new)
        CS->>LC: chain.ainvoke(input)
        LC->>Redis: load last 4 turns
        Redis-->>LC: history messages
        LC->>VG: generate(messages + history + RAG)
        VG->>VLLM: POST /v1/chat/completions
        VLLM-->>VG: {text, usage}
        VG-->>LC: response
        LC->>Redis: save new turn
        LC-->>CS: assistant message
        CS->>PG: INSERT Message (role=assistant)
        CS-->>CCS: response + conversation_id
        CCS-->>Client: JSON {message, conversation_id, usage}
    end
```

### مسیر B — OpenAI-Compatible API (بدون حافظه)

```mermaid
sequenceDiagram
    participant WebUI as Open WebUI
    participant Router as /v1/chat
    participant Auth as API Key Auth
    participant CCS as chat_completion_service
    participant RAG as rag_service
    participant OCR as OCR Service :8010
    participant VG as vllm_http_generator
    participant VLLM as vLLM :8003

    WebUI->>Router: POST {messages, model, stream?, files?}
    Router->>Auth: X-API-Key header → SHA-256 → lookup DB
    Auth-->>Router: User object

    CCS->>CCS: flatten_messages()\nمتن‌سازی پیام‌های multimodal
    alt Image content
        CCS->>OCR: POST base64 image
        OCR-->>CCS: extracted text
    end

    alt files provided
        CCS->>RAG: retrieve_context()
        RAG-->>CCS: context chunks
        CCS->>CCS: inject RAG into system prompt
    end

    CCS->>CCS: trim_history() برای token budget

    alt stream=false
        CCS->>VG: generate()
        VG->>VLLM: POST /v1/chat/completions
        VLLM-->>VG: JSON response
        VG-->>CCS: {text, usage}
        CCS-->>WebUI: JSON response
    else stream=true
        CCS->>VG: generate_stream()
        VG->>VLLM: POST stream=true
        VLLM-->>VG: SSE chunks
        VG-->>CCS: AsyncIterator[str]
        CCS-->>WebUI: SSE stream (EventSourceResponse)
    end
```

### مسیر C — Code Bot Proxy (بدون واسطه)

```mermaid
flowchart LR
    Cline[Cline IDE] -->|POST /code_bot/v1/chat/completions\nAPI Key| Router[code_bot router]
    Router -->|require_api_key| DB[(PostgreSQL\nkey lookup)]
    DB -->|User OK| Router
    Router -->|raw httpx POST| VLLM[vLLM :8003]
    VLLM -->|JSON response| Router
    Router -->|raw JSON| Cline
```

بدون RAG، بدون DB tracking، بدون LangChain — مستقیم‌ترین مسیر.

### مسیر D — RAG File Ingestion

```mermaid
flowchart TD
    Upload[POST /api/v1/files\nJWT Auth] --> Save[ذخیره فایل در دیسک\nRAG_UPLOAD_DIR]
    Save --> DB1[INSERT RAGFile در PostgreSQL]
    DB1 --> Q{process=true?}
    Q -->|بله| Extract[extract_text_async]
    Q -->|خیر| Done[پایان - processing بعداً]
    Extract --> PDF{نوع فایل}
    PDF -->|PDF| PyPDF[pypdf text extraction]
    PDF -->|Image| EasyOCR[easyocr local OCR]
    PDF -->|Text| Direct[خواندن مستقیم]
    PyPDF & EasyOCR & Direct --> Chunk[تقسیم به chunk‌ها]
    Chunk --> Embed[HashingVectorizer embedding]
    Embed --> DB2[INSERT RAGChunk per chunk\nبا vector embedding]
    DB2 --> Done2[آماده برای retrieval]
```

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
    App->>PG: Base.metadata.create_all()\nایجاد جداول اگر نباشند
    App->>BG: asyncio.create_task(chain_cleanup_loop)\nهر 600 ثانیه یکبار
    BG->>BG: ChainManager.cleanup()\nحذف chain‌های idle بیش از 30 دقیقه

    Note over Uvicorn,BG: RUNNING
    loop هر 10 دقیقه
        BG->>BG: evict idle chains از memory
    end

    Note over Uvicorn,BG: SHUTDOWN
    Uvicorn->>App: shutdown signal
    App->>BG: cancel cleanup task
    App->>App: GeneratorFactory.close_all()\nبستن httpx clients
    App->>PG: engine.dispose()
```

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
        int id PK
        string name
        string model_id
        string provider
        bool is_active
        json metadata
    }
    conversations {
        int id PK
        int user_id FK
        int model_id FK
        string title
        datetime created_at
    }
    messages {
        int id PK
        int conversation_id FK
        string role
        text content
        int token_count
        datetime created_at
    }
    rag_files {
        int id PK
        int user_id FK
        string filename
        string file_path
        bool is_processed
        datetime uploaded_at
    }
    rag_chunks {
        int id PK
        int file_id FK
        text content
        blob embedding
        int chunk_index
    }

    users_user ||--o{ api_keys_apikey : has
    users_user ||--o{ conversations : owns
    users_user ||--o{ rag_files : uploads
    conversations ||--o{ messages : contains
    llm_llmmodel ||--o{ conversations : uses
    rag_files ||--o{ rag_chunks : split_into
```

---

## نقاط قوت و ضعف معماری

**نقاط قوت:**
- کاملاً async — بدون blocking thread
- سه سطح سرویس با احراز هویت مستقل
- Provider abstraction — تعویض راحت vLLM با OpenAI
- Singleton cache برای httpx clients و LangChain chains
- RAG با fair-share round-robin و token budget

**نقاط ضعف / بدهی فنی:**
- `create_all` در startup به جای Alembic migrations (versions خالی)
- Rate limiting و quota ذخیره‌سازی می‌شود اما **اعمال نمی‌شود**
- Chat ownership validation گم است در `/api/v1/chats/{chat_id}`
- مسیر داخلی streaming کد دارد اما **wired نشده**
- `DEFAULT_SECRET_KEY` و `DEBUG=True` در config پیش‌فرض
- کدهای comment شده زیاد در `chat_completion_service.py`

---

## فایل تغییر یافته: `vllm_http_generator.py`

```mermaid
flowchart LR
    subgraph before [قبل از تغییر]
        B1[timeout ثابت 300s]
        B2[خطاها swallow می‌شدند]
        B3[stream scope bug]
        B4[بدون connection pooling]
    end
    subgraph after [بعد از تغییر - uncommitted]
        A1[min 180s read timeout\nاگر config کمتر از 120s]
        A2[خطاها re-raise می‌شوند]
        A3[last_data bug fix]
        A4[max_connections=50\nkeepalive=10]
    end
    before -->|git diff| after
```
