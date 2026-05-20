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

    logger.info("Database URL: %s", engine.url)
    # Auto-create tables (use Alembic in production instead)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(auth_router, prefix="/api/v1/auth")
    app.include_router(internal_router, prefix="/api/v1")
    app.include_router(openai_router, prefix="/v1")

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
