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

# ── Database ───────────────────────────────────────────────────────────────
    # تغییر localhost به 127.0.0.1 جهت دور زدن باگ uvloop
    DATABASE_URL: str = "postgresql+asyncpg://postgres:Isiran%40123@127.0.0.1:5432/llm_server"
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

    # ── LLM Runtime ───────────────────────────────────────────────────────────
    VLLM_BASE_URL: str = "http://127.0.0.1:8003/v1"
    VLLM_DEFAULT_MODEL: str = "/home/moazemi-gc/Qwen3-Coder-30B-A3B-Instruct"
    VLLM_REQUEST_TIMEOUT: float = 300.0

    # ── Chain Manager TTL ─────────────────────────────────────────────────────
    CHAIN_TTL_SECONDS: int = 1800         # 30 minutes idle eviction

    # ── RAG ───────────────────────────────────────────────────────────────────
    RAG_UPLOAD_DIR: str = "/tmp/llm_fastapi_uploads"
    RAG_CHUNK_SIZE: int = 1200
    RAG_CHUNK_OVERLAP: int = 200
    RAG_TOP_K: int = 4

    # ── OCR ────────────────────────────────────────────────────────────────────
    OCR_LANG: str = "fa"              # OCR language (fa = Persian + English)
    OCR_GPU: bool = True               # Use GPU for easyocr when available


@lru_cache
def get_settings() -> Settings:
    return Settings()
