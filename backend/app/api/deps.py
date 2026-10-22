"""Reusable FastAPI dependencies for database sessions, authentication, and tenancy."""
from __future__ import annotations

import uuid
from typing import Generator, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import ExpiredTokenError, InvalidTokenError, InvalidTokenTypeError, decode_token
from app.models.tenant import Organization, User

# HTTP Bearer scheme with automatic Authorization header parsing
http_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request = None,  # type: ignore
    auth: Optional[HTTPAuthorizationCredentials] = Depends(http_bearer),
    db: Session = Depends(get_db),
) -> User:
    """
    Extract and validate JWT access token from Authorization header or auth_token cookie.
    Returns the authenticated User instance.
    """
    token: Optional[str] = None
    if isinstance(auth, HTTPAuthorizationCredentials) and auth.credentials:
        token = auth.credentials
    elif request and hasattr(request, "cookies") and "auth_token" in request.cookies:
        token = request.cookies.get("auth_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(token, expected_type="access")
        user_id_str = payload.get("sub")
        if not user_id_str:
            raise InvalidTokenError("Missing user identity in token")
        user_id = uuid.UUID(user_id_str)
    except ExpiredTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has expired. Please refresh your session.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except (InvalidTokenError, InvalidTokenTypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User associated with this token does not exist.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Ensure the authenticated user account is active."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive. Please contact support.",
        )
    return current_user


async def get_current_organization(
    request: Request = None,  # type: ignore
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    auth: Optional[HTTPAuthorizationCredentials] = Depends(http_bearer),
) -> Organization:
    """
    Resolve the tenant authority strictly from the authenticated user's organization_id
    or token org_id claim.
    Prevents cross-tenant parameter tampering.
    """
    target_org_id = current_user.organization_id

    # Verify token org_id claim if present
    raw_token = None
    if isinstance(auth, HTTPAuthorizationCredentials) and auth.credentials:
        raw_token = auth.credentials
    elif request and hasattr(request, "cookies") and "auth_token" in request.cookies:
        raw_token = request.cookies.get("auth_token")

    if raw_token:
        try:
            payload = decode_token(raw_token, expected_type="access")
            token_org_id = payload.get("org_id")
            if token_org_id:
                claimed_org_id = uuid.UUID(str(token_org_id))
                if claimed_org_id != current_user.organization_id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Cross-tenant access forbidden: token organization mismatch.",
                    )
        except HTTPException:
            raise
        except Exception:
            pass

    org = db.query(Organization).filter(Organization.id == target_org_id).first()

    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization associated with this account was not found.",
        )
    return org


async def get_current_admin_user(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Ensure the authenticated user has administrative privileges within their organization or platform."""
    if current_user.role not in ("owner", "admin", "superadmin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative privileges required to access this resource.",
        )
    return current_user


async def get_current_platform_admin_user(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Ensure the authenticated user is an authorized platform administrator."""
    if current_user.role not in ("superadmin", "platform_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform administrator privileges required to review and approve channel upgrades.",
        )
    return current_user



