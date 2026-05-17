"""
Security helpers:
  - password hashing  (bcrypt via passlib)
  - JWT create / decode
  - API key generation / hashing
"""
import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import jwt, JWTError
from passlib.context import CryptContext

from app.config import get_settings

settings = get_settings()




# ── Password ───────────────────────────────────────────────────────────────────
_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_ctx.verify(plain, hashed)


# ── JWT ────────────────────────────────────────────────────────────────────────

def _encode(payload: dict[str, Any]) -> str:
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(subject: str | int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return _encode({"sub": str(subject), "type": "access", "exp": expire})


def create_refresh_token(subject: str | int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    return _encode({"sub": str(subject), "type": "refresh", "exp": expire})


def decode_token(token: str) -> dict[str, Any]:
    """
    Raises jose.JWTError on invalid / expired tokens.
    Caller is responsible for catching.
    """
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


# ── API Key ────────────────────────────────────────────────────────────────────

def generate_api_key() -> str:
    """Returns a cryptographically secure random API key with prefix."""
    return settings.API_KEY_PREFIX + secrets.token_urlsafe(32)


def hash_api_key(raw_key: str) -> str:
    """SHA-256 hash stored in the DB — never store raw keys."""
    return hashlib.sha256(raw_key.encode()).hexdigest()
