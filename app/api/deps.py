"""
FastAPI dependency functions.

Usage in a route:
    current_user: User = Depends(get_current_user)       # JWT
    current_user: User = Depends(require_api_key)        # API Key (OpenAI routes)
    db: AsyncSession  = Depends(get_db)                  # DB session
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Security, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.api_key import APIKey
from app.core.security import decode_token, hash_api_key

# ── JWT Bearer ─────────────────────────────────────────────────────────────────
_bearer = HTTPBearer(auto_error=False)
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Validates Bearer JWT and returns the associated User.
    Raises HTTP 401 on any failure.
    """
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not credentials:
        raise exc

    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            raise exc
        user_id: str = payload.get("sub")
        if user_id is None:
            raise exc
    except JWTError:
        raise exc

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise exc
    return user


async def require_api_key(
    request: Request,
    x_api_key: str | None = Security(_api_key_header),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Validates X-API-Key header (or Bearer fallback) and returns the User.
    This is used on the OpenAI-compatible public endpoints.
    """
    raw_key = x_api_key

    # fallback: Authorization: Bearer sk-...
    if not raw_key:
        auth = request.headers.get("Authorization")
        if auth and auth.startswith("Bearer "):
            raw_key = auth.split(" ", 1)[1]

    if not raw_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Provide X-API-Key header or Bearer token.",
        )

    key_hash = hash_api_key(raw_key)

    result = await db.execute(
        select(APIKey)
        .where(APIKey.key_hash == key_hash, APIKey.is_active == True)  # noqa: E712
        .options()
    )
    api_key_obj = result.scalar_one_or_none()

    if api_key_obj is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API key.",
        )

    # Load user via a second query (avoids lazy-load on async session)
    user_result = await db.execute(
        select(User).where(User.id == api_key_obj.user_id)
    )
    user = user_result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")

    return user
