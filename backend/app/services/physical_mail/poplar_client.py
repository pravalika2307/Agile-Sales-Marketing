"""Poplar Direct Mail API Client for programmatic physical mail campaigns."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import re

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


# ── Exception Hierarchy ───────────────────────────────────────────────────────

class PoplarError(Exception):
    """Base exception for Poplar direct mail provider errors."""
    pass


class PoplarConfigurationError(PoplarError):
    """Raised when Poplar configuration or credentials are missing or invalid."""
    pass


class PoplarAuthenticationError(PoplarError):
    """Raised when authentication fails (HTTP 401)."""
    def __init__(self, message: str = "Invalid or expired Poplar API key", status_code: int = 401) -> None:
        super().__init__(message)
        self.status_code = status_code


class PoplarPermissionError(PoplarError):
    """Raised when access is forbidden or account suspended (HTTP 403)."""
    def __init__(self, message: str = "Poplar operation forbidden", status_code: int = 403) -> None:
        super().__init__(message)
        self.status_code = status_code


class PoplarNotFoundError(PoplarError):
    """Raised when campaign, creative, or mailing resource is not found (HTTP 404)."""
    def __init__(self, message: str = "Poplar resource not found", resource_id: Optional[str] = None) -> None:
        super().__init__(message)
        self.resource_id = resource_id


class PoplarValidationError(PoplarError):
    """Raised when address or recipient data fails Poplar CASS/schema validation (HTTP 400)."""
    def __init__(self, message: str = "Poplar request validation failed", errors: Optional[List[str]] = None) -> None:
        super().__init__(message)
        self.errors = errors or []


class PoplarRateLimitError(PoplarError):
    """Raised when Poplar API rate limit is exceeded (HTTP 429)."""
    def __init__(self, message: str = "Poplar API rate limit exceeded", retry_after: Optional[int] = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class PoplarTimeoutError(PoplarError):
    """Raised when an HTTP request to Poplar times out."""
    pass


class PoplarAPIError(PoplarError):
    """Raised when Poplar returns an unexpected error (HTTP 5xx or unhandled status)."""
    def __init__(self, status_code: int, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(f"Poplar API error ({status_code}): {message}")
        self.status_code = status_code
        self.details = details or {}


# ── Data Models ───────────────────────────────────────────────────────────────

@dataclass
class PoplarRecipient:
    """Recipient postal address payload matching Poplar /v1/mailing schema."""
    address_1: str
    city: str
    state: str
    postal_code: str
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company: Optional[Optional[str]] = None
    address_2: Optional[str] = None
    country: Optional[str] = "US"
    email: Optional[str] = None
    identifier: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert recipient to Poplar request dictionary, pruning empty optional fields."""
        data: Dict[str, Any] = {
            "address_1": self.address_1.strip(),
            "city": self.city.strip(),
            "state": self.state.strip().upper(),
            "postal_code": self.postal_code.strip(),
        }
        name = self.full_name
        if not name and (self.first_name or self.last_name):
            name = f"{self.first_name or ''} {self.last_name or ''}".strip()
        if name:
            data["full_name"] = name
        if self.company and self.company.strip():
            data["company"] = self.company.strip()
        if self.address_2 and self.address_2.strip():
            data["address_2"] = self.address_2.strip()
        if self.email and self.email.strip():
            data["email"] = self.email.strip()
        if self.identifier and self.identifier.strip():
            data["identifier"] = str(self.identifier).strip()
        return data


@dataclass
class PoplarMailingResult:
    """Response returned upon successful mailing creation."""
    id: str
    status: str
    campaign_id: str
    created_at: Optional[str] = None
    creative_id: Optional[str] = None
    estimated_delivery_date: Optional[str] = None
    proof_url: Optional[str] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)


# ── Poplar API Client ─────────────────────────────────────────────────────────

