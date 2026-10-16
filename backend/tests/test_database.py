"""Unit tests for database configuration and session lifecycle."""
from app.core.config import Settings
from app.core.database import Base, get_db
from app.models import BusinessProfile, Organization, User


def test_configuration_loads_without_real_credentials():
    settings = Settings(
        DATABASE_URL="postgresql+psycopg://dummy:dummy@localhost:5432/test_db",
        HUBSPOT_ACCESS_TOKEN=None,
    )
    assert settings.DATABASE_URL == "postgresql+psycopg://dummy:dummy@localhost:5432/test_db"
    assert settings.is_hubspot_configured is False


def test_model_imports_and_metadata_registration():
    table_names = list(Base.metadata.tables.keys())
    assert "organizations" in table_names
    assert "users" in table_names
    assert "business_profiles" in table_names


def test_get_db_session_lifecycle():
    gen = get_db()
    db = next(gen)
    assert db is not None
    try:
        # Verify db session is active
        assert db.is_active
    finally:
        try:
            next(gen)
        except StopIteration:
            pass
