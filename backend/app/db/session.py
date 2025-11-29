# backend/app/db/session.py
from __future__ import annotations

"""
Database session and Base ORM declarations.

This module depends on:
- app.config.settings.get_settings for the DATABASE_URL
It is imported by:
- app.models (for Base)
- app.main (for engine/Base)
- any code needing a DB session (via SessionLocal or get_db)
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import get_settings

# Load settings once; get_settings() is cached in app.config.settings
settings = get_settings()

# SQLAlchemy engine for PostgreSQL (or any DB configured in DATABASE_URL)
engine = create_engine(
    settings.database_url,
    future=True,
)

# Session factory used throughout the app
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    future=True,
)

# Base class for all ORM models
Base = declarative_base()


def get_db():
    """
    FastAPI dependency that yields a DB session and ensures it is closed.

    Example usage in a route:
        from app.db.session import get_db
        def endpoint(db: Session = Depends(get_db)): ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
