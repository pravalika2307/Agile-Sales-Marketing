"""Unit tests for application configuration."""
from app.core.config import Settings


def test_settings_token_not_in_repr():
    token = "secret-super-confidential-token"
    s = Settings(HUBSPOT_ACCESS_TOKEN=token)
    repr_str = repr(s)
    # Token must NEVER appear in the representation
    assert token not in repr_str
    assert s.HUBSPOT_ACCESS_TOKEN == token
    assert s.is_hubspot_configured is True


def test_settings_unconfigured():
    s = Settings(HUBSPOT_ACCESS_TOKEN=None)
    assert s.is_hubspot_configured is False

    s2 = Settings(HUBSPOT_ACCESS_TOKEN="   ")
    assert s2.is_hubspot_configured is False


def test_settings_resend_token_not_in_repr():
    resend_key = "re_super_secret_resend_api_key_12345"
    s = Settings(RESEND_API_KEY=resend_key, EMAIL_FROM_ADDRESS="sales@mycompany.com")
    repr_str = repr(s)
    # Resend API key must NEVER appear in the representation
    assert resend_key not in repr_str
    assert s.RESEND_API_KEY == resend_key
    assert s.EMAIL_FROM_ADDRESS == "sales@mycompany.com"
    assert s.is_resend_configured is True


def test_settings_resend_unconfigured():
    # Missing key
    s1 = Settings(RESEND_API_KEY=None, EMAIL_FROM_ADDRESS="sales@mycompany.com")
    assert s1.is_resend_configured is False

    # Missing email
    s2 = Settings(RESEND_API_KEY="re_123", EMAIL_FROM_ADDRESS=None)
    assert s2.is_resend_configured is False

    # Empty strings
    s3 = Settings(RESEND_API_KEY="  ", EMAIL_FROM_ADDRESS="   ")
    assert s3.is_resend_configured is False

