"""
Admin API endpoints.
Auth: JWT Bearer + require_superuser.
Mounted at: /api/v1/admin
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_superuser
from app.database import get_db
from app.models.api_key import APIKey
from app.models.user import User
from app.schemas.schemas import (
    AdminUserCreate,
    AdminUserUpdate,
    AdminUserOut,
    AdminAPIKeyCreate,
    AdminAPIKeyUpdate,
    AdminAPIKeyOut,
    AdminAPIKeyCreatedResponse,
    UsageSummary,
)
from app.services import admin_user_service, admin_key_service, admin_usage_service

router = APIRouter(tags=["Admin"])


# ── Users ──────────────────────────────────────────────────────────────────────

@router.get("/users", response_model=list[AdminUserOut])
async def admin_list_users(
    _: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
):
    return await admin_user_service.list_users(db)


@router.post("/users", response_model=AdminUserOut, status_code=201)
async def admin_create_user(
    body: AdminUserCreate,
    _: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
):
    user = await admin_user_service.create_user(
        db,
        username=body.username,
        password=body.password,
        email=body.email,
        is_active=body.is_active,
    )
    return AdminUserOut(
        id=user.id,
        username=user.username,
        email=user.email,
        is_active=user.is_active,
        key_count=0,
    )


@router.patch("/users/{user_id}", response_model=AdminUserOut)
async def admin_update_user(
    user_id: int,
    body: AdminUserUpdate,
    _: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
):
    user = await admin_user_service.update_user(
        db,
        user_id,
        email=body.email,
        is_active=body.is_active,
    )
    key_count = await db.scalar(
        select(func.count()).select_from(APIKey).where(APIKey.user_id == user_id)
    )
    return AdminUserOut(
        id=user.id,
        username=user.username,
        email=user.email,
        is_active=user.is_active,
        key_count=key_count or 0,
    )


# ── API Keys ───────────────────────────────────────────────────────────────────

@router.get("/api-keys", response_model=list[AdminAPIKeyOut])
async def admin_list_api_keys(
    user_id: int | None = Query(default=None),
    _: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
):
    return await admin_key_service.list_api_keys(db, user_id=user_id)


@router.post("/api-keys", response_model=AdminAPIKeyCreatedResponse, status_code=201)
async def admin_create_api_key(
    body: AdminAPIKeyCreate,
    _: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
):
    key_data, raw_key = await admin_key_service.create_api_key_for_user(
        db,
        user_id=body.user_id,
        name=body.name,
        rate_limit_per_minute=body.rate_limit_per_minute,
        monthly_token_quota=body.monthly_token_quota,
    )
    key_data = {**key_data, "raw_key": raw_key}
    return AdminAPIKeyCreatedResponse(**key_data)


@router.patch("/api-keys/{key_id}", response_model=AdminAPIKeyOut)
async def admin_update_api_key(
    key_id: uuid.UUID,
    body: AdminAPIKeyUpdate,
    _: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
):
    return await admin_key_service.update_api_key(
        db,
        key_id,
        is_active=body.is_active,
        rate_limit_per_minute=body.rate_limit_per_minute,
        monthly_token_quota=body.monthly_token_quota,
    )


# ── Usage ──────────────────────────────────────────────────────────────────────

@router.get("/usage", response_model=list[UsageSummary])
async def admin_usage_summary(
    _: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
):
    return await admin_usage_service.list_usage_summary(db)


@router.get("/usage/{api_key_id}")
async def admin_key_usage(
    api_key_id: uuid.UUID,
    _: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
):
    return await admin_usage_service.get_key_usage(db, api_key_id)
