"""Database engine, session management, and base declarative class."""
from __future__ import annotations

from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

# Engine configuration with sensible connection pooling
engine_kwargs = {}
if settings.DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs["pool_pre_ping"] = True

engine = create_engine(settings.DATABASE_URL, **engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy domain models."""
    pass


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency yielding a scoped database session.
    Guarantees session cleanup upon request completion.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
