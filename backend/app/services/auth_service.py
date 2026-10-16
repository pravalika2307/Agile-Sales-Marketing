"""Authentication service managing registration, credential verification, and token issuance."""
from __future__ import annotations

import logging
import re
import secrets
import uuid
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.core.security import (
    InvalidCredentialsError,
    InvalidTokenError,
    InvalidTokenTypeError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.business import BusinessProfile
from app.models.crm import Pipeline, PipelineStage
from app.models.tenant import Organization, User
from app.schemas.auth import RegisterRequest, TokenResponse

logger = logging.getLogger(__name__)


# ── Service Domain Exceptions ─────────────────────────────────────────────────

class AuthServiceError(Exception):
    """Base exception for authentication service errors."""
    pass


class EmailAlreadyExistsError(AuthServiceError):
    """Raised when an email is already registered."""
    pass


class InactiveUserError(AuthServiceError):
    """Raised when an inactive user attempts to authenticate."""
    pass


# ── Helper: Slug Generation ───────────────────────────────────────────────────

def generate_organization_slug(db: Session, name: str) -> str:
    """
    Generate a URL-friendly, unique slug for an organization.
    Appends a random suffix if a slug collision occurs.
    """
    base_slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    if not base_slug:
        base_slug = "org"

    slug = base_slug
    counter = 1
    while db.query(Organization).filter(Organization.slug == slug).first() is not None:
        random_suffix = secrets.token_hex(2)
        slug = f"{base_slug}-{random_suffix}"
        counter += 1
        if counter > 10:
            slug = f"{base_slug}-{uuid.uuid4().hex[:6]}"
            break

    return slug


# ── Core Service Functions ────────────────────────────────────────────────────

def register_user(
    db: Session,
    request: RegisterRequest,
) -> Tuple[User, Organization, TokenResponse]:
    """
    Atomically register an Organization, Owner User, and default BusinessProfile.
    Returns the created User, Organization, and initial Token pair.
    """
    clean_email = request.email.strip().lower()

    # 1. Check duplicate email
    existing_user = db.query(User).filter(User.email == clean_email).first()
    if existing_user:
        raise EmailAlreadyExistsError(f"Email '{clean_email}' is already registered.")

    # 2. Transactional creation
    try:
        slug = generate_organization_slug(db, request.organization_name)
        org = Organization(
            name=request.organization_name.strip(),
            slug=slug,
            billing_status="trial",
        )
        db.add(org)
        db.flush()  # Populates org.id

        hashed_pw = hash_password(request.password)
        user = User(
            organization_id=org.id,
            email=clean_email,
            hashed_password=hashed_pw,
            full_name=request.full_name.strip(),
            role="owner",
            is_active=True,
        )
        db.add(user)

        profile = BusinessProfile(
            organization_id=org.id,
            company_name=request.organization_name.strip(),
        )
        db.add(profile)

        # Default Sales Pipeline & Stages
        default_pipeline = Pipeline(
            organization_id=org.id,
            name="Default Sales Pipeline",
            is_default=True,
        )
        db.add(default_pipeline)
        db.flush()  # Populates default_pipeline.id

        default_stages = [
            PipelineStage(
                pipeline_id=default_pipeline.id,
                name="Discovery",
                order_index=1,
                probability_pct=10,
            ),
            PipelineStage(
                pipeline_id=default_pipeline.id,
                name="Qualified",
                order_index=2,
                probability_pct=25,
            ),
            PipelineStage(
                pipeline_id=default_pipeline.id,
                name="Demo",
                order_index=3,
                probability_pct=50,
            ),
            PipelineStage(
                pipeline_id=default_pipeline.id,
                name="Proposal",
                order_index=4,
                probability_pct=70,
            ),
            PipelineStage(
                pipeline_id=default_pipeline.id,
                name="Won",
                order_index=5,
                probability_pct=100,
            ),
        ]
        db.add_all(default_stages)

        db.commit()
        db.refresh(user)
        db.refresh(org)

    except Exception as exc:
        db.rollback()
        logger.error("Registration failed, transaction rolled back: %s", exc)
        raise

    # 3. Generate tokens
    access_token = create_access_token(
        user_id=user.id,
        organization_id=org.id,
        role=user.role,
    )
    refresh_token = create_refresh_token(
        user_id=user.id,
        organization_id=org.id,
    )

    tokens = TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )
    return user, org, tokens


def authenticate_user(
    db: Session,
    email: str,
    password: str,
) -> Tuple[User, TokenResponse]:
    """
    Authenticate a user by email and password.
    Returns the User and newly generated Token pair.
    """
    clean_email = email.strip().lower()
    user = db.query(User).filter(User.email == clean_email).first()

    if not user or not verify_password(password, user.hashed_password):
        raise InvalidCredentialsError("Invalid email or password.")

    if not user.is_active:
        raise InactiveUserError("User account is inactive. Please contact support.")

    access_token = create_access_token(
        user_id=user.id,
        organization_id=user.organization_id,
        role=user.role,
    )
    refresh_token = create_refresh_token(
        user_id=user.id,
        organization_id=user.organization_id,
    )

    tokens = TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )
    return user, tokens


def refresh_tokens(
    db: Session,
    refresh_token: str,
) -> TokenResponse:
    """
    Validate a refresh token and issue a new access token and rotating refresh token.
    """
    payload = decode_token(refresh_token, expected_type="refresh")

    try:
        user_id = uuid.UUID(payload["sub"])
    except (ValueError, KeyError) as exc:
        raise InvalidTokenError("Invalid user identity in token") from exc

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise InvalidTokenError("User associated with this token does not exist or is inactive.")

    new_access_token = create_access_token(
        user_id=user.id,
        organization_id=user.organization_id,
        role=user.role,
    )
    new_refresh_token = create_refresh_token(
        user_id=user.id,
        organization_id=user.organization_id,
    )

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
    )
