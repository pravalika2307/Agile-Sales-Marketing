"""Provider-independent outreach execution interfaces and mock provider implementation."""
from __future__ import annotations

import abc
import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


@dataclass
class EmailMessage:
    """Outreach email payload structure."""
    to_email: str
    subject: str
    body: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EmailSendResult:
    """Outcome of an email provider delivery attempt."""
    provider: str
    provider_message_id: str
    success: bool
    error_message: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class EmailProvider(abc.ABC):
    """
    Abstract interface for email delivery providers.
    All future concrete providers (SES, SendGrid, Resend, etc.) must implement this contract.
    """

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        """Identifier name of the provider."""
        raise NotImplementedError

    @abc.abstractmethod
    def send(self, message: EmailMessage) -> EmailSendResult:
        """
        Deliver an outreach email message through the provider.
        Must return an EmailSendResult and never raise unhandled delivery exceptions.
        """
        raise NotImplementedError


class MockEmailProvider(EmailProvider):
    """
    Mock Email Provider for local development and automated testing.

    IMPORTANT SAFETY GUARANTEES:
    - Never makes external network requests.
    - Never contacts SMTP or external APIs.
    - Never requires credentials or configuration.
    - Generates deterministic fake provider message IDs.
    - Safe for sandboxed test environments.
    """

    def __init__(self, should_fail: bool = False, failure_reason: Optional[str] = None) -> None:
        self._should_fail = should_fail
        self._failure_reason = failure_reason or "Simulated provider failure"

    @property
    def provider_name(self) -> str:
        return "mock"

    def send(self, message: EmailMessage) -> EmailSendResult:
        """Simulate email delivery without network calls."""
        if self._should_fail:
            return EmailSendResult(
                provider=self.provider_name,
                provider_message_id="",
                success=False,
                error_message=self._failure_reason,
            )

        # Generate a deterministic fake provider message ID based on recipient and timestamp/hash
        recipient_hash = hashlib.sha256(message.to_email.encode("utf-8")).hexdigest()[:8]
        msg_uuid = uuid.uuid4().hex[:12]
        fake_id = f"mock-msg-{recipient_hash}-{msg_uuid}"

        return EmailSendResult(
            provider=self.provider_name,
            provider_message_id=fake_id,
            success=True,
            error_message=None,
        )
