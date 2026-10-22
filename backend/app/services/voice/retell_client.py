"""Retell AI API Client for conversational voice agent discovery, configuration, and health monitoring."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


# ── Exception Hierarchy ───────────────────────────────────────────────────────

class RetellError(Exception):
    """Base exception for Retell AI client errors."""
    pass


class RetellConfigurationError(RetellError):
    """Raised when Retell API key or required configuration is missing."""
    pass


class RetellAuthenticationError(RetellError):
    """Raised when authentication fails (HTTP 401)."""
    def __init__(self, message: str = "Invalid or expired Retell API key", status_code: int = 401) -> None:
        super().__init__(message)
        self.status_code = status_code


class RetellPermissionError(RetellError):
    """Raised when operation is forbidden (HTTP 403)."""
    def __init__(self, message: str = "Retell access forbidden", status_code: int = 403) -> None:
        super().__init__(message)
        self.status_code = status_code


class RetellNotFoundError(RetellError):
    """Raised when requested agent or resource is not found (HTTP 404)."""
    def __init__(self, message: str = "Retell resource not found", resource_id: Optional[str] = None) -> None:
        super().__init__(message)
        self.resource_id = resource_id


class RetellRateLimitError(RetellError):
    """Raised when Retell API rate limit is reached (HTTP 429)."""
    def __init__(self, message: str = "Retell API rate limit exceeded", retry_after: Optional[int] = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class RetellTimeoutError(RetellError):
    """Raised when a request to Retell API times out."""
    pass


class RetellAPIError(RetellError):
    """Raised when Retell API returns an unexpected error (5xx or unhandled status)."""
    def __init__(self, status_code: int, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(f"Retell API error ({status_code}): {message}")
        self.status_code = status_code
        self.details = details or {}


# ── Data Models ───────────────────────────────────────────────────────────────

@dataclass
class RetellAgentSummary:
    """Summary representation of a Retell voice agent returned by list-agents."""
    agent_id: str
    agent_name: str
    channel: str = "voice"
    voice_id: Optional[str] = None
    user_modified_timestamp: Optional[int] = None
    response_engine_type: Optional[str] = None
    llm_id: Optional[str] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RetellAgentDetail:
    """Detailed representation of a Retell voice agent returned by get-agent."""
    agent_id: str
    agent_name: str
    channel: str = "voice"
    voice_id: Optional[str] = None
    voice_model: Optional[str] = None
    fallback_voice_ids: List[str] = field(default_factory=list)
    voice_temperature: Optional[float] = None
    voice_speed: Optional[float] = None
    responsiveness: Optional[float] = None
    interruption_sensitivity: Optional[float] = None
    enable_backchannel: Optional[bool] = None
    ambient_sound: Optional[str] = None
    language: Optional[str] = None
    is_published: Optional[bool] = None
    response_engine: Dict[str, Any] = field(default_factory=dict)
    post_call_analysis_data: List[Dict[str, Any]] = field(default_factory=list)
    last_modification_timestamp: Optional[int] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RetellConnectionStatus:
    """Connection and health status of the Retell AI integration."""
    configured: bool
    connected: bool
    provider: str = "retell"
    base_url: str = "https://api.retellai.com"
    agent_count: int = 0
    configured_outbound_agent_id: Optional[str] = None
    configured_inbound_agent_id: Optional[str] = None
    outbound_agent_valid: Optional[bool] = None
    inbound_agent_valid: Optional[bool] = None
    caller_id: Optional[str] = None
    error: Optional[str] = None
    message: str = ""


# ── Client Implementation ─────────────────────────────────────────────────────

class RetellClient:
    """
    HTTP client for the official Retell AI REST API.

    Guarantees:
    - Never logs or exposes API keys in tracebacks, repr strings, or exceptions.
    - Supports dependency injection of an existing httpx.Client for testing.
    - Handles timeouts, rate limits (HTTP 429), auth failures (401), and server errors cleanly.
    - Strictly inspects and discovers agents without dialing live phone calls.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 10.0,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        raw_key = api_key if api_key is not None else getattr(settings, "RETELL_API_KEY", None)
        self._api_key = raw_key.strip() if raw_key and isinstance(raw_key, str) else ""
        raw_base = base_url or getattr(settings, "RETELL_BASE_URL", "https://api.retellai.com")
        self.base_url = (raw_base or "https://api.retellai.com").rstrip("/")
        self.timeout = timeout
        self._http_client = http_client

    @property
    def is_configured(self) -> bool:
        """Check if an API key is configured."""
        return bool(self._api_key)

    def __repr__(self) -> str:
        masked_status = "configured=True" if self.is_configured else "configured=False"
        return f"<RetellClient base_url='{self.base_url}' {masked_status} timeout={self.timeout}>"

    def _get_headers(self) -> Dict[str, str]:
        """Construct authorization headers without leaking secrets."""
        if not self._api_key:
            raise RetellConfigurationError("Retell API key is not configured in settings.")
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "User-Agent": "AgileSalesMarketing/1.0",
        }

    def _sanitize_message(self, message: str) -> str:
        """Remove API key from error strings or logs if present."""
        if self._api_key and self._api_key in message:
            return message.replace(self._api_key, "********")
        return message

    def _handle_error_response(self, response: httpx.Response, action: str = "request") -> None:
        """Translates HTTP error status codes into typed Retell exceptions with sanitized messages."""
        status_code = response.status_code
        try:
            body_json = response.json()
            raw_detail = body_json.get("message") or body_json.get("error") or response.text
        except Exception:
            raw_detail = response.text or ""

        detail = self._sanitize_message(str(raw_detail))

        if status_code == 401:
            logger.warning("Retell API authentication failure on %s: %s", action, detail)
            raise RetellAuthenticationError(
                message=f"Retell authentication failed: {detail or 'Invalid API key'}",
                status_code=401,
            )
        elif status_code == 403:
            logger.warning("Retell API permission denied on %s: %s", action, detail)
            raise RetellPermissionError(
                message=f"Retell permission denied: {detail or 'Access forbidden'}",
                status_code=403,
            )
        elif status_code == 404:
            raise RetellNotFoundError(
                message=f"Retell resource not found: {detail}",
            )
        elif status_code == 429:
            retry_after_str = response.headers.get("Retry-After")
            retry_after = int(retry_after_str) if retry_after_str and retry_after_str.isdigit() else None
            logger.warning("Retell API rate limit reached on %s (retry_after=%s): %s", action, retry_after, detail)
            raise RetellRateLimitError(
                message=f"Retell API rate limit exceeded: {detail}",
                retry_after=retry_after,
            )
        else:
            logger.error("Retell API error (%d) on %s: %s", status_code, action, detail)
            raise RetellAPIError(
                status_code=status_code,
                message=detail or f"HTTP {status_code}",
            )

    def _execute_request(
        self,
        method: str,
        path: str,
        json_payload: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> httpx.Response:
        """Executes an HTTP request with timeout and network exception translation."""
        headers = self._get_headers()
        url = f"{self.base_url}{path}"

        def _do_call(client: httpx.Client) -> httpx.Response:
            try:
                resp = client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=json_payload,
                    params=params,
                    timeout=self.timeout,
                )
                if resp.is_error:
                    self._handle_error_response(resp, action=f"{method} {path}")
                return resp
            except httpx.TimeoutException as exc:
                sanitized_err = self._sanitize_message(str(exc))
                logger.warning("Retell API timeout on %s %s: %s", method, path, sanitized_err)
                raise RetellTimeoutError(f"Retell API request timed out after {self.timeout}s.") from exc
            except httpx.RequestError as exc:
                sanitized_err = self._sanitize_message(str(exc))
                logger.warning("Retell API connection error on %s %s: %s", method, path, sanitized_err)
                raise RetellAPIError(
                    status_code=502,
                    message=f"Failed to connect to Retell API: {sanitized_err}",
                ) from exc

        if self._http_client is not None:
            return _do_call(self._http_client)

        with httpx.Client() as client:
            return _do_call(client)

    # ── Agent Operations ──────────────────────────────────────────────────────

    def list_agents(
        self,
        limit: int = 50,
        pagination_key: Optional[str] = None,
    ) -> List[RetellAgentSummary]:
        """
        Retrieves available voice agents from Retell AI.

        Uses the official POST /v2/list-agents endpoint, supporting pagination and channel filtering.
        Gracefully handles both current v2 dictionary schema and array responses.
        """
        payload: Dict[str, Any] = {
            "limit": min(max(1, limit), 100),
            "filter_criteria": {
                "channel": {
                    "op": "eq",
                    "value": "voice",
                }
            },
        }
        if pagination_key:
            payload["pagination_key"] = pagination_key

        try:
            resp = self._execute_request("POST", "/v2/list-agents", json_payload=payload)
            data = resp.json()
        except RetellAPIError as exc:
            # Fallback to GET /list-agents if v2 POST is not supported on endpoint
            if exc.status_code in (404, 405):
                logger.info("Retell /v2/list-agents returned %d. Falling back to /list-agents.", exc.status_code)
                resp = self._execute_request("GET", "/list-agents")
                data = resp.json()
            else:
                raise

        raw_items: List[Dict[str, Any]] = []
        if isinstance(data, list):
            raw_items = data
        elif isinstance(data, dict):
            raw_items = data.get("items") or data.get("agents") or []

        summaries: List[RetellAgentSummary] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            agent_id = str(item.get("agent_id") or "")
            if not agent_id:
                continue
            agent_name = str(item.get("agent_name") or agent_id)
            channel = str(item.get("channel") or "voice")
            voice_id = item.get("voice_id")
            ts = item.get("user_modified_timestamp") or item.get("last_modification_timestamp")

            # Extract response engine info if present
            resp_eng = item.get("response_engine") or {}
            engine_type = resp_eng.get("type") if isinstance(resp_eng, dict) else None
            llm_id = resp_eng.get("llm_id") if isinstance(resp_eng, dict) else None

            summaries.append(
                RetellAgentSummary(
                    agent_id=agent_id,
                    agent_name=agent_name,
                    channel=channel,
                    voice_id=voice_id,
                    user_modified_timestamp=ts,
                    response_engine_type=engine_type,
                    llm_id=llm_id,
                    raw_data=item,
                )
            )

        return summaries

    def get_agent(self, agent_id: str) -> RetellAgentDetail:
        """
        Retrieves detailed configuration for a specific Retell agent by ID.
        Uses the official GET /get-agent/{agent_id} endpoint.
        """
        clean_id = (agent_id or "").strip()
        if not clean_id:
            raise ValueError("agent_id must not be empty.")

        resp = self._execute_request("GET", f"/get-agent/{clean_id}")
        data = resp.json()
        if not isinstance(data, dict):
            raise RetellAPIError(500, "Unexpected non-dictionary response from Retell /get-agent.")

        return RetellAgentDetail(
            agent_id=str(data.get("agent_id") or clean_id),
            agent_name=str(data.get("agent_name") or clean_id),
            channel=str(data.get("channel") or "voice"),
            voice_id=data.get("voice_id"),
            voice_model=data.get("voice_model"),
            fallback_voice_ids=data.get("fallback_voice_ids") or [],
            voice_temperature=data.get("voice_temperature"),
            voice_speed=data.get("voice_speed"),
            responsiveness=data.get("responsiveness"),
            interruption_sensitivity=data.get("interruption_sensitivity"),
            enable_backchannel=data.get("enable_backchannel"),
            ambient_sound=data.get("ambient_sound"),
            language=data.get("language") or "en-US",
            is_published=data.get("is_published"),
            response_engine=data.get("response_engine") or {},
            post_call_analysis_data=data.get("post_call_analysis_data") or [],
            last_modification_timestamp=data.get("last_modification_timestamp"),
            raw_data=data,
        )

    # ── Call Operations ───────────────────────────────────────────────────────

    def create_phone_call(
        self,
        from_number: str,
        to_number: str,
        override_agent_id: Optional[str] = None,
        dynamic_variables: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Initiates an outbound phone call via the official Retell REST API: POST /v2/create-phone-call.

        Parameters:
        - from_number: E.164 phone number purchased or registered with Retell.
        - to_number: Destination E.164 phone number.
        - override_agent_id: Optional agent ID to handle the call (defaults to Retell phone number agent).
        - dynamic_variables: Key-value string pairs passed to the agent LLM prompt.
        - metadata: Arbitrary key-value metadata preserved through call webhooks.

        Returns:
        Dictionary representing the created Call object containing call_id, call_status, etc.
        """
        if not self.is_configured:
            raise RetellConfigurationError("Retell API key is not configured in settings.")

        clean_from = (from_number or "").strip()
        clean_to = (to_number or "").strip()

        if not clean_from:
            raise ValueError("from_number must not be empty.")
        if not clean_to:
            raise ValueError("to_number must not be empty.")

        payload: Dict[str, Any] = {
            "from_number": clean_from,
            "to_number": clean_to,
        }

        if override_agent_id and override_agent_id.strip():
            payload["override_agent_id"] = override_agent_id.strip()

        if dynamic_variables and isinstance(dynamic_variables, dict):
            # Ensure all values are strings per Retell LLM dynamic variables specification
            clean_vars = {
                str(k): str(v) if v is not None else ""
                for k, v in dynamic_variables.items()
                if k is not None
            }
            payload["retell_llm_dynamic_variables"] = clean_vars

        if metadata and isinstance(metadata, dict):
            payload["metadata"] = metadata

        logger.info(
            "Creating outbound Retell call from %s to %s (override_agent_id=%s)",
            clean_from,
            clean_to,
            override_agent_id,
        )

        resp = self._execute_request("POST", "/v2/create-phone-call", json_payload=payload)
        data = resp.json()
        if not isinstance(data, dict):
            raise RetellAPIError(500, "Unexpected non-dictionary response from Retell /v2/create-phone-call.")

        return data

    # ── Connection & Health Probe ─────────────────────────────────────────────

    def check_connection(self) -> RetellConnectionStatus:
        """
        Probes Retell API connectivity, validates credentials, and verifies configured agents.
        Safe: strictly read-only and never dials live phone numbers.
        """
        outbound_id = getattr(settings, "RETELL_AGENT_ID", None)
        inbound_id = getattr(settings, "RETELL_INBOUND_AGENT_ID", None)
        from_num = getattr(settings, "RETELL_FROM_NUMBER", None)

        if not self.is_configured:
            return RetellConnectionStatus(
                configured=False,
                connected=False,
                provider="retell",
                base_url=self.base_url,
                agent_count=0,
                configured_outbound_agent_id=outbound_id,
                configured_inbound_agent_id=inbound_id,
                caller_id=from_num,
                error="RETELL_API_KEY is not configured",
                message="Retell AI voice provider is unconfigured. Set RETELL_API_KEY to enable.",
            )

        try:
            agents = self.list_agents(limit=50)
            agent_ids = {a.agent_id for a in agents}

            outbound_valid = bool(outbound_id in agent_ids) if outbound_id else None
            inbound_valid = bool(inbound_id in agent_ids) if inbound_id else None

            return RetellConnectionStatus(
                configured=True,
                connected=True,
                provider="retell",
                base_url=self.base_url,
                agent_count=len(agents),
                configured_outbound_agent_id=outbound_id,
                configured_inbound_agent_id=inbound_id,
                outbound_agent_valid=outbound_valid,
                inbound_agent_valid=inbound_valid,
                caller_id=from_num,
                error=None,
                message=f"Retell AI connection active. {len(agents)} voice agent(s) discovered.",
            )
        except RetellAuthenticationError as exc:
            return RetellConnectionStatus(
                configured=True,
                connected=False,
                provider="retell",
                base_url=self.base_url,
                agent_count=0,
                configured_outbound_agent_id=outbound_id,
                configured_inbound_agent_id=inbound_id,
                caller_id=from_num,
                error="Authentication failed",
                message="Retell authentication rejected. Check that RETELL_API_KEY is valid.",
            )
        except RetellRateLimitError as exc:
            return RetellConnectionStatus(
                configured=True,
                connected=False,
                provider="retell",
                base_url=self.base_url,
                agent_count=0,
                configured_outbound_agent_id=outbound_id,
                configured_inbound_agent_id=inbound_id,
                caller_id=from_num,
                error="Rate limited",
                message="Retell API rate limit reached. Please retry later.",
            )
        except RetellTimeoutError as exc:
            return RetellConnectionStatus(
                configured=True,
                connected=False,
                provider="retell",
                base_url=self.base_url,
                agent_count=0,
                configured_outbound_agent_id=outbound_id,
                configured_inbound_agent_id=inbound_id,
                caller_id=from_num,
                error="Timeout",
                message=f"Retell connection timed out after {self.timeout}s.",
            )
        except RetellError as exc:
            return RetellConnectionStatus(
                configured=True,
                connected=False,
                provider="retell",
                base_url=self.base_url,
                agent_count=0,
                configured_outbound_agent_id=outbound_id,
                configured_inbound_agent_id=inbound_id,
                caller_id=from_num,
                error=self._sanitize_message(str(exc)),
                message="Retell API communication error occurred.",
            )


def get_retell_client() -> RetellClient:
    """Dependency provider returning an instantiated RetellClient."""
    return RetellClient()
