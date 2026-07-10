import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, BigInteger, Integer, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.database import Base


class APIKey(Base):
    __tablename__ = "api_keys_apikey"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users_user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(64), default="")
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    key_hint: Mapped[str] = mapped_column(String(32), default="")
    key_encrypted: Mapped[str] = mapped_column(String(512), default="")

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, default=180)
    monthly_token_quota: Mapped[int] = mapped_column(BigInteger, default=1_000_000)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────────
    user: Mapped["User"] = relationship("User", back_populates="api_keys")  # noqa: F821

    def __repr__(self) -> str:
        return f"<APIKey {self.name or self.id}>"
