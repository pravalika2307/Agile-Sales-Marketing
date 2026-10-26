"""Cryptographically secure token-at-rest encryption service for LinkedIn integration.

Uses AES-128-CBC with HMAC-SHA256 via Fernet authenticated symmetric encryption.
Key material is securely derived via HKDF-SHA256 from the application SECRET_KEY
or supplied via an explicitly configured LINKEDIN_TOKEN_ENCRYPTION_KEY.
Tokens are encrypted before persistence in database records and never printed or logged.
"""
from __future__ import annotations

import base64
import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import settings

logger = logging.getLogger(__name__)

# Domain separation parameters for HKDF key derivation
HKDF_SALT = b"agile_linkedin_tokens_v1"
HKDF_INFO = b"token_encryption"


def get_encryption_key() -> bytes:
    """
    Resolve the 32-byte urlsafe base64-encoded Fernet key.
    If LINKEDIN_TOKEN_ENCRYPTION_KEY is configured in settings, validates and uses it.
    Otherwise, deterministically derives a cryptographically secure key from settings.SECRET_KEY
    using HKDF-SHA256 with domain separation.
    """
    explicit_key = getattr(settings, "LINKEDIN_TOKEN_ENCRYPTION_KEY", None)
    if explicit_key and explicit_key.strip():
        raw_key = explicit_key.strip().encode("utf-8")
        try:
            # Validate key format with Fernet
            Fernet(raw_key)
            return raw_key
        except Exception as exc:
            logger.warning(
                "Configured LINKEDIN_TOKEN_ENCRYPTION_KEY is invalid (%s); falling back to HKDF key derivation.",
                type(exc).__name__,
            )

    # Derive 32-byte key from application SECRET_KEY
    secret_bytes = settings.SECRET_KEY.encode("utf-8")
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=HKDF_SALT,
        info=HKDF_INFO,
    )
    derived_32 = hkdf.derive(secret_bytes)
    return base64.urlsafe_b64encode(derived_32)


def encrypt_token(token: Optional[str]) -> Optional[str]:
    """
    Encrypt a plaintext token using Fernet authenticated symmetric encryption.
    Returns the ciphertext string (URL-safe base64).
    Returns None if token is None or empty.
    Never logs or leaks the plaintext token.
    """
    if not token or not token.strip():
        return None

    key = get_encryption_key()
    fernet = Fernet(key)
    encrypted_bytes = fernet.encrypt(token.strip().encode("utf-8"))
    return encrypted_bytes.decode("utf-8")


def decrypt_token(ciphertext: Optional[str]) -> Optional[str]:
    """
    Decrypt a Fernet ciphertext back to plaintext token.
    Returns None if ciphertext is None or empty.
    Raises ValueError if ciphertext has an invalid signature or has been tampered with.
    Never logs or leaks the decrypted token.
    """
    if not ciphertext or not ciphertext.strip():
        return None

    key = get_encryption_key()
    fernet = Fernet(key)
    try:
        decrypted_bytes = fernet.decrypt(ciphertext.strip().encode("utf-8"))
        return decrypted_bytes.decode("utf-8")
    except InvalidToken as exc:
        logger.error("Token decryption failed: ciphertext is invalid or tampered with.")
        raise ValueError("Decryption failed: invalid or tampered token ciphertext") from exc
