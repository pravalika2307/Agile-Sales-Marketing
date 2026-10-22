"""Exceptions for Microsoft Graph Integration."""
from __future__ import annotations

from typing import Optional


class GraphClientError(Exception):
    """Base exception for all Microsoft Graph client errors."""
    pass


class GraphAuthenticationError(GraphClientError):
    """Raised when Microsoft Entra ID authentication fails (expired secret, invalid tenant, invalid client ID)."""
    pass


class GraphPermissionError(GraphClientError):
    """Raised when Microsoft Graph returns 403 Forbidden due to missing or unconsented application/delegated scopes."""
    pass


class GraphThrottlingError(GraphClientError):
    """Raised when Microsoft Graph throttles requests (HTTP 429 Too Many Requests)."""
    def __init__(self, message: str, retry_after: Optional[int] = None):
        super().__init__(message)
        self.retry_after = retry_after


class GraphMailboxNotFoundError(GraphClientError):
    """Raised when the specified target mailbox does not exist in Microsoft 365 Exchange Online (HTTP 404)."""
    pass


class GraphSecurityError(GraphClientError):
    """Raised when URL validation fails, SSRF is attempted, or unexpected redirects occur."""
    pass


class GraphMailboxScopeError(GraphSecurityError):
    """Raised when access to an unauthorized or non-approved mailbox is attempted."""
    pass


class GraphDeltaTokenExpiredError(GraphClientError):
    """Raised when Microsoft Graph returns HTTP 410 Gone indicating a delta token has expired."""
    pass


class GraphAPIError(GraphClientError):
    """Generic error returned by Microsoft Graph REST API."""
    def __init__(self, message: str, status_code: Optional[int] = None, error_code: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
