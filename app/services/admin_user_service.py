from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.api_key import APIKey
from app.models.user import User


async def list_users(db: AsyncSession) -> list[dict]:
    key_count_subq = (
        select(APIKey.user_id, func.count(APIKey.id).label("key_count"))
        .group_by(APIKey.user_id)
        .subquery()
    )
    result = await db.execute(
        select(User, func.coalesce(key_count_subq.c.key_count, 0).label("key_count"))
        .outerjoin(key_count_subq, User.id == key_count_subq.c.user_id)
        .order_by(User.id)
    )
    rows = result.all()
    return [
        {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_active": user.is_active,
            "key_count": int(key_count),
        }
        for user, key_count in rows
    ]


async def create_user(
    db: AsyncSession,
    *,
    username: str,
    password: str,
    email: str = "",
    is_active: bool = True,
) -> User:
    existing = await db.execute(select(User).where(User.username == username))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists",
        )

    user = User(
        username=username,
        password=hash_password(password),
        email=email,
        is_active=is_active,
    )
    db.add(user)
    await db.flush()
    return user


async def update_user(
    db: AsyncSession,
    user_id: int,
    *,
    email: str | None = None,
    is_active: bool | None = None,
) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if email is not None:
        user.email = email
    if is_active is not None:
        user.is_active = is_active

    await db.flush()
    return user
