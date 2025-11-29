# backend/app/models/__init__.py
from __future__ import annotations

"""
Core ORM models for the fuzz backend.

This module depends on:
- app.db.session.Base for the declarative base

It is used by:
- app.schemas (for type references)
- API routes (for querying and persisting data)
- Celery tasks / scanner services for storing scan results

Models:
- Project: logical grouping of smart contracts
- Scan: a single run of tools over a project/target
- Finding: normalized vulnerability / issue from any tool
- ToolExecution: per-tool execution metadata for a scan
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.db.session import Base


class ScanStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class ToolExecutionStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"


class Project(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, unique=True, nullable=False)
    path = Column(String, nullable=False)  # path to project root (host or workspace)
    meta = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    scans = relationship(
        "Scan",
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Scan(Base):
    __tablename__ = "scans"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)

    # Optional human-friendly name for the scan
    name = Column(String, nullable=True)

    # Target (file or directory) relative to project.path or workspace
    target = Column(String, nullable=False)

    status = Column(Enum(ScanStatus), default=ScanStatus.PENDING, nullable=False)

    # List of tools: ["slither", "echidna", "foundry"]
    tools = Column(JSON, nullable=False, default=list)

    # Optional chain/network tag and arbitrary metadata
    chain = Column(String, nullable=True)
    meta = Column(JSON, nullable=True)

    # Aggregated logs snapshot across tools (JSON stringified by scanner)
    logs = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    project = relationship("Project", back_populates="scans")
    findings = relationship(
        "Finding",
        back_populates="scan",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    tool_executions = relationship(
        "ToolExecution",
        back_populates="scan",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Finding(Base):
    """
    Normalized finding produced by the scanner using NormalizedFinding.

    Fields mirror app.normalization.findings.NormalizedFinding so that
    tool adapters can store structured data directly here.
    """

    __tablename__ = "findings"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    scan_id = Column(String, ForeignKey("scans.id", ondelete="CASCADE"), nullable=False)

    tool = Column(String, nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    severity = Column(String, nullable=False)  # CRITICAL/HIGH/MEDIUM/LOW/INFO

    category = Column(String, nullable=True)
    file_path = Column(String, nullable=True)
    line_number = Column(String, nullable=True)
    function = Column(String, nullable=True)

    tool_version = Column(String, nullable=True)
    input_seed = Column(String, nullable=True)
    coverage = Column(JSON, nullable=True)
    assertions = Column(JSON, nullable=True)

    raw = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    scan = relationship("Scan", back_populates="findings")


class ToolExecution(Base):
    """
    Per-tool execution record for a scan.

    This is populated from ToolResult (see services/tools/base.py in later stages)
    and enriched by the scanner runner.
    """

    __tablename__ = "tool_executions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    scan_id = Column(String, ForeignKey("scans.id", ondelete="CASCADE"), nullable=False)

    tool = Column(String, nullable=False)
    status = Column(
        Enum(ToolExecutionStatus),
        default=ToolExecutionStatus.PENDING,
        nullable=False,
    )

    # Retry bookkeeping
    attempt = Column(Integer, nullable=False, default=0)

    # Timing info
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)

    # Command + environment used for the tool execution
    command = Column(JSON, nullable=True)  # list[str]
    exit_code = Column(Integer, nullable=True)
    stdout_path = Column(String, nullable=True)
    stderr_path = Column(String, nullable=True)
    environment = Column(JSON, nullable=True)
    artifacts_path = Column(String, nullable=True)

    # Diagnostics and summary
    error = Column(Text, nullable=True)
    parsing_error = Column(Text, nullable=True)
    failure_reason = Column(String, nullable=True)
    findings_count = Column(Integer, nullable=False, default=0)
    tool_version = Column(String, nullable=True)
    input_seed = Column(String, nullable=True)
    coverage = Column(JSON, nullable=True)
    assertions = Column(JSON, nullable=True)

    scan = relationship("Scan", back_populates="tool_executions")
