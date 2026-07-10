from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.rate_limit import get_monthly_usage
from app.models.api_key import APIKey


def _percent_used(used: int, quota: int) -> float:
    if quota <= 0:
        return 0.0
    return round(min(100.0, (used / quota) * 100.0), 2)


async def _usage_row(api_key: APIKey, tokens_used: int) -> dict:
    quota = int(api_key.monthly_token_quota)
    return {
        "api_key_id": api_key.id,
        "user_id": api_key.user_id,
        "username": api_key.user.username if api_key.user else "",
        "key_name": api_key.name,
        "tokens_used": tokens_used,
        "monthly_token_quota": quota,
        "percent_used": _percent_used(tokens_used, quota),
    }


async def list_usage_summary(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(APIKey).options(selectinload(APIKey.user)).order_by(APIKey.created_at.desc())
    )
    keys = result.scalars().all()
    rows: list[dict] = []
    for api_key in keys:
        used = await get_monthly_usage(str(api_key.id))
        rows.append(await _usage_row(api_key, used))
    return rows


async def get_key_usage(db: AsyncSession, api_key_id: uuid.UUID) -> dict:
    result = await db.execute(
        select(APIKey)
        .where(APIKey.id == api_key_id)
        .options(selectinload(APIKey.user))
    )
    api_key = result.scalar_one_or_none()
    if api_key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")

    used = await get_monthly_usage(str(api_key.id))
    quota = int(api_key.monthly_token_quota)
    now = datetime.now(timezone.utc)
    return {
        **await _usage_row(api_key, used),
        "tokens_remaining": max(0, quota - used),
        "month": f"{now.year}-{now.month:02d}",
    }
