"""Unit tests for password hashing (Argon2) and JWT token operations."""
import uuid
from datetime import timedelta
import pytest

from app.core.security import (
    ExpiredTokenError,
    InvalidTokenError,
    InvalidTokenTypeError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hashing_and_verification():
    raw_password = "SuperSecretPassword123!"
    hashed = hash_password(raw_password)

    # Hash must not equal raw password
    assert hashed != raw_password
    # Argon2id identifier prefix
    assert hashed.startswith("$argon2id$")

    # Correct password succeeds
    assert verify_password(raw_password, hashed) is True
    # Wrong password fails
    assert verify_password("WrongPassword999!", hashed) is False
    # Empty string fails
    assert verify_password("", hashed) is False


def test_access_token_claims_and_decoding():
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()

    token = create_access_token(user_id=user_id, organization_id=org_id, role="owner")
    payload = decode_token(token, expected_type="access")

    assert payload["sub"] == str(user_id)
    assert payload["org_id"] == str(org_id)
    assert payload["role"] == "owner"
    assert payload["type"] == "access"
    assert "exp" in payload
    assert "iat" in payload


def test_refresh_token_claims_and_jti():
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()

    token = create_refresh_token(user_id=user_id, organization_id=org_id)
    payload = decode_token(token, expected_type="refresh")

    assert payload["sub"] == str(user_id)
    assert payload["org_id"] == str(org_id)
    assert payload["type"] == "refresh"
    assert "jti" in payload
    assert len(payload["jti"]) > 0


def test_expired_token_raises_expired_error():
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()

    # Create token already expired 10 seconds ago
    token = create_access_token(
        user_id=user_id,
        organization_id=org_id,
        expires_delta=timedelta(seconds=-10),
    )

    with pytest.raises(ExpiredTokenError):
        decode_token(token)


def test_malformed_token_raises_invalid_error():
    with pytest.raises(InvalidTokenError):
        decode_token("this.is.a.completely.malformed.token")


def test_token_type_mismatch_raises_error():
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()

    access_token = create_access_token(user_id=user_id, organization_id=org_id)

    # Expecting refresh token but passing access token
    with pytest.raises(InvalidTokenTypeError):
        decode_token(access_token, expected_type="refresh")
