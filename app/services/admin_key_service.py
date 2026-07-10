from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.core.security import generate_api_key, hash_api_key, mask_api_key, encrypt_api_key, decrypt_api_key
from app.models.api_key import APIKey
from app.models.user import User


def _key_to_dict(api_key: APIKey) -> dict:
    return {
        "id": api_key.id,
        "user_id": api_key.user_id,
        "username": api_key.user.username if api_key.user else "",
        "name": api_key.name,
        "key_hint": api_key.key_hint or "",
        "raw_key": decrypt_api_key(api_key.key_encrypted),
        "is_active": api_key.is_active,
        "rate_limit_per_minute": api_key.rate_limit_per_minute,
        "monthly_token_quota": api_key.monthly_token_quota,
        "created_at": api_key.created_at,
        "revoked_at": api_key.revoked_at,
    }


async def list_api_keys(db: AsyncSession, user_id: int | None = None) -> list[dict]:
    q = select(APIKey).options(selectinload(APIKey.user)).order_by(APIKey.created_at.desc())
    if user_id is not None:
        q = q.where(APIKey.user_id == user_id)

    result = await db.execute(q)
    keys = result.scalars().all()
    return [_key_to_dict(k) for k in keys]


async def create_api_key_for_user(
    db: AsyncSession,
    *,
    user_id: int,
    name: str = "",
    rate_limit_per_minute: int | None = None,
    monthly_token_quota: int = 1_000_000,
) -> tuple[dict, str]:
    user_result = await db.execute(select(User).where(User.id == user_id))
    if user_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    default_rpm = get_settings().DEFAULT_RATE_LIMIT_PER_MINUTE
    rpm = rate_limit_per_minute if rate_limit_per_minute is not None else default_rpm

    raw_key = generate_api_key()
    api_key = APIKey(
        user_id=user_id,
        name=name,
        key_hash=hash_api_key(raw_key),
        key_hint=mask_api_key(raw_key),
        key_encrypted=encrypt_api_key(raw_key),
        rate_limit_per_minute=rpm,
        monthly_token_quota=monthly_token_quota,
    )
    db.add(api_key)
    await db.flush()

    await db.refresh(api_key, attribute_names=["user"])
    return _key_to_dict(api_key), raw_key


async def update_api_key(
    db: AsyncSession,
    key_id: uuid.UUID,
    *,
    is_active: bool | None = None,
    rate_limit_per_minute: int | None = None,
    monthly_token_quota: int | None = None,
) -> dict:
    result = await db.execute(
        select(APIKey).where(APIKey.id == key_id).options(selectinload(APIKey.user))
    )
    api_key = result.scalar_one_or_none()
    if api_key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")

    if is_active is not None:
        api_key.is_active = is_active
        if not is_active and api_key.revoked_at is None:
            api_key.revoked_at = datetime.now(timezone.utc)
        elif is_active:
            api_key.revoked_at = None

    if rate_limit_per_minute is not None:
        api_key.rate_limit_per_minute = rate_limit_per_minute
    if monthly_token_quota is not None:
        api_key.monthly_token_quota = monthly_token_quota

    await db.flush()
    return _key_to_dict(api_key)
