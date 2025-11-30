# backend/app/schemas/__init__.py
from __future__ import annotations

"""
Pydantic schemas for request/response models.

This module is the API contract layer and depends on:
- app.models.ScanStatus
- app.models.ToolExecutionStatus

It is used by:
- API routes
- Future Celery/scanner code where structured responses are needed
"""

from datetime import datetime
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

from app.models import ScanStatus, ToolExecutionStatus


# ---------- Project Schemas ----------


class ProjectCreate(BaseModel):
    name: str
    path: str
    meta: Optional[dict] = None


class ProjectRead(ProjectCreate):
    id: str
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Scan Schemas ----------


class ScanRequest(BaseModel):
    """
    Flexible scan creation payload.

    Either:
    - provide an existing project_id
    OR
    - provide project_name (and optionally project_path)

    target can be:
    - an explicit contract path, or
    - inferred from log_file when not provided.
    """

    project_id: str | None = None
    project_name: str | None = None
    project_path: str | None = None
    target: str | None = None
    # NOTE: Mythril removed per requirements (Slither/Echidna/Foundry only)
    tools: List[str] = Field(
        default_factory=lambda: ["slither", "echidna", "foundry"]
    )
    scan_name: str | None = None
    log_file: str | None = None
    chain: str | None = None
    meta: Optional[dict] = None

    @staticmethod
    def _normalize_target(raw_target: str | None) -> str:
        """Sanitize and normalize a scan target to a relative path.

        The API expects targets to be paths relative to the project root. Users may
        accidentally paste absolute paths (e.g., "/project/contracts") or prefix
        values with shell-style comments ("# /project/contracts"), which causes
        downstream tools like Slither to fail with "Unrecognised file/dir path".

        This helper trims whitespace, strips leading comment characters, and removes
        common absolute prefixes so the resulting value is a clean relative path.
        """

        target = (raw_target or "").strip()

        # Strip accidental leading comment markers (e.g., "# /project/contracts")
        if target.startswith("#"):
            target = target.lstrip("#").strip()

        # Convert absolute paths to project-relative ones
        if target.startswith("/project/"):
            target = target[len("/project/") :]
        elif target.startswith("/"):
            target = target.lstrip("/")

        # Normalize redundant relative prefixes
        target = target.lstrip("./")

        if not target:
            raise ValueError("Provide a target or log_file to scan")

        return target

    @model_validator(mode="after")
    def ensure_project_and_target(self) -> "ScanRequest":
        # Ensure we know which project to associate the scan with
        if not self.project_id and not (self.project_name or self.scan_name):
            raise ValueError("Provide either project_id or project_name/scan_name")

        # If project_name missing, fall back to scan_name
        if not self.project_name:
            self.project_name = self.scan_name

        # Derive target from log_file if not provided
        if not self.target:
            self.target = self.log_file

        if not self.target:
            raise ValueError("Provide a target or log_file to scan")

        self.target = self._normalize_target(self.target)

        # If we need to create a project and project_path is missing, infer from log_file
        if not self.project_id and not self.project_path:
            if self.log_file:
                self.project_path = str(Path(self.log_file).parent or ".")
            else:
                raise ValueError("Provide project_path when creating a project")

        return self


class QuickScanProject(BaseModel):
    name: str
    path: str
    meta: Optional[dict] = None


class QuickScanRequest(BaseModel):
    """
    Simple "one-shot" scan that always ensures a project exists/updated
    by name, then triggers a scan on the given target.
    """

    project: QuickScanProject
    target: str
    tools: List[str] = Field(
        default_factory=lambda: ["slither", "echidna", "foundry"]
    )

    @model_validator(mode="after")
    def normalize(self) -> "QuickScanRequest":
        self.target = ScanRequest._normalize_target(self.target)
        return self


class ScanRead(BaseModel):
    id: str
    project_id: str
    name: Optional[str]
    status: ScanStatus
    tools: List[str]
    target: str
    chain: Optional[str]
    meta: Optional[dict]
    logs: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]

    class Config:
        from_attributes = True


# ---------- Finding Schemas ----------


class FindingRead(BaseModel):
    id: str
    scan_id: str
    tool: str
    title: str
    description: str
    severity: str
    category: Optional[str]
    file_path: Optional[str]
    line_number: Optional[str]
    function: Optional[str]
    tool_version: Optional[str]
    input_seed: Optional[str]
    coverage: Optional[dict]
    assertions: Optional[dict]
    raw: Optional[dict]
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Tool Execution Schemas ----------


class ToolExecutionRead(BaseModel):
    id: str
    scan_id: str
    tool: str
    status: ToolExecutionStatus
    attempt: int
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    duration_seconds: Optional[float]
    command: Optional[list[str]]
    exit_code: Optional[int]
    stdout_path: Optional[str]
    stderr_path: Optional[str]
    environment: Optional[dict]
    artifacts_path: Optional[str]
    error: Optional[str]
    parsing_error: Optional[str]
    failure_reason: Optional[str]
    findings_count: int
    tool_version: Optional[str]
    input_seed: Optional[str]
    coverage: Optional[dict]
    assertions: Optional[dict]

    class Config:
        from_attributes = True


# ---------- Aggregated Views ----------


class ScanDetail(ScanRead):
    findings: List[FindingRead]
    tool_executions: List[ToolExecutionRead] = Field(default_factory=list)


class QuickScanResponse(BaseModel):
    project_id: str
    scan_id: str
