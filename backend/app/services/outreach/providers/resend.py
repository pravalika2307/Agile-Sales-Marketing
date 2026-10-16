"""Resend email provider implementation using official HTTP API."""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.core.config import settings
from app.services.outreach.base import (
    EmailMessage,
    EmailProvider,
    EmailSendResult,
)

logger = logging.getLogger(__name__)


class ResendConfigurationError(Exception):
    """Raised when Resend provider is invoked without required configuration."""
    pass


class ResendEmailProvider(EmailProvider):
    """
    Concrete EmailProvider communicating with Resend transactional email HTTP API.

    Guarantees:
    - Never logs or exposes API keys, authorization headers, or sensitive secrets.
    - Synchronous HTTP delivery via httpx.
    - Captures returned Resend message ID.
    - Controlled error handling returning EmailSendResult without raising unhandled exceptions.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        from_address: Optional[str] = None,
        from_name: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self._api_key = api_key or settings.RESEND_API_KEY
        self._from_address = from_address or settings.EMAIL_FROM_ADDRESS
        self._from_name = from_name or settings.EMAIL_FROM_NAME
        self._base_url = (base_url or settings.RESEND_BASE_URL).rstrip("/")
        self._timeout = timeout if timeout is not None else settings.RESEND_TIMEOUT_SECONDS

    @property
    def provider_name(self) -> str:
        return "resend"

    @property
    def is_configured(self) -> bool:
        return bool(
            self._api_key
            and self._api_key.strip()
            and self._from_address
            and self._from_address.strip()
        )

    def _format_sender(self) -> str:
        """Format the 'from' email header, e.g. 'Company <sales@example.com>'."""
        from_addr = (self._from_address or "").strip()
        from_name = (self._from_name or "").strip()
        if from_name:
            return f"{from_name} <{from_addr}>"
        return from_addr

    def send(self, message: EmailMessage) -> EmailSendResult:
        """
        Deliver an outreach email message via Resend HTTP API.
        Never exposes credentials or unhandled exceptions.
        """
        if not self.is_configured:
            logger.warning("Resend provider invoked without required configuration (RESEND_API_KEY or EMAIL_FROM_ADDRESS missing).")
            return EmailSendResult(
                provider=self.provider_name,
                provider_message_id="",
                success=False,
                error_message="Resend provider is not configured. Missing API key or sender email address.",
            )

        sender = self._format_sender()
        url = f"{self._base_url}/emails"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Agile-Sales-Marketing/0.1.0",
        }
        payload = {
            "from": sender,
            "to": [message.to_email],
            "subject": message.subject,
            "text": message.body,
        }

        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(url, headers=headers, json=payload)

            if response.status_code in (200, 201):
                try:
                    data = response.json()
                    msg_id = data.get("id") or ""
                except Exception:
                    msg_id = ""

                logger.info(
                    "Email successfully submitted to Resend for delivery to %s (message_id=%s)",
                    message.to_email,
                    msg_id,
                )
                return EmailSendResult(
                    provider=self.provider_name,
                    provider_message_id=str(msg_id),
                    success=True,
                    error_message=None,
                )

            # Handle non-success response from Resend
            error_detail = "Unknown error"
            try:
                error_data = response.json()
                error_detail = error_data.get("message") or error_data.get("error") or str(error_data)
            except Exception:
                error_detail = response.text[:200]

            clean_error = f"Resend API error {response.status_code}: {error_detail}"
            logger.warning(
                "Resend delivery failed for %s with status %s: %s",
                message.to_email,
                response.status_code,
                clean_error,
            )
            return EmailSendResult(
                provider=self.provider_name,
                provider_message_id="",
                success=False,
                error_message=clean_error,
            )

        except httpx.TimeoutException:
            err_msg = f"Resend request timed out after {self._timeout}s."
            logger.warning("Resend delivery timeout for %s", message.to_email)
            return EmailSendResult(
                provider=self.provider_name,
                provider_message_id="",
                success=False,
                error_message=err_msg,
            )
        except httpx.RequestError as exc:
            err_msg = f"Resend network error: {type(exc).__name__}"
            logger.warning("Resend connection error for %s: %s", message.to_email, type(exc).__name__)
            return EmailSendResult(
                provider=self.provider_name,
                provider_message_id="",
                success=False,
                error_message=err_msg,
            )
        except Exception as exc:
            err_msg = f"Unexpected delivery error: {type(exc).__name__}"
            logger.warning("Unexpected error during Resend delivery: %s", type(exc).__name__)
            return EmailSendResult(
                provider=self.provider_name,
                provider_message_id="",
                success=False,
                error_message=err_msg,
            )
