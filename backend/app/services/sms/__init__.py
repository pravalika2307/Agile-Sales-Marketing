"""SMS service module initialization."""
from app.services.sms.base import (
    E164_REGEX,
    GSM_7BIT_ALL,
    MockSMSProvider,
    SMSMessage,
    SMSProvider,
    SMSSendResult,
    calculate_sms_segments,
    is_gsm7_compatible,
    normalize_phone_number,
)
from app.services.sms.service import (
    InvalidPhoneNumberError,
    SMSConsentSuppressedError,
    SMSDeliveryError,
    SMSServiceError,
    check_sms_consent,
    get_sms_provider,
    preview_sms_step,
    render_sms_message,
    send_sms_outreach,
    validate_recipient_phone,
)
from app.services.sms.twilio_provider import (
    TwilioConfigurationError,
    TwilioLiveSendingDisabledError,
    TwilioSMSProvider,
)
from app.services.sms.webhook import (
    MessageRecordNotFoundError,
    WebhookSignatureVerificationError,
    process_twilio_delivery_callback,
    verify_twilio_signature,
)

__all__ = [
    "SMSMessage",
    "SMSSendResult",
    "SMSProvider",
    "MockSMSProvider",
    "TwilioSMSProvider",
    "calculate_sms_segments",
    "is_gsm7_compatible",
    "normalize_phone_number",
    "validate_recipient_phone",
    "check_sms_consent",
    "render_sms_message",
    "preview_sms_step",
    "send_sms_outreach",
    "get_sms_provider",
    "verify_twilio_signature",
    "process_twilio_delivery_callback",
    "SMSServiceError",
    "InvalidPhoneNumberError",
    "SMSConsentSuppressedError",
    "SMSDeliveryError",
    "TwilioConfigurationError",
    "TwilioLiveSendingDisabledError",
    "WebhookSignatureVerificationError",
    "MessageRecordNotFoundError",
]
