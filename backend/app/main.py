# backend/app/main.py
from __future__ import annotations

"""
FastAPI application setup.

This module depends on:
- app.config.get_settings for configuration
- app.db.session.Base and engine for DB initialization
- app.api.api_router for route registration
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.config import get_settings
from app.db.session import Base, engine

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
)


# ---- CORS ----

app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(o) for o in settings.allowed_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- Routes ----

app.include_router(api_router, prefix="/api")


# ---- Lifecycle ----


@app.on_event("startup")
def on_startup() -> None:
    """
    Initialize database schema on startup.

    In a production-grade deployment you'll normally use Alembic migrations
    instead of `create_all`, but this keeps the system runnable out of the box.
    """
    Base.metadata.create_all(bind=engine)


# ---- Healthcheck ----


@app.get("/health", tags=["health"])
def health() -> dict:
    return {"status": "ok"}
