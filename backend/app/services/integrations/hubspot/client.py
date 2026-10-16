"""HubSpot API Client.

Handles HTTP communication, authentication, base URL configuration, timeouts,
and error handling with HubSpot CRM API v3. Ensures tokens are never leaked or logged.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class HubSpotError(Exception):
    """Base exception for HubSpot integration errors."""
    pass


class HubSpotConfigurationError(HubSpotError):
    """Raised when required HubSpot configuration is missing."""
    pass


class HubSpotAuthenticationError(HubSpotError):
    """Raised when authentication fails (HTTP 401)."""
    def __init__(self, message: str = "Invalid or expired HubSpot credentials", status_code: int = 401) -> None:
        super().__init__(message)
        self.status_code = status_code


class HubSpotPermissionError(HubSpotError):
    """Raised when access is forbidden due to missing scopes or permissions (HTTP 403)."""
    def __init__(
        self,
        message: str = "HubSpot access forbidden (missing required scopes)",
        required_scopes: Optional[List[str]] = None,
        correlation_id: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = 403
        self.required_scopes = required_scopes or []
        self.correlation_id = correlation_id


class HubSpotNotFoundError(HubSpotError):
    """Raised when requested object does not exist (HTTP 404)."""
    def __init__(self, message: str = "HubSpot resource not found", resource_id: Optional[str] = None) -> None:
        super().__init__(message)
        self.resource_id = resource_id


class HubSpotConflictError(HubSpotError):
    """Raised on resource conflict / duplicate (HTTP 409)."""
    def __init__(self, message: str, existing_id: Optional[str] = None, response_text: str = "") -> None:
        super().__init__(message)
        self.existing_id = existing_id
        self.response_text = response_text


class HubSpotRateLimitError(HubSpotError):
    """Raised when rate limit is exceeded (HTTP 429)."""
    pass


class HubSpotTimeoutError(HubSpotError):
    """Raised when HubSpot API request times out."""
    pass


class HubSpotAPIError(HubSpotError):
    """Raised when HubSpot API returns an unexpected error."""
    def __init__(self, status_code: int, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(f"HubSpot API error ({status_code}): {message}")
        self.status_code = status_code
        self.details = details or {}


class HubSpotClient:
    """Async HTTP client for HubSpot CRM API v3."""

    def __init__(
        self,
        access_token: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self._access_token = access_token if access_token is not None else settings.HUBSPOT_ACCESS_TOKEN
        self.base_url = (base_url or settings.HUBSPOT_BASE_URL).rstrip("/")
        self.timeout = timeout if timeout is not None else settings.HUBSPOT_TIMEOUT_SECONDS

    @property
    def is_configured(self) -> bool:
        """Verify if the client has a configured access token."""
        return bool(self._access_token and self._access_token.strip())

    def __repr__(self) -> str:
        # Guarantee that access token is NEVER printed or logged
        configured = self.is_configured
        return f"<HubSpotClient base_url='{self.base_url}' configured={configured} timeout={self.timeout}>"

    def _auth_headers(self) -> Dict[str, str]:
        """Construct authorization and content headers without exposing secrets."""
        if not self.is_configured:
            raise HubSpotConfigurationError("HUBSPOT_ACCESS_TOKEN is not configured.")
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _url(self, path: str) -> str:
        """Resolve full URL from path."""
        clean_path = path if path.startswith("/") else f"/{path}"
        return f"{self.base_url}{clean_path}"

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        check_status: bool = True,
    ) -> httpx.Response:
        """
        Execute an HTTP request against HubSpot API with timeout and error mapping.
        """
        url = self._url(path)
        headers = self._auth_headers()

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.request(
                    method=method.upper(),
                    url=url,
                    headers=headers,
                    params=params,
                    json=json_data,
                )

            if check_status and not resp.is_success:
                self._handle_error_response(resp, path)

            return resp

        except httpx.TimeoutException as exc:
            logger.error("HubSpot request timed out for path: %s", path)
            raise HubSpotTimeoutError(f"HubSpot request timed out after {self.timeout}s") from exc
        except httpx.RequestError as exc:
            logger.error("HubSpot request network failure for path %s: %s", path, exc)
            raise HubSpotError(f"Network error connecting to HubSpot: {exc}") from exc

    def _handle_error_response(self, resp: httpx.Response, path: str) -> None:
        """Map HTTP error status codes to typed exceptions."""
        status = resp.status_code
        error_json: Dict[str, Any] = {}
        error_msg = f"HTTP {status}"

        try:
            error_json = resp.json()
            error_msg = error_json.get("message", error_msg)
        except Exception:
            error_msg = resp.text[:300] if resp.text else error_msg

        if status == 403:
            required_scopes = []
            for err in error_json.get("errors", []):
                reqs = err.get("context", {}).get("requiredGranularScopes", [])
                if reqs:
                    required_scopes.extend(reqs)
            logger.warning("HubSpot permission forbidden (403): %s, required_scopes=%s", error_msg, required_scopes)
            raise HubSpotPermissionError(
                message=error_msg,
                required_scopes=required_scopes,
                correlation_id=error_json.get("correlationId"),
            )
        elif status == 401:
            logger.warning("HubSpot authentication failed: %d - %s", status, error_msg)
            raise HubSpotAuthenticationError(f"Authentication failed: {error_msg}", status_code=status)
        elif status == 404:
            logger.info("HubSpot resource not found: %s", path)
            raise HubSpotNotFoundError(f"Resource not found: {path}")
        elif status == 409:
            logger.info("HubSpot conflict error on path %s: %s", path, error_msg)
            raise HubSpotConflictError(f"Resource conflict: {error_msg}", response_text=resp.text)
        elif status == 429:
            logger.warning("HubSpot rate limit exceeded: %s", error_msg)
            raise HubSpotRateLimitError(f"HubSpot rate limit exceeded: {error_msg}")
        else:
            logger.warning("HubSpot API error %d on path %s: %s", status, path, error_msg)
            raise HubSpotAPIError(status_code=status, message=error_msg, details=error_json)

    # ── High-Level HTTP Helpers ───────────────────────────────────────────────

    async def get(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        check_status: bool = True,
    ) -> httpx.Response:
        return await self.request("GET", path, params=params, check_status=check_status)

    async def post(
        self,
        path: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        check_status: bool = True,
    ) -> httpx.Response:
        return await self.request("POST", path, params=params, json_data=json_data, check_status=check_status)

    async def patch(
        self,
        path: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        check_status: bool = True,
    ) -> httpx.Response:
        return await self.request("PATCH", path, params=params, json_data=json_data, check_status=check_status)

    async def put(
        self,
        path: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        check_status: bool = True,
    ) -> httpx.Response:
        return await self.request("PUT", path, params=params, json_data=json_data, check_status=check_status)

    async def delete(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        check_status: bool = True,
    ) -> httpx.Response:
        return await self.request("DELETE", path, params=params, check_status=check_status)

    # ── Connection Probe ──────────────────────────────────────────────────────

    async def validate_credentials(self) -> Dict[str, Any]:
        """
        Lightweight connection check against GET /crm/v3/owners?limit=1.
        Proves token validity and basic CRM read scopes without modifying any data.
        """
        if not self.is_configured:
            return {
                "success": False,
                "status_code": 0,
                "message": "HubSpot access token is not configured.",
                "details": None,
            }

        try:
            resp = await self.get("/crm/v3/owners", params={"limit": 1}, check_status=False)
            if resp.status_code == 200:
                data = resp.json()
                owner_count = len(data.get("results", []))
                return {
                    "success": True,
                    "status_code": 200,
                    "message": "HubSpot connection verified successfully.",
                    "details": {
                        "owners_sampled": owner_count,
                        "status_code": 200,
                    },
                }
            elif resp.status_code in (401, 403):
                return {
                    "success": False,
                    "status_code": resp.status_code,
                    "message": f"HubSpot authentication failed (HTTP {resp.status_code}). Token may be invalid or expired.",
                    "details": {"status_code": resp.status_code},
                }
            else:
                return {
                    "success": False,
                    "status_code": resp.status_code,
                    "message": f"HubSpot API returned HTTP {resp.status_code}.",
                    "details": {"status_code": resp.status_code, "body": resp.text[:200]},
                }
        except HubSpotTimeoutError:
            return {
                "success": False,
                "status_code": 408,
                "message": "HubSpot API request timed out.",
                "details": None,
            }
        except Exception as exc:
            return {
                "success": False,
                "status_code": 500,
                "message": f"HubSpot connection probe error: {str(exc)}",
                "details": None,
            }
