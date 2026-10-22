"""Twilio SMS Provider with strict fail-closed live send protection and HTTP REST API client."""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.core.config import settings
from app.services.sms.base import (
    SMSMessage,
    SMSProvider,
    SMSSendResult,
    calculate_sms_segments,
    normalize_phone_number,
)

logger = logging.getLogger(__name__)


class TwilioConfigurationError(Exception):
    """Raised when Twilio provider is configured incorrectly or missing credentials."""
    pass


class TwilioLiveSendingDisabledError(Exception):
    """Raised when real Twilio SMS delivery is attempted while live sending is disabled."""
    pass


class TwilioSMSProvider(SMSProvider):
    """
    Concrete SMSProvider communicating with the Twilio REST API.

    STRICT SAFETY GUARANTEES:
    1. Fail-closed: Never initiates real sending unless TWILIO_ENABLED=True AND
       TWILIO_ALLOW_LIVE_SENDING=True.
    2. Missing or false settings default to blocking external delivery.
    3. Never logs or prints Account SID or Auth Token in tracebacks or log output.
    4. Validates recipient E.164 phone numbers prior to any API submission.
    5. Returns SMSSendResult and catches network or HTTP errors without unhandled crashes.
    """

    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        from_number: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self._account_sid = (account_sid or settings.TWILIO_ACCOUNT_SID or "").strip()
        self._auth_token = (auth_token or settings.TWILIO_AUTH_TOKEN or "").strip()
        self._from_number = (from_number or settings.TWILIO_FROM_NUMBER or "").strip()
        self._base_url = (base_url or settings.TWILIO_API_BASE_URL).rstrip("/")
        self._timeout = timeout if timeout is not None else settings.TWILIO_TIMEOUT_SECONDS

    @property
    def provider_name(self) -> str:
        return "twilio"

    @property
    def is_configured(self) -> bool:
        """Check if Account SID, Auth Token, and From Number are all present."""
        return bool(self._account_sid and self._auth_token and self._from_number)

    @property
    def is_live_sending_allowed(self) -> bool:
        """Check whether fail-closed flags explicitly authorize live message delivery."""
        return bool(
            self.is_configured
            and settings.TWILIO_ENABLED
            and getattr(settings, "TWILIO_ALLOW_LIVE_SENDING", False)
        )

    def send(self, message: SMSMessage) -> SMSSendResult:
        """
        Send an SMS through Twilio.
        Protects against unauthorized sending via independent fail-closed validation.
        """
        calc = calculate_sms_segments(message.body)

        # 1. Non-negotiable Fail-Closed Safety Guard:
        # If live sending is disabled by configuration, immediately abort before any HTTP connection
        if not self.is_live_sending_allowed:
            logger.warning(
                "Twilio real SMS dispatch blocked: TWILIO_ENABLED=%s, TWILIO_ALLOW_LIVE_SENDING=%s. "
                "Fail-closed safety active.",
                settings.TWILIO_ENABLED,
                getattr(settings, "TWILIO_ALLOW_LIVE_SENDING", False),
            )
            return SMSSendResult(
                provider=self.provider_name,
                provider_message_id="",
                success=False,
                status="failed",
                error_message=(
                    "Real SMS sending is strictly disabled by safety configuration "
                    "(TWILIO_ENABLED=False or TWILIO_ALLOW_LIVE_SENDING=False). "
                    "No external message delivery was attempted."
                ),
                character_count=calc["character_count"],
                segment_count=calc["segment_count"],
                encoding=calc["encoding"],
            )

        # 2. Recipient phone validation
        is_valid, formatted_phone, error_msg = normalize_phone_number(message.to_phone)
        if not is_valid:
            return SMSSendResult(
                provider=self.provider_name,
                provider_message_id="",
                success=False,
                status="failed",
                error_message=f"Invalid recipient phone: {error_msg}",
                character_count=calc["character_count"],
                segment_count=calc["segment_count"],
                encoding=calc["encoding"],
            )

        # 3. Message body validation
        if not message.body or not message.body.strip():
            return SMSSendResult(
                provider=self.provider_name,
                provider_message_id="",
                success=False,
                status="failed",
                error_message="SMS body cannot be empty.",
                character_count=0,
                segment_count=0,
                encoding="GSM-7",
            )

        sender_number = (message.from_phone or self._from_number).strip()
        if not sender_number:
            return SMSSendResult(
                provider=self.provider_name,
                provider_message_id="",
                success=False,
                status="failed",
                error_message="Twilio sender number is not configured.",
                character_count=calc["character_count"],
                segment_count=calc["segment_count"],
                encoding=calc["encoding"],
            )

        endpoint_url = f"{self._base_url}/2010-04-01/Accounts/{self._account_sid}/Messages.json"
        payload = {
            "To": formatted_phone,
            "From": sender_number,
            "Body": message.body,
        }

        # Status callback webhook URL if specified in metadata
        callback_url = message.metadata.get("status_callback")
        if callback_url:
            payload["StatusCallback"] = callback_url

        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(
                    endpoint_url,
                    data=payload,
                    auth=(self._account_sid, self._auth_token),
                )

            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}

            if resp.status_code in (200, 201):
                msg_sid = data.get("sid", "")
                msg_status = data.get("status", "queued")
                return SMSSendResult(
                    provider=self.provider_name,
                    provider_message_id=msg_sid,
                    success=True,
                    status=msg_status,
                    error_message=None,
                    character_count=calc["character_count"],
                    segment_count=calc["segment_count"],
                    encoding=calc["encoding"],
                )
            else:
                error_code = data.get("code")
                error_text = data.get("message") or f"Twilio API error HTTP {resp.status_code}"
                return SMSSendResult(
                    provider=self.provider_name,
                    provider_message_id="",
                    success=False,
                    status="failed",
                    error_message=f"[{error_code}] {error_text}" if error_code else error_text,
                    character_count=calc["character_count"],
                    segment_count=calc["segment_count"],
                    encoding=calc["encoding"],
                )
        except Exception as exc:
            logger.error("Exception communicating with Twilio REST API: %s", exc)
            return SMSSendResult(
                provider=self.provider_name,
                provider_message_id="",
                success=False,
                status="failed",
                error_message=f"Network error communicating with Twilio: {exc}",
                character_count=calc["character_count"],
                segment_count=calc["segment_count"],
                encoding=calc["encoding"],
            )
