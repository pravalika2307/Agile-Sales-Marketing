"""
Cookie utility functions for handling auth tokens, adapted from Agile Receivables.
"""
from typing import Optional
from fastapi import Response
from app.core.config import settings

def set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
    access_token_expires_in: Optional[int] = None,
    refresh_token_expires_in: Optional[int] = None,
) -> None:
    """
    Set authentication cookies in the response.
    
    Args:
        response: FastAPI Response object
        access_token: JWT access token
        refresh_token: JWT refresh token
        access_token_expires_in: Access token expiry in seconds (defaults to settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)
        refresh_token_expires_in: Refresh token expiry in seconds (defaults to settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400)
    """
    access_expiry = (
        access_token_expires_in
        if access_token_expires_in is not None
        else settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
    refresh_expiry = (
        refresh_token_expires_in
        if refresh_token_expires_in is not None
        else settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
    )
    cookie_domain_from_env = getattr(settings, "COOKIE_DOMAIN", None)

    if cookie_domain_from_env:
        # Hosted environment (staging/production) with a real domain
        cookie_domain = cookie_domain_from_env
        samesite = "none"
        secure = True
    else:
        # Local-only environment (localhost), don't set a domain and use lax
        cookie_domain = None
        samesite = "lax"
        secure = settings.ENVIRONMENT == "production"
    
    # Set auth token cookie
    response.set_cookie(
        key="auth_token",
        value=access_token,
        httponly=True,
        max_age=access_expiry,
        path="/",
        samesite=samesite,
        secure=secure,
        domain=cookie_domain,
    )
    
    # Set refresh token cookie
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        max_age=refresh_expiry,
        path="/",
        samesite=samesite,
        secure=secure,
        domain=cookie_domain,
    )

def clear_auth_cookies(response: Response) -> None:
    """
    Clear authentication cookies from the response.
    
    Args:
        response: FastAPI Response object
    """
    cookie_domain_from_env = getattr(settings, "COOKIE_DOMAIN", None)
    cookie_domain = cookie_domain_from_env if cookie_domain_from_env else None
    response.delete_cookie("auth_token", path="/", domain=cookie_domain)
    response.delete_cookie("refresh_token", path="/", domain=cookie_domain)
    # Also delete without domain to handle environment changes
    response.delete_cookie("auth_token", path="/", domain=None)
    response.delete_cookie("refresh_token", path="/", domain=None)
