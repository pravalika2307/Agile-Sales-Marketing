"""Authentication API endpoints: registration, login, session inspection, and token refresh."""
from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.database import get_db
from app.core.security import (
    ExpiredTokenError,
    InvalidCredentialsError,
    InvalidTokenError,
    InvalidTokenTypeError,
)
from app.models.tenant import Organization, User
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
)
from app.schemas.user import OrganizationResponse, UserResponse
from app.services.auth_service import (
    EmailAlreadyExistsError,
    InactiveUserError,
    authenticate_user,
    refresh_tokens,
    register_user,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register new organization and owner account",
    description="Atomically provisions an Organization, an Owner User account, and an initial Business Profile.",
)
async def register(
    request: RegisterRequest,
    db: Session = Depends(get_db),
) -> AuthResponse:
    try:
        user, org, tokens = register_user(db, request)
    except EmailAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error("Unexpected error during registration: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed due to an internal error. Please try again.",
        )

    return AuthResponse(
        user=UserResponse.model_validate(user),
        organization=OrganizationResponse.model_validate(org),
        tokens=tokens,
    )


@router.post(
    "/login",
    response_model=AuthResponse,
    status_code=status.HTTP_200_OK,
    summary="User login",
    description="Authenticates credentials and returns a new access and refresh token pair.",
)
async def login(
    request: LoginRequest,
    db: Session = Depends(get_db),
) -> AuthResponse:
    try:
        user, tokens = authenticate_user(db, request.email, request.password)
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except InactiveUserError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive. Please contact support.",
        )

    org = db.query(Organization).filter(Organization.id == user.organization_id).first()

    return AuthResponse(
        user=UserResponse.model_validate(user),
        organization=OrganizationResponse.model_validate(org) if org else None,
        tokens=tokens,
    )


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current authenticated user profile",
    description="Inspects the validated session and returns current user details.",
)
async def get_me(
    current_user: User = Depends(get_current_active_user),
) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Refresh session tokens",
    description="Validates a refresh token and issues a new access token.",
)
async def refresh_session(
    request: RefreshTokenRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    try:
        return refresh_tokens(db, request.refresh_token)
    except ExpiredTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except (InvalidTokenError, InvalidTokenTypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid refresh token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )
