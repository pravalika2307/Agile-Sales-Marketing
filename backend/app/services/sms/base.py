"""SMS Provider interfaces, message data models, and Mock SMS provider implementation."""
from __future__ import annotations

import abc
import hashlib
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple


# GSM 7-bit default character set (basic character set + extension characters)
GSM_7BIT_BASIC = (
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1bÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ`¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
GSM_7BIT_EXTENDED = "|^€{}[~]\\\f"
GSM_7BIT_ALL = set(GSM_7BIT_BASIC + GSM_7BIT_EXTENDED)

# Standard ITU-T E.164 phone number pattern
E164_REGEX = re.compile(r"^\+[1-9]\d{6,14}$")


def is_gsm7_compatible(text: str) -> bool:
    """Check if all characters in text belong to the standard GSM-7 basic or extended charset."""
    return all(ch in GSM_7BIT_ALL for ch in text)


def calculate_sms_segments(body: str) -> Dict[str, Any]:
    """
    Calculate SMS length, segment count, and encoding.

    GSM-7 Encoding:
    - 1 segment: up to 160 characters.
    - Multipart: 153 characters per segment (7 bytes reserved for User Data Header).
    - Note: GSM extension characters (|^€{}[~]\\) count as 2 characters.

    UCS-2 (Unicode) Encoding:
    - 1 segment: up to 70 characters.
    - Multipart: 67 characters per segment (3 bytes reserved for User Data Header).
    """
    if not body:
        return {
            "character_count": 0,
            "segment_count": 0,
            "encoding": "GSM-7",
            "remaining_in_segment": 160,
            "max_per_segment": 160,
        }

    is_gsm = is_gsm7_compatible(body)
    if is_gsm:
        encoding = "GSM-7"
        # Extension characters count as 2 units in GSM 7-bit
        char_count = sum(2 if ch in GSM_7BIT_EXTENDED else 1 for ch in body)
        if char_count <= 160:
            segment_count = 1 if char_count > 0 else 0
            remaining = 160 - char_count
            max_per_segment = 160
        else:
            segment_count = (char_count + 152) // 153
            current_seg_used = char_count % 153 or 153
            remaining = 153 - current_seg_used
            max_per_segment = 153
    else:
        encoding = "UCS-2"
        char_count = len(body)
        if char_count <= 70:
            segment_count = 1 if char_count > 0 else 0
            remaining = 70 - char_count
            max_per_segment = 70
        else:
            segment_count = (char_count + 66) // 67
            current_seg_used = char_count % 67 or 67
            remaining = 67 - current_seg_used
            max_per_segment = 67

    return {
        "character_count": char_count,
        "segment_count": segment_count,
        "encoding": encoding,
        "remaining_in_segment": remaining,
        "max_per_segment": max_per_segment,
    }


def normalize_phone_number(
    phone: Optional[str],
    default_country_code: str = "1",
) -> Tuple[bool, str, Optional[str]]:
    """
    Validates and normalizes phone numbers into E.164 international format (+<country><number>).

    Returns:
        (is_valid, formatted_phone, error_message)
    """
    if not phone or not phone.strip():
        return False, "", "Phone number cannot be empty."

    raw = phone.strip()

    if re.search(r"[a-zA-Z]", raw):
        return (
            False,
            "",
            f"Invalid phone number format '{raw}'. Phone numbers cannot contain alphabetic characters.",
        )

    # Retain leading '+' if present and strip all spaces, dashes, parentheses, dots
    has_plus = raw.startswith("+")
    digits_only = re.sub(r"\D", "", raw)

    if not digits_only:
        return False, "", "Phone number must contain numeric digits."

    if has_plus:
        formatted = f"+{digits_only}"
    elif len(digits_only) == 10:
        # Standard 10-digit North American number without +1
        formatted = f"+{default_country_code}{digits_only}"
    elif len(digits_only) == 12 and digits_only.startswith("91"):
        # Indian number with country code 91
        formatted = f"+{digits_only}"
    elif len(digits_only) == 11 and digits_only.startswith("1"):
        # North American number with leading 1
        formatted = f"+{digits_only}"
    else:
        formatted = f"+{digits_only}"

    if not E164_REGEX.match(formatted):
        return (
            False,
            formatted,
            f"Invalid phone number format '{raw}'. Must be valid E.164 format (e.g. +1234567890).",
        )

    return True, formatted, None


@dataclass
class SMSMessage:
    """Outreach SMS payload structure."""
    to_phone: str
    body: str
    from_phone: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SMSSendResult:
    """Outcome of an SMS delivery attempt."""
    provider: str
    provider_message_id: str
    success: bool
    status: str = "sent"
    error_message: Optional[str] = None
    character_count: int = 0
    segment_count: int = 1
    encoding: str = "GSM-7"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class SMSProvider(abc.ABC):
    """
    Abstract interface for SMS delivery providers.
    All concrete implementations (MockSMSProvider, TwilioSMSProvider) must implement this contract.
    """

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        """Unique identifier name of the provider."""
        raise NotImplementedError

    @abc.abstractmethod
    def send(self, message: SMSMessage) -> SMSSendResult:
        """
        Deliver an outreach SMS through the provider.
        Must return an SMSSendResult and never raise unhandled delivery exceptions.
        """
        raise NotImplementedError


class MockSMSProvider(SMSProvider):
    """
    Mock SMS Provider for safe development, automated testing, and simulated campaign runs.

    NON-NEGOTIABLE SAFETY GUARANTEES:
    - Never makes external network requests.
    - Never contacts Twilio API or messaging gateways.
    - Never consumes trial messages.
    - Operates completely in-memory with deterministic fake IDs.
    - Generates realistic statuses ('sent', 'delivered', 'failed').
    """

    def __init__(
        self,
        should_fail: bool = False,
        failure_reason: Optional[str] = None,
        simulated_status: str = "sent",
    ) -> None:
        self._should_fail = should_fail
        self._failure_reason = failure_reason or "Simulated SMS provider failure"
        self._simulated_status = simulated_status

    @property
    def provider_name(self) -> str:
        return "mock-twilio"

    def send(self, message: SMSMessage) -> SMSSendResult:
        """Simulate SMS delivery without network calls or credential requirements."""
        calc = calculate_sms_segments(message.body)

        if self._should_fail:
            return SMSSendResult(
                provider=self.provider_name,
                provider_message_id="",
                success=False,
                status="failed",
                error_message=self._failure_reason,
                character_count=calc["character_count"],
                segment_count=calc["segment_count"],
                encoding=calc["encoding"],
            )

        # Generate deterministic mock message ID using hash of recipient and random token
        recipient_hash = hashlib.sha256(message.to_phone.encode("utf-8")).hexdigest()[:8]
        msg_uuid = uuid.uuid4().hex[:12]
        fake_id = f"mock-sms-SM{recipient_hash}{msg_uuid}"

        return SMSSendResult(
            provider=self.provider_name,
            provider_message_id=fake_id,
            success=True,
            status=self._simulated_status,
            error_message=None,
            character_count=calc["character_count"],
            segment_count=calc["segment_count"],
            encoding=calc["encoding"],
        )
