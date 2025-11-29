# backend/app/api/tools.py
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import get_settings

router = APIRouter(prefix="/tools", tags=["tools"])


class ToolInfo(BaseModel):
    name: str
    kind: str
    docker_image: str


@router.get("", response_model=list[ToolInfo])
def list_tools() -> list[ToolInfo]:
    """
    Return the supported tools and their Docker images.

    All tools are expected to run inside containers; no host-installed
    security tools are used, in line with the project constraints.
    """
    settings = get_settings()
    return [
        ToolInfo(
            name="slither",
            kind="static-analysis",
            docker_image=settings.slither_image,
        ),
        ToolInfo(
            name="echidna",
            kind="property-based-fuzzing",
            docker_image=settings.echidna_image,
        ),
        ToolInfo(
            name="foundry",
            kind="tests-fuzzing-invariants",
            docker_image=settings.foundry_image,
        ),
    ]
