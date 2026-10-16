"""Email provider abstractions and implementations."""
from __future__ import annotations

from typing import Optional

from app.core.config import settings
from app.services.outreach.base import (
    EmailMessage,
    EmailProvider,
    EmailSendResult,
    MockEmailProvider,
)
from app.services.outreach.providers.resend import (
    ResendConfigurationError,
    ResendEmailProvider,
)
from app.services.outreach.providers.ses import (
    SesConfigurationError,
    SesEmailProvider,
)


def get_email_provider(provider_type: Optional[str] = None) -> EmailProvider:
    """
    Factory function to retrieve the appropriate EmailProvider.
    - If provider_type == 'mock' -> MockEmailProvider
    - If provider_type in ('ses', 'aws_ses') -> SesEmailProvider
    - If provider_type == 'resend' -> ResendEmailProvider
    - If provider_type is None:
        - Checks settings.EMAIL_PROVIDER_TYPE
        - Then checks settings.is_ses_configured (prioritizing Agile SES)
        - Then checks settings.is_resend_configured
        - Otherwise -> MockEmailProvider
    """
    selected_type = (provider_type or settings.EMAIL_PROVIDER_TYPE or "").strip().lower()

    if selected_type == "mock":
        return MockEmailProvider()

    if selected_type in ("ses", "aws_ses"):
        return SesEmailProvider()

    if selected_type == "resend":
        return ResendEmailProvider()

    # Automatic provider detection based on environment configuration
    if settings.is_ses_configured:
        return SesEmailProvider()

    if settings.is_resend_configured:
        return ResendEmailProvider()

    return MockEmailProvider()


__all__ = [
    "EmailMessage",
    "EmailProvider",
    "EmailSendResult",
    "MockEmailProvider",
    "ResendConfigurationError",
    "ResendEmailProvider",
    "SesConfigurationError",
    "SesEmailProvider",
    "get_email_provider",
]
