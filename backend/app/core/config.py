"""Application configuration for Agile Sales & Marketing Backend."""
from __future__ import annotations

from typing import Dict, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
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

    # Authentication & Security settings
    # SECRET_KEY is marked with repr=False so it is never exposed in logging or repr strings
    SECRET_KEY: str = Field(
        default="09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7",
        repr=False,
    )
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14

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
    def is_retell_inbound_configured(self) -> bool:
        """Check if Retell inbound voice provider is configured."""
        return bool(
            self.RETELL_API_KEY
            and self.RETELL_API_KEY.strip()
            and (self.RETELL_INBOUND_AGENT_ID or self.RETELL_INBOUND_CF_AGENT_ID)
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
        }
    )


settings = Settings()

