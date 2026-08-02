import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    String, Boolean, Integer, BigInteger, Text,
    ForeignKey, DateTime, JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.database import Base


class LLMConnection(Base):
    """
    Upstream LLM endpoint (LiteLLM-style provider/connection).

    Phase 1: provider_type=openai_compatible (vLLM, TGI, etc.).
    """
    __tablename__ = "llm_llmconnection"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, comment="Slug id, e.g. local-vllm"
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_type: Mapped[str] = mapped_column(
        String(64), default="openai_compatible", nullable=False
    )
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    api_key_hint: Mapped[str] = mapped_column(String(32), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    models: Mapped[list["LLMModel"]] = relationship(
        "LLMModel", back_populates="connection"
    )

    def __repr__(self) -> str:
        return f"<LLMConnection {self.id}>"


class LLMModel(Base):
    """Represents an available LLM model in the system."""
    __tablename__ = "llm_llmmodel"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, comment="Public model id, e.g. code-bot-v1"
    )
    model_path: Mapped[str] = mapped_column(String(255), nullable=False)
    # Per-model OpenAI-compatible base, e.g. http://llm-vllm-a:8003/v1
    # Empty/null → connection.base_url → settings.VLLM_BASE_URL
    base_url: Mapped[str | None] = mapped_column(String(512), nullable=True, default=None)
    connection_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("llm_llmconnection.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(32), default="local")
    context_length: Mapped[int] = mapped_column(Integer, default=8192)
    max_output_tokens: Mapped[int] = mapped_column(Integer, default=2048)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Ordered public model ids to try if this deployment fails (LiteLLM-style fallbacks).
    fallback_model_ids: Mapped[list] = mapped_column(JSON, default=list)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    connection: Mapped["LLMConnection | None"] = relationship(
        "LLMConnection", back_populates="models"
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        "Conversation", back_populates="model"
    )

    def __repr__(self) -> str:
        return f"<LLMModel {self.id}>"


class Conversation(Base):
    """Represents a chat session."""
    __tablename__ = "llm_conversation"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users_user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("llm_llmmodel.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), default="")
    system_prompt: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ── Relationships ──────────────────────────────────────────────────────────
    user: Mapped["User"] = relationship("User", back_populates="conversations")  # noqa: F821
    model: Mapped["LLMModel"] = relationship("LLMModel", back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan",
        order_by="Message.created_at"
    )

    def __repr__(self) -> str:
        return f"<Conversation {self.id}>"


class Message(Base):
    """A single message in a conversation."""
    __tablename__ = "llm_message"

    ROLE_SYSTEM = "system"
    ROLE_USER = "user"
    ROLE_ASSISTANT = "assistant"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("llm_conversation.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")

    def __repr__(self) -> str:
        return f"<Message {self.role}@{self.conversation_id}>"


class UploadedFile(Base):
    """Uploaded document for RAG."""
    __tablename__ = "llm_uploadedfile"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:
        return f"<UploadedFile {self.filename}>"


class RAGFile(Base):
    """A user-uploaded file prepared for retrieval."""
    __tablename__ = "rag_file"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users_user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), default="")
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="uploaded")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    chunks: Mapped[list["RAGChunk"]] = relationship(
        "RAGChunk", back_populates="file", cascade="all, delete-orphan",
        order_by="RAGChunk.chunk_index"
    )


class RAGChunk(Base):
    """A searchable text chunk extracted from a RAG file."""
    __tablename__ = "rag_chunk"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    file_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("rag_file.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    file: Mapped["RAGFile"] = relationship("RAGFile", back_populates="chunks")
