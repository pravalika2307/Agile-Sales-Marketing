"""Application configuration for Agile Sales & Marketing Backend."""
from __future__ import annotations

from typing import Any, ClassVar, Dict, List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General application settings
    PROJECT_NAME: str = "Agile Sales & Marketing API"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    # Database settings
    DATABASE_URL: str = "postgresql+psycopg://user:password@localhost:5432/agile_sales_marketing"

    # Known insecure or tutorial default secrets that must be rejected at startup
    KNOWN_INSECURE_SECRETS: ClassVar[set[str]] = {
        "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7",
        "change-me-in-production-use-a-strong-secret-key-at-least-32-chars",
        "secret",
        "secretkey",
        "changeme",
        "your-secret-key",
        "password",
        "1234567890",
    }

    # Authentication & Security settings
    # SECRET_KEY is marked with repr=False so it is never exposed in logging or repr strings.
    # Must be configured via environment variable or .env file (no insecure default fallback).
    SECRET_KEY: str = Field(
        ...,
        description="Cryptographically secure 256-bit signing key for JWT tokens.",
        repr=False,
    )
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        """Reject missing, weak (< 32 chars), or known insecure/default signing keys."""
        if not v or not v.strip():
            raise ValueError("SECRET_KEY must be configured and cannot be empty.")
        val = v.strip()
        if len(val) < 32:
            raise ValueError("SECRET_KEY is too weak: must be at least 32 characters long.")
        if val in cls.KNOWN_INSECURE_SECRETS or "change-me" in val.lower():
            raise ValueError(
                "SECRET_KEY is using a known insecure, default, or placeholder secret. "
                "A strong, cryptographically random secret must be configured."
            )
        return val

    # CORS settings: strict allowlist for trusted origins (development and documented clients)
    CORS_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"],
        description="Allowed origins for CORS requests. Restricts cross-origin credentialed access.",
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> Any:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    # HubSpot integration settings
    # Access token is marked with repr=False so it is never exposed in logging or repr strings
    HUBSPOT_ACCESS_TOKEN: Optional[str] = Field(default=None, repr=False)
    HUBSPOT_BASE_URL: str = "https://api.hubapi.com"
    HUBSPOT_TIMEOUT_SECONDS: float = 10.0

    @property
    def is_hubspot_configured(self) -> bool:
        """Check if a non-empty HubSpot access token is configured."""
        return bool(self.HUBSPOT_ACCESS_TOKEN and self.HUBSPOT_ACCESS_TOKEN.strip())

    # General Email Provider Selection ('mock', 'ses', 'resend', or None for auto-detection)
    EMAIL_PROVIDER_TYPE: Optional[str] = Field(default=None)

    # Email provider settings (Resend)
    # API key is marked with repr=False so it is never exposed in logging or repr strings
    RESEND_API_KEY: Optional[str] = Field(default=None, repr=False)
    EMAIL_FROM_ADDRESS: Optional[str] = Field(default=None)
    EMAIL_FROM_NAME: Optional[str] = Field(default="Agile Sales & Marketing")
    RESEND_BASE_URL: str = "https://api.resend.com"
    RESEND_TIMEOUT_SECONDS: float = 10.0

    @property
    def is_resend_configured(self) -> bool:
        """Check if Resend API key and sender email are both configured."""
        return bool(
            self.RESEND_API_KEY
            and self.RESEND_API_KEY.strip()
            and self.EMAIL_FROM_ADDRESS
            and self.EMAIL_FROM_ADDRESS.strip()
        )

    # Email provider settings (AWS SES - adapted from Agile backend)
    # Credentials are marked with repr=False so they are never exposed in logging or repr strings
    AWS_SES_REGION: str = "us-east-2"
    AWS_SES_CONFIGURATION_SET: Optional[str] = None
    AWS_SES_FROM_EMAIL: Optional[str] = None
    AWS_ACCESS_KEY_ID: Optional[str] = Field(default=None, repr=False)
    AWS_SECRET_ACCESS_KEY: Optional[str] = Field(default=None, repr=False)

    @property
    def is_ses_configured(self) -> bool:
        """Check if AWS SES provider is configured."""
        from_email = self.AWS_SES_FROM_EMAIL or self.EMAIL_FROM_ADDRESS
        return bool(self.AWS_SES_REGION and from_email and from_email.strip())

    # Webhook security settings (SES/SNS & Inbound Replies)
    AWS_SNS_VERIFY_WEBHOOK_SIGNATURE: bool = Field(default=True)
    INBOUND_REPLY_WEBHOOK_SECRET: Optional[str] = Field(default=None, repr=False)

    # Retell AI Voice settings (Outbound SDR)
    RETELL_API_KEY: Optional[str] = Field(default=None, repr=False)
    RETELL_AGENT_ID: Optional[str] = Field(default=None)
    RETELL_LLM_ID: Optional[str] = Field(default=None)
    RETELL_FROM_NUMBER: Optional[str] = Field(default=None)
    RETELL_BASE_URL: str = "https://api.retellai.com"
    RETELL_WEBHOOK_SECRET: Optional[str] = Field(default=None, repr=False)
    RETELL_VERIFY_WEBHOOK_SIGNATURE: bool = Field(default=True)
    VOICE_FOLLOWUP_COOLDOWN_HOURS: int = Field(default=24)
    # Fail-closed safety flags: Both must be explicitly True to allow real external voice calls
    RETELL_ENABLED: bool = Field(default=False)
    RETELL_ALLOW_LIVE_CALLS: bool = Field(default=False)
    RETELL_TIMEOUT_SECONDS: float = Field(default=10.0)

    # Retell AI Voice settings (Inbound Assistant)
    RETELL_INBOUND_AGENT_ID: Optional[str] = Field(default=None)
    RETELL_INBOUND_LLM_ID: Optional[str] = Field(default=None)
    RETELL_INBOUND_CF_AGENT_ID: Optional[str] = Field(default=None)
    RETELL_INBOUND_CONVERSATION_FLOW_ID: Optional[str] = Field(default=None)

    @property
    def is_retell_configured(self) -> bool:
        """Check if Retell outbound voice provider is configured."""
        return bool(
            self.RETELL_API_KEY
            and self.RETELL_API_KEY.strip()
            and self.RETELL_AGENT_ID
            and self.RETELL_AGENT_ID.strip()
        )

    @property
    def is_retell_live_calling_allowed(self) -> bool:
        """Safe fail-closed guard: Real phone calls require both RETELL_ENABLED=True and RETELL_ALLOW_LIVE_CALLS=True, plus valid credentials."""
        return bool(
            self.RETELL_ENABLED
            and self.RETELL_ALLOW_LIVE_CALLS
            and self.is_retell_configured
            and self.RETELL_FROM_NUMBER
        )

    @property
    def is_retell_inbound_configured(self) -> bool:
        """Check if Retell inbound voice provider is configured."""
        return bool(
            self.RETELL_API_KEY
            and self.RETELL_API_KEY.strip()
            and (self.RETELL_INBOUND_AGENT_ID or self.RETELL_INBOUND_CF_AGENT_ID)
        )

    # Twilio SMS Integration Settings
    # Credentials are marked with repr=False so they are never exposed in logging or repr strings
    TWILIO_ACCOUNT_SID: Optional[str] = Field(default=None, repr=False)
    TWILIO_AUTH_TOKEN: Optional[str] = Field(default=None, repr=False)
    TWILIO_FROM_NUMBER: Optional[str] = Field(default=None)
    # Fail-closed safety flags: Both must be explicitly True to allow real external sending
    TWILIO_ENABLED: bool = Field(default=False)
    TWILIO_ALLOW_LIVE_SENDING: bool = Field(default=False)
    TWILIO_API_BASE_URL: str = Field(default="https://api.twilio.com")
    TWILIO_TIMEOUT_SECONDS: float = Field(default=10.0)

    @property
    def is_twilio_configured(self) -> bool:
        """Check if Twilio account credentials and sender number are configured."""
        return bool(
            self.TWILIO_ACCOUNT_SID
            and self.TWILIO_ACCOUNT_SID.strip()
            and self.TWILIO_AUTH_TOKEN
            and self.TWILIO_AUTH_TOKEN.strip()
            and self.TWILIO_FROM_NUMBER
            and self.TWILIO_FROM_NUMBER.strip()
        )

    @property
    def is_twilio_live_sending_allowed(self) -> bool:
        """
        Fail-closed guard for live Twilio sending.
        Requires configuration, TWILIO_ENABLED=True, and TWILIO_ALLOW_LIVE_SENDING=True.
        """
        return bool(
            self.is_twilio_configured
            and self.TWILIO_ENABLED
            and self.TWILIO_ALLOW_LIVE_SENDING
        )

    # Campaign execution scheduler settings
    SCHEDULER_ENABLED: bool = Field(default=False)
    SCHEDULER_INTERVAL_SECONDS: int = Field(default=60)
    SCHEDULER_BATCH_SIZE: int = Field(default=50)
    SCHEDULER_AUTO_DISPATCH: bool = Field(default=False)
    SCHEDULER_MAX_RETRIES: int = Field(default=3)

    # AWS Bedrock (AI Email Generation)
    # Uses Anthropic Claude Sonnet 4.5 via cross-region inference profile (matching Agile Receivables)
    BEDROCK_REGION: str = "us-east-2"
    BEDROCK_DEFAULT_MODEL_ID: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    AWS_ACCESS_KEY_ID_AI: Optional[str] = Field(default=None, repr=False)
    AWS_SECRET_ACCESS_KEY_AI: Optional[str] = Field(default=None, repr=False)
    BEDROCK_READ_TIMEOUT: int = Field(default=60)
    BEDROCK_CONNECT_TIMEOUT: int = Field(default=10)
    BEDROCK_TEMPERATURE: float = Field(default=0.4)
    BEDROCK_MAX_TOKENS: int = Field(default=2048)

    @property
    def is_bedrock_configured(self) -> bool:
        """Check if AWS Bedrock credentials (dedicated AI or standard AWS) are present."""
        key_id = self.AWS_ACCESS_KEY_ID_AI or self.AWS_ACCESS_KEY_ID
        secret = self.AWS_SECRET_ACCESS_KEY_AI or self.AWS_SECRET_ACCESS_KEY
        return bool(key_id and key_id.strip() and secret and secret.strip() and self.BEDROCK_REGION)

    # Organization Meeting Booking URLs
    # Mapping of organization slug or organization UUID string to booking destination.
    # By default, Agile Receivables is configured with its confirmed Cal.com booking URL.
    ORGANIZATION_BOOKING_URLS: Dict[str, str] = Field(
        default_factory=lambda: {
            "agile-receivables": "https://cal.com/agilereceivables/30min",
            "agile-receivables-org": "https://cal.com/agilereceivables/30min",
            "3de43e6b-6cc0-4391-a061-2faba481bcb8": "https://cal.com/agilereceivables/30min",
            "agile-sales-marketing": "https://cal.com/agilereceivables/30min",
            "agile-sales-marketing-org": "https://cal.com/agilereceivables/30min",
            "agile sales & marketing": "https://cal.com/agilereceivables/30min",
            "0d85dc9f-1520-4bcb-8af4-8aad025255cb": "https://cal.com/agilereceivables/30min",
        }
    )

    # Microsoft Graph Integration (Inbound Email Ingestion for Support Mailbox)
    MICROSOFT_GRAPH_TENANT_ID: Optional[str] = Field(
        default=None,
        description="Microsoft Entra Directory (Tenant) ID",
    )
    MICROSOFT_GRAPH_CLIENT_ID: Optional[str] = Field(
        default=None,
        description="Microsoft Entra Application (Client) ID",
    )
    MICROSOFT_GRAPH_CLIENT_SECRET: Optional[str] = Field(
        default=None,
        repr=False,
        description="Microsoft Entra Client Secret (never exposed in logs/repr)",
    )
    MICROSOFT_GRAPH_SUPPORT_MAILBOX: str = Field(
        default="support@agilereceivables.com",
        description="Specifically approved support mailbox address for inbound ingestion.",
    )

    @field_validator("MICROSOFT_GRAPH_SUPPORT_MAILBOX")
    @classmethod
    def validate_support_mailbox(cls, v: Optional[str]) -> str:
        """
        Enforces that only the explicitly approved support mailbox can be configured.
        Rejects empty values, arbitrary mailboxes, and lookalike targets.
        """
        if not v or not v.strip():
            raise ValueError("MICROSOFT_GRAPH_SUPPORT_MAILBOX must be configured and cannot be empty.")
        normalized = v.strip().lower()
        if normalized != "support@agilereceivables.com":
            raise ValueError(
                f"Unauthorized mailbox '{normalized}'. Inbound email integration is strictly restricted "
                f"to 'support@agilereceivables.com'."
            )
        return normalized
    MICROSOFT_GRAPH_ENABLED: bool = Field(
        default=False,
        description="Fail-closed guard. Live mailbox sync is disabled by default.",
    )
    MICROSOFT_GRAPH_AUTH_FLOW: str = Field(
        default="client_credentials",
        description="Authentication flow: 'client_credentials' (Application) or 'delegated'.",
    )
    MICROSOFT_GRAPH_DELEGATED_ACCESS_TOKEN: Optional[str] = Field(
        default=None,
        repr=False,
        description="Optional pre-acquired delegated access token.",
    )
    MICROSOFT_GRAPH_DELEGATED_REFRESH_TOKEN: Optional[str] = Field(
        default=None,
        repr=False,
        description="Optional delegated refresh token for user-delegated renewal.",
    )
    MICROSOFT_GRAPH_BASE_URL: str = Field(
        default="https://graph.microsoft.com/v1.0",
        description="Microsoft Graph API base URL.",
    )
    MICROSOFT_GRAPH_TIMEOUT_SECONDS: float = Field(
        default=15.0,
        description="HTTP client timeout for Microsoft Graph requests.",
    )
    MICROSOFT_GRAPH_MAX_MESSAGES_PER_PAGE: int = Field(
        default=50,
        description="Maximum messages per page returned by Microsoft Graph.",
    )
    # Automatic background synchronization settings
    MICROSOFT_GRAPH_AUTO_SYNC_ENABLED: bool = Field(
        default=False,
        description="Fail-closed guard. Automated background sync loop is disabled by default.",
    )
    MICROSOFT_GRAPH_SYNC_INTERVAL_MINUTES: int = Field(
        default=10,
        description="Interval in minutes between automatic incremental mailbox sync ticks.",
    )
    MICROSOFT_GRAPH_SYNC_LOCK_TIMEOUT_SECONDS: int = Field(
        default=900,
        description="Concurrency lock timeout in seconds to release stale sync locks (default 15m).",
    )
    MICROSOFT_GRAPH_PRIMARY_ORG_ID: Optional[str] = Field(
        default=None,
        description="Optional explicit primary organization UUID for automated support mailbox sync.",
    )

    @property
    def is_graph_configured(self) -> bool:
        """Check if Microsoft Graph credentials are fully configured for the chosen flow."""
        if self.MICROSOFT_GRAPH_AUTH_FLOW == "delegated":
            return bool(
                self.MICROSOFT_GRAPH_DELEGATED_ACCESS_TOKEN
                or (self.MICROSOFT_GRAPH_CLIENT_ID and self.MICROSOFT_GRAPH_DELEGATED_REFRESH_TOKEN)
            )
        return bool(
            self.MICROSOFT_GRAPH_TENANT_ID
            and self.MICROSOFT_GRAPH_TENANT_ID.strip()
            and self.MICROSOFT_GRAPH_CLIENT_ID
            and self.MICROSOFT_GRAPH_CLIENT_ID.strip()
            and self.MICROSOFT_GRAPH_CLIENT_SECRET
            and self.MICROSOFT_GRAPH_CLIENT_SECRET.strip()
        )

    @property
    def is_graph_live_sync_allowed(self) -> bool:
        """
        Fail-closed guard for Microsoft Graph live synchronization.
        Requires configuration AND explicit MICROSOFT_GRAPH_ENABLED=True.
        """
        return bool(self.is_graph_configured and self.MICROSOFT_GRAPH_ENABLED)

    @property
    def is_graph_auto_sync_allowed(self) -> bool:
        """
        Fail-closed guard for automatic background synchronization.
        Requires live sync to be permitted AND MICROSOFT_GRAPH_AUTO_SYNC_ENABLED=True.
        """
        return bool(self.is_graph_live_sync_allowed and self.MICROSOFT_GRAPH_AUTO_SYNC_ENABLED)


settings = Settings()

