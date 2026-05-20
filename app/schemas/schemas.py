"""
All Pydantic v2 schemas used across the API.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Any
from pydantic import BaseModel, Field, field_validator


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
    model: str
    messages: list[ChatMessage]
    conversation_id: uuid.UUID | None = None
    files: list[ChatFileReference] = Field(default_factory=list)
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