class PoplarClient:
    """
    HTTP client for the Poplar Direct Mail REST API (v1).
    Enforces test vs production credential isolation and fail-closed safety.
    """

    def __init__(
        self,
        test_api_key: Optional[str] = None,
        production_api_key: Optional[str] = None,
        api_key: Optional[str] = None,
        environment: str = "test",
        allow_live_sending: bool = False,
        base_url: str = "https://api.heypoplar.com/v1",
        timeout: float = 15.0,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        self.environment = (environment or "test").strip().lower()
        self.allow_live_sending = allow_live_sending
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

        # Resolve credentials strictly matching environment
        self._test_key = (test_api_key or (api_key if api_key and api_key.startswith("test_") else None) or "").strip() or None
        self._prod_key = (production_api_key or (api_key if api_key and not api_key.startswith("test_") else None) or "").strip() or None

        if self.environment == "test":
            # Test mode must NEVER silently fall back to production credentials
            if not self._test_key:
                raise PoplarConfigurationError(
                    "Poplar test API key is missing. In test mode, PoplarClient requires a valid test key "
                    "(e.g., POPLAR_TEST_API_KEY prefixed with 'test_') and refuses to fall back to production."
                )
            self._active_key = self._test_key
        elif self.environment == "production":
            # Production mode requires live sending authorization
            if not self.allow_live_sending:
                raise PoplarConfigurationError(
                    "Poplar live sending is disabled (POPLAR_ALLOW_LIVE_SENDING=False). "
                    "Cannot initialize production Poplar client."
                )
            if not self._prod_key:
                raise PoplarConfigurationError("Poplar production API key is missing.")
            self._active_key = self._prod_key
        else:
            raise PoplarConfigurationError(f"Invalid Poplar environment '{environment}'. Allowed: 'test', 'production'.")

        self._http_client = http_client or httpx.Client(
            timeout=httpx.Timeout(self.timeout, connect=5.0),
        )

    @property
    def is_test_mode(self) -> bool:
        """Returns True if the client is bound to test environment credentials."""
        return self.environment == "test"

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._active_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "AgileSalesMarketing-PoplarClient/1.0",
        }

    def _sanitize_error_detail(self, text: str) -> str:
        """Sanitize any leaked bearer tokens or credential fragments from error strings."""
        if not text:
            return ""
        if self._active_key:
            text = text.replace(self._active_key, "[REDACTED_TOKEN]")
        # Strip generic token patterns
        text = re.sub(r"Bearer\s+[a-zA-Z0-9_\-\.]+", "Bearer [REDACTED]", text, flags=re.IGNORECASE)
        return text.strip()

    def _handle_response_error(self, response: httpx.Response) -> None:
        """Map HTTP error status codes to sanitized domain exceptions."""
        status_code = response.status_code
        try:
            body = response.json()
            error_msg = body.get("message") or body.get("error") or str(body)
        except Exception:
            error_msg = response.text or "Unknown provider error"

        clean_msg = self._sanitize_error_detail(str(error_msg))

        if status_code == 401:
            raise PoplarAuthenticationError("Poplar authentication rejected: Invalid or expired API token.", status_code=401)
        elif status_code == 403:
            raise PoplarPermissionError(f"Poplar access forbidden: {clean_msg}", status_code=403)
        elif status_code == 404:
            raise PoplarNotFoundError(f"Poplar resource not found: {clean_msg}")
        elif status_code == 400:
            raise PoplarValidationError(f"Poplar rejected request: {clean_msg}")
        elif status_code == 429:
            retry_after = None
            if "Retry-After" in response.headers:
                try:
                    retry_after = int(response.headers["Retry-After"])
                except ValueError:
                    pass
            raise PoplarRateLimitError(f"Poplar rate limit exceeded: {clean_msg}", retry_after=retry_after)
        else:
            raise PoplarAPIError(status_code=status_code, message=clean_msg)

    # ── API Operations ────────────────────────────────────────────────────────

    def verify_connection(self) -> Dict[str, Any]:
        """
        Verify connectivity and token validity against Poplar API via read-only GET /v1/me.
        Does not initiate any mailings or incur costs.
        """
        url = f"{self.base_url}/me"
        try:
            resp = self._http_client.get(url, headers=self._headers())
            if resp.status_code >= 400:
                self._handle_response_error(resp)
            data = resp.json() if resp.text else {}
            return {
                "connected": True,
                "environment": self.environment,
                "status_code": resp.status_code,
                "data": data,
                "base_url": self.base_url,
            }
        except (httpx.TimeoutException, httpx.ConnectTimeout) as exc:
            raise PoplarTimeoutError(f"Poplar connection verification timed out: {exc}") from exc
        except httpx.RequestError as exc:
            raise PoplarAPIError(0, f"Poplar network connection error: {exc}") from exc

    def create_mailing(
        self,
        campaign_id: str,
        recipient: PoplarRecipient | Dict[str, Any],
        merge_tags: Optional[Dict[str, Any]] = None,
        creative_id: Optional[str] = None,
        send_at: Optional[str] = None,
    ) -> PoplarMailingResult:
        """
        Dispatches a 1-to-1 physical mailing through Poplar API.
        In test mode (test token), validates address and generates proof URL without printing or billing.
        """
        if not campaign_id or not campaign_id.strip():
            raise PoplarValidationError("campaign_id is required to create a physical mailing.")

        recipient_payload = recipient.to_dict() if isinstance(recipient, PoplarRecipient) else recipient
        if not recipient_payload:
            raise PoplarValidationError("recipient payload is required.")

        payload: Dict[str, Any] = {
            "campaign_id": campaign_id.strip(),
            "recipient": recipient_payload,
        }
        if creative_id and creative_id.strip():
            payload["creative_id"] = creative_id.strip()
        if send_at and send_at.strip():
            payload["send_at"] = send_at.strip()
        if merge_tags:
            payload["merge_tags"] = merge_tags

        url = f"{self.base_url}/mailing"
        try:
            resp = self._http_client.post(url, headers=self._headers(), json=payload)
            if resp.status_code >= 400:
                self._handle_response_error(resp)

            data = resp.json()
            mailing_id = data.get("id") or data.get("mailing_id") or ""
            status = data.get("status") or "mailing_queued"
            proof_url = data.get("proof_url") or data.get("preview_url")

            return PoplarMailingResult(
                id=mailing_id,
                status=status,
                campaign_id=campaign_id,
                created_at=data.get("created_at"),
                creative_id=data.get("creative_id") or creative_id,
                estimated_delivery_date=data.get("estimated_delivery_date"),
                proof_url=proof_url,
                raw_data=data,
            )
        except (httpx.TimeoutException, httpx.ConnectTimeout) as exc:
            raise PoplarTimeoutError("Request to create Poplar mailing timed out.") from exc
        except httpx.RequestError as exc:
            raise PoplarAPIError(0, f"Poplar network request error: {exc}") from exc

    def get_mailing(self, mailing_id: str) -> Dict[str, Any]:
        """
        Retrieves status, USPS scan history, and delivery details for an in-flight mailing.
        """
        if not mailing_id or not mailing_id.strip():
            raise PoplarValidationError("mailing_id is required.")

        url = f"{self.base_url}/mailing/{mailing_id.strip()}"
        try:
            resp = self._http_client.get(url, headers=self._headers())
            if resp.status_code >= 400:
                self._handle_response_error(resp)
            return resp.json()
        except (httpx.TimeoutException, httpx.ConnectTimeout) as exc:
            raise PoplarTimeoutError(f"Request to query Poplar mailing '{mailing_id}' timed out.") from exc
        except httpx.RequestError as exc:
            raise PoplarAPIError(0, f"Poplar network request error: {exc}") from exc


def get_poplar_client() -> PoplarClient:
    """Dependency injection provider returning a configured PoplarClient from app settings."""
    return PoplarClient(
        test_api_key=settings.POPLAR_TEST_API_KEY,
        production_api_key=settings.POPLAR_PRODUCTION_API_KEY,
        api_key=settings.POPLAR_API_KEY,
        environment=settings.POPLAR_ENVIRONMENT,
        allow_live_sending=settings.POPLAR_ALLOW_LIVE_SENDING,
        base_url=settings.POPLAR_BASE_URL,
        timeout=settings.POPLAR_TIMEOUT_SECONDS,
    )
