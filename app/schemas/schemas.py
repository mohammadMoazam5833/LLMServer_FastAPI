"""
All Pydantic v2 schemas used across the API.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Any
from pydantic import BaseModel, Field, field_validator, ConfigDict


# ── Auth ───────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRefreshRequest(BaseModel):
    refresh_token: str


# ── API Key ────────────────────────────────────────────────────────────────────

class APIKeyCreate(BaseModel):
    name: str = ""


class APIKeyResponse(BaseModel):
    id: uuid.UUID
    name: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class APIKeyCreatedResponse(APIKeyResponse):
    raw_key: str   # returned ONLY on creation


# ── Chat ───────────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: Any
    images: list[str] = Field(default_factory=list)

    @field_validator("content", mode="before")
    @classmethod
    def normalize_content(cls, v):
        if v is None:
            return ""
        return v


class ChatFileReference(BaseModel):
    id: str
    type: str | None = None
    name: str | None = None


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str
    messages: list[ChatMessage]
    conversation_id: uuid.UUID | None = None
    files: list[ChatFileReference] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None
    max_tokens: int = Field(default=2048, ge=1, le=32768)
    stream: bool = False
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)


class ChatCompletionChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str = "stop"


class UsageStats(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionChoice]
    usage: UsageStats = Field(default_factory=UsageStats)
    conversation_id: str | None = None


# ── Streaming (SSE delta format) ───────────────────────────────────────────────

class DeltaContent(BaseModel):
    content: str = ""
    role: str | None = None


class StreamChoice(BaseModel):
    index: int = 0
    delta: DeltaContent
    finish_reason: str | None = None


class ChatCompletionChunk(BaseModel):
    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: list[StreamChoice]


# ── Models ─────────────────────────────────────────────────────────────────────

class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    owned_by: str = "local"


class ModelListResponse(BaseModel):
    object: str = "list"
    data: list[ModelInfo]


# ── Chat History ───────────────────────────────────────────────────────────────

class ConversationSummary(BaseModel):
    id: str
    title: str
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationDetail(BaseModel):
    id: str
    title: str
    messages: list[MessageOut]


class RAGFileResponse(BaseModel):
    id: uuid.UUID
    filename: str
    content_type: str
    status: str
    created_at: datetime
    chunk_count: int = 0


# ── Admin ──────────────────────────────────────────────────────────────────────

class AdminUserCreate(BaseModel):
    username: str
    password: str
    email: str = ""
    is_active: bool = True


class AdminUserUpdate(BaseModel):
    email: str | None = None
    is_active: bool | None = None


class AdminUserOut(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool
    key_count: int = 0


class AdminAPIKeyCreate(BaseModel):
    user_id: int
    name: str = ""
    rate_limit_per_minute: int = Field(default=180, ge=1)
    monthly_token_quota: int = Field(default=1_000_000, ge=0)


class AdminAPIKeyUpdate(BaseModel):
    is_active: bool | None = None
    rate_limit_per_minute: int | None = Field(default=None, ge=1)
    monthly_token_quota: int | None = Field(default=None, ge=0)


class AdminAPIKeyOut(BaseModel):
    id: uuid.UUID
    user_id: int
    username: str
    name: str
    key_hint: str = ""
    raw_key: str | None = None
    is_active: bool
    rate_limit_per_minute: int
    monthly_token_quota: int
    created_at: datetime
    revoked_at: datetime | None = None

    model_config = {"from_attributes": True}


class AdminAPIKeyCreatedResponse(AdminAPIKeyOut):
    raw_key: str


class UsageSummary(BaseModel):
    api_key_id: uuid.UUID
    user_id: int
    username: str
    key_name: str
    tokens_used: int
    monthly_token_quota: int
    percent_used: float
