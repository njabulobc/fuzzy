# backend/app/api/__init__.py
from __future__ import annotations

"""
API router aggregation.

This module exposes a single `api_router` that the FastAPI app
can include with a prefix such as `/api`.
"""

from fastapi import APIRouter

from . import projects, scans, findings, tools

api_router = APIRouter()
api_router.include_router(projects.router)
api_router.include_router(scans.router)
api_router.include_router(findings.router)
api_router.include_router(tools.router)
