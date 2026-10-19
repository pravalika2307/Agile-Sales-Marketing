"""Authentication API endpoints: registration, login, session inspection, and token refresh."""
from __future__ import annotations

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.cookie_utils import clear_auth_cookies, set_auth_cookies
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
    response: Response,
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

    set_auth_cookies(response, tokens.access_token, tokens.refresh_token)

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
    response: Response,
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

    set_auth_cookies(response, tokens.access_token, tokens.refresh_token)

    return AuthResponse(
        user=UserResponse.model_validate(user),
        organization=OrganizationResponse.model_validate(org) if org else None,
        tokens=tokens,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="User logout",
    description="Clears authentication cookies and invalidates current session.",
)
async def logout(response: Response) -> dict:
    clear_auth_cookies(response)
    return {"message": "Successfully logged out."}


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
    description="Validates a refresh token from JSON body or refresh_token cookie and issues a new token pair with updated cookies.",
)
async def refresh_session(
    response: Response,
    request: Request = None,  # type: ignore
    payload: Optional[RefreshTokenRequest] = None,
    db: Session = Depends(get_db),
) -> TokenResponse:
    raw_token: Optional[str] = None
    if payload and payload.refresh_token:
        raw_token = payload.refresh_token
    elif request and hasattr(request, "cookies") and "refresh_token" in request.cookies:
        raw_token = request.cookies.get("refresh_token")

    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token was not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        tokens = refresh_tokens(db, raw_token)
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

    set_auth_cookies(response, tokens.access_token, tokens.refresh_token)
    return tokens
