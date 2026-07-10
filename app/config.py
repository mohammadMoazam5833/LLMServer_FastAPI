from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── App ────────────────────────────────────────────────────────────────────
    APP_TITLE: str = "OpenAI Compatible LLM API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    ALLOWED_ORIGINS: list[str] = ["*"]
    # در حالت توسعه جداول خودکار ساخته می‌شوند؛ در production این را false کنید و از Alembic استفاده کنید.
    AUTO_CREATE_TABLES: bool = True

# ── Database ───────────────────────────────────────────────────────────────
    # مقدار واقعی باید از فایل .env یا secret manager بیاید؛ این فقط placeholder است.
    # (از 127.0.0.1 به‌جای localhost برای دور زدن باگ uvloop استفاده کنید)
    DATABASE_URL: str = "postgresql+asyncpg://user:password@127.0.0.1:5432/llm_server"
    # ── JWT ────────────────────────────────────────────────────────────────────
    SECRET_KEY: str = "change-me-in-production-use-secrets-token-hex-64"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Redis ──────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_CHAT_TTL: int = 604800          # 7 days in seconds

    # ── API Key ────────────────────────────────────────────────────────────────
    API_KEY_PREFIX: str = "sk-"
    # سقف پیش‌فرض درخواست در دقیقه به ازای هر کلید (~۱۵ کاربر همزمان + ابزارهای agent)
    DEFAULT_RATE_LIMIT_PER_MINUTE: int = 180

    # ── LLM Runtime ───────────────────────────────────────────────────────────
    VLLM_BASE_URL: str = "http://127.0.0.1:8003/v1"
    VLLM_DEFAULT_MODEL: str = "/home/moazemi-gc/extra_space/models/Qwen3-Coder-30B-A3B-Instruct"
    VLLM_REQUEST_TIMEOUT: float = 300.0

    # سقف کانتکست برای مسیر چت (OpenWebUI و API داخلی). روت code_bot/Cline پروکسی خام است
    # و از این سقف عبور نمی‌کند، پس Cline همچنان از کل max-model-len واقعی vLLM استفاده می‌کند.
    CHAT_MAX_CONTEXT_TOKENS: int = 65536
    # حداقل توکن خروجی وقتی OpenWebUI max_tokens=2048 می‌فرستد ولی کانتکست جا دارد
    CHAT_MIN_OUTPUT_TOKENS: int = 4096

    # ── Chain Manager TTL ─────────────────────────────────────────────────────
    CHAIN_TTL_SECONDS: int = 1800         # 30 minutes idle eviction

    # ── RAG ───────────────────────────────────────────────────────────────────
    RAG_UPLOAD_DIR: str = "/tmp/llm_fastapi_uploads"
    RAG_CHUNK_SIZE: int = 1200
    RAG_CHUNK_OVERLAP: int = 200
    RAG_TOP_K: int = 4
    RAG_MIN_SCORE: float = 0.30
    RAG_MAX_CONTEXT_TOKENS: int = 2048
    RAG_EMBEDDING_DIM: int = 384
    RAG_EMBEDDING_MODEL: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    RAG_EMBEDDING_DEVICE: str = "cpu"
    RAG_MAX_FILE_SIZE_MB: int = 25       # سقف حجم فایل آپلودی برای RAG

    # ── OpenWebUI file fetch (وقتی Bypass فایل را در messages فوروارد نمی‌کند)
    OPENWEBUI_BASE_URL: str = "http://127.0.0.1:3000"
    OPENWEBUI_API_KEY: str = ""  # JWT یا API key کاربر OWUI برای /api/v1/files/{id}/data/content
    OPENWEBUI_FILE_FETCH_ENABLED: bool = True

    # ── Auto-attach uploaded files for OpenWebUI fallback
    # When True, if a chat request contains no `files`, the server will
    # look for a recent upload by the same user and attach it automatically.
    ALLOW_AUTO_ATTACH_RECENT_UPLOADS: bool = True
    AUTO_ATTACH_TIME_WINDOW_SECONDS: int = 300  # 5 minutes

    # ── OCR ────────────────────────────────────────────────────────────────────
    OCR_LANG: str = "fa"              # OCR language (fa = Persian + English)
    OCR_GPU: bool = False               # Use GPU for easyocr when available
    # آدرس میکروسرویس تک‌ورکره OCR
    OCR_SERVICE_URL :str = "http://127.0.0.1:8010/api/v1/ocr"

    # ── Load testing (dev only) ───────────────────────────────────────────────
    # وقتی true باشد enforce_rate_limit هیچ سقفی اعمال نمی‌کند (فقط برای Locust/k6)
    LOAD_TEST_DISABLE_RATE_LIMIT: bool = False

@lru_cache
def get_settings() -> Settings:
    return Settings()
