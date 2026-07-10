"""
Security helpers:
  - password hashing  (bcrypt via passlib)
  - JWT create / decode
  - API key generation / hashing
"""
import secrets
import hashlib
import base64
from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from jose import jwt, JWTError
from passlib.context import CryptContext
from passlib.exc import UnknownHashError

from app.config import get_settings

settings = get_settings()




# ── Password ───────────────────────────────────────────────────────────────────
# Existing users have Django pbkdf2_sha256 hashes in the database, so accept that
# scheme plus bcrypt for new passwords.
_pwd_ctx = CryptContext(schemes=["django_pbkdf2_sha256", "bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _pwd_ctx.verify(plain, hashed)
    except UnknownHashError:
        return False


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


def mask_api_key(raw_key: str) -> str:
    """Display hint only, e.g. sk-ab12…xy89 (not reversible)."""
    if len(raw_key) <= 12:
        return raw_key[:3] + "…"
    return f"{raw_key[:7]}…{raw_key[-4:]}"


def _api_key_fernet() -> Fernet:
    digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_api_key(raw_key: str) -> str:
    """Reversible encryption for admin key display (superuser only)."""
    return _api_key_fernet().encrypt(raw_key.encode()).decode()


def decrypt_api_key(encrypted: str | None) -> str | None:
    if not encrypted:
        return None
    try:
        return _api_key_fernet().decrypt(encrypted.encode()).decode()
    except InvalidToken:
        return None
