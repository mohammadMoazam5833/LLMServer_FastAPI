"""
main.py — FastAPI application entry point.

Startup:
  - Creates DB tables (if not using Alembic)
  - Starts background chain cleanup task

Shutdown:
  - Cancels cleanup task
  - Closes all shared httpx clients
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import engine, Base

# Import models so SQLAlchemy knows about them before create_all
import app.models  # noqa: F401

from app.api.auth.router import router as auth_router
from app.api.internal.router import router as internal_router
from app.api.openai.router import router as openai_router
from app.api.code_bot.router import router as code_bot_router

logger = logging.getLogger(__name__)
settings = get_settings()

# Ensure logging is configured when running via uvicorn (not just __main__)
logging.basicConfig(level=logging.DEBUG if settings.DEBUG else logging.INFO)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

# ── Background cleanup task ────────────────────────────────────────────────────
_cleanup_task: asyncio.Task | None = None


async def _chain_cleanup_loop():
    """Evict idle chains every 10 minutes."""
    from app.langchain_integration.chain_manager import ChainManager
    while True:
        await asyncio.sleep(600)
        evicted = await ChainManager.cleanup()
        if evicted:
            logger.info("🧹 Chain cleanup: evicted %d entries", evicted)


# ── Lifespan ───────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _cleanup_task

    # ── Startup ────────────────────────────────────────────────────────────────
    logger.info("🚀 Starting up LLM FastAPI server…")

    from app.core.redis_client import ping as redis_ping
    if await redis_ping():
        logger.info("✅ Redis connected (%s)", settings.REDIS_URL)
    else:
        logger.warning(
            "⚠️  Redis unavailable at %s — rate limit/quota/attachment cache use in-memory fallback",
            settings.REDIS_URL,
        )

    logger.info("Database URL: %s", engine.url)
    # ساخت خودکار جداول فقط در حالت توسعه؛ در production با AUTO_CREATE_TABLES=false
    # از مهاجرت‌های Alembic استفاده کنید (`alembic upgrade head`).
    if settings.AUTO_CREATE_TABLES:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("🧱 Tables ensured via create_all (dev mode)")
    else:
        logger.info("🧱 AUTO_CREATE_TABLES disabled — manage schema with Alembic")

    _cleanup_task = asyncio.create_task(_chain_cleanup_loop())
    logger.info("✅ Server ready")

    yield  # ← application runs here

    # ── Shutdown ───────────────────────────────────────────────────────────────
    logger.info("🛑 Shutting down…")

    if _cleanup_task:
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass

    from app.runtime.generator_factory import GeneratorFactory
    await GeneratorFactory.close_all()

    from app.core.rate_limit import aclose as close_rate_limit_redis
    await close_rate_limit_redis()

    from app.core.redis_client import aclose as close_shared_redis
    await close_shared_redis()

    await engine.dispose()
    logger.info("👋 Shutdown complete")


# ── App factory ────────────────────────────────────────────────────────────────
def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_TITLE,
        version=settings.APP_VERSION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS
    # طبق اسپک، allow_origins=["*"] با allow_credentials=True نامعتبر است و مرورگرها
    # آن را رد می‌کنند؛ پس فقط وقتی origin مشخص باشد credential مجاز می‌شود.
    allow_credentials = "*" not in settings.ALLOWED_ORIGINS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(auth_router, prefix="/api/v1/auth")
    app.include_router(internal_router, prefix="/api/v1")
    app.include_router(openai_router, prefix="/v1")
    app.include_router(code_bot_router, prefix="/code_bot/v1")

    @app.get("/health")
    async def health():
        from app.core.redis_client import ping as redis_ping
        from app.core.attachment_cache import ping as attach_cache_ping
        redis_ok = await redis_ping()
        return {
            "status": "ok",
            "redis": redis_ok,
            "attachment_cache_redis": attach_cache_ping(),
        }

    return app


app = create_app()


# ── Dev entry point ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.DEBUG if settings.DEBUG else logging.INFO)
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="debug" if settings.DEBUG else "info",
    )
