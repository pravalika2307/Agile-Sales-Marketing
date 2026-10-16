"""Security utilities: password hashing (Argon2) and JWT token management."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import argon2
import argon2.exceptions
import jwt

from app.core.config import settings

logger = logging.getLogger(__name__)

# Password hasher using modern Argon2id
_hasher = argon2.PasswordHasher(
    time_cost=2,
    memory_cost=19456,  # 19 MiB
    parallelism=1,
    hash_len=32,
    type=argon2.Type.ID,
)


# ── Typed Security Exceptions ─────────────────────────────────────────────────

class SecurityError(Exception):
    """Base exception for security operations."""
    pass


class InvalidCredentialsError(SecurityError):
    """Raised when authentication credentials (password) are invalid."""
    pass


class TokenError(SecurityError):
    """Base exception for token failures."""
    pass


class ExpiredTokenError(TokenError):
    """Raised when a JWT token has expired."""
    pass


class InvalidTokenError(TokenError):
    """Raised when a JWT token is malformed, has invalid signature, or invalid claims."""
    pass


class InvalidTokenTypeError(TokenError):
    """Raised when a token of unexpected type is presented (e.g. access token as refresh)."""
    pass


# ── Password Hashing & Verification ───────────────────────────────────────────

def hash_password(password: str) -> str:
    """
    Hash a plaintext password using Argon2id.
    Never stores or logs the plaintext password.
    """
    if not password:
        raise ValueError("Password cannot be empty")
    return _hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plaintext password against an Argon2id hash using constant-time comparison.
    Returns True if valid, False otherwise.
    """
    if not plain_password or not hashed_password:
        return False
    try:
        return _hasher.verify(hashed_password, plain_password)
    except argon2.exceptions.VerifyMismatchError:
        return False
    except Exception as exc:
        logger.warning("Unexpected password verification error: %s", type(exc).__name__)
        return False


# ── JWT Token Creation & Decoding ─────────────────────────────────────────────

def create_access_token(
    user_id: str | uuid.UUID,
    organization_id: str | uuid.UUID,
    role: str = "member",
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Generate a signed JWT access token.
    Claims: sub (user_id), org_id, role, type="access", exp, iat
    """
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))

    payload: Dict[str, Any] = {
        "sub": str(user_id),
        "org_id": str(organization_id),
        "role": role,
        "type": "access",
        "exp": expire,
        "iat": now,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(
    user_id: str | uuid.UUID,
    organization_id: str | uuid.UUID,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Generate a signed JWT refresh token.
    Claims: sub (user_id), org_id, type="refresh", jti (unique UUID), exp, iat
    """
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS))

    payload: Dict[str, Any] = {
        "sub": str(user_id),
        "org_id": str(organization_id),
        "type": "refresh",
        "jti": str(uuid.uuid4()),
        "exp": expire,
        "iat": now,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str, expected_type: Optional[str] = None) -> Dict[str, Any]:
    """
    Decode and validate a JWT token.
    Verifies signature, expiration, algorithm, and optionally token type.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["sub", "org_id", "type", "exp"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise ExpiredTokenError("Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError(f"Invalid token: {exc}") from exc

    token_type = payload.get("type")
    if expected_type and token_type != expected_type:
        raise InvalidTokenTypeError(
            f"Expected token of type '{expected_type}', got '{token_type}'"
        )

    return payload
