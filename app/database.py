from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
)
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings

settings = get_settings()

# ── Engine ─────────────────────────────────────────────────────────────────────
# echo=True logs all SQL in DEBUG mode – turn off in production
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,          # verify connection before using from pool
    pool_size=20,
    max_overflow=30,
)

# ── Session factory ────────────────────────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,      # keep attributes accessible after commit
    autoflush=False,
    autocommit=False,
)


# ── Declarative Base ───────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── FastAPI dependency ─────────────────────────────────────────────────────────
async def get_db() -> AsyncSession:
    """
    Yields an async DB session per request.
    Usage:
        db: AsyncSession = Depends(get_db)
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def ensure_api_key_columns(*, bind=None) -> None:
    """
    Lightweight schema patches for api_keys_apikey (no Alembic required).

    Safe when AUTO_CREATE_TABLES=false on an empty database: if the table is not
    present yet, this is a no-op so the gateway can start and Alembic (or a
    one-time create_all) can create the schema afterwards.
    """
    import logging
    from sqlalchemy import text

    logger = logging.getLogger(__name__)
    eng = bind if bind is not None else engine

    async with eng.begin() as conn:
        exists = await conn.scalar(
            text("SELECT to_regclass('public.api_keys_apikey') IS NOT NULL")
        )
        if not exists:
            logger.info(
                "🧱 Skipping api_keys_apikey column patch — table not present yet "
                "(run alembic upgrade / enable AUTO_CREATE_TABLES for first boot)"
            )
            return

        await conn.execute(
            text(
                "ALTER TABLE api_keys_apikey "
                "ADD COLUMN IF NOT EXISTS key_hint VARCHAR(32) DEFAULT ''"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE api_keys_apikey "
                "ADD COLUMN IF NOT EXISTS key_encrypted VARCHAR(512) DEFAULT ''"
            )
        )
