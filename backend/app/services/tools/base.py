from __future__ import annotations

"""backend/app/services/tools/base.py

Shared utilities for running security tools inside Docker containers.

This module provides:

- ToolSettings: per-tool runtime configuration (timeouts, env, etc.)
- ToolResult: structured result for a single tool invocation
- run_command: low-level helper that executes a command and captures logs
- detect_tool_version: small helper for binaries that support --version
- NormalizedFinding: neutral in-memory finding representation
- store_normalized_findings: persistence helper for normalized findings

Higher-level tool adapters (slither_tool, echidna_tool, foundry_tool)
build on top of these helpers.

NOTE: We invoke tools via Docker (`docker run ...`) from the adapters to
respect the project requirement that **no host-installed tools** are used.
"""

import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app import models


@dataclass
class ToolSettings:
    """Per-tool runtime settings."""

    timeout_seconds: int = 600
    max_runtime_seconds: int | None = None
    fuzz_duration_seconds: int | None = None
    env: Dict[str, str] = field(default_factory=dict)


@dataclass
class ToolResult:
    """Result of a single tool invocation."""

    success: bool
    output: str
    error: str | None = None
    return_code: int | None = None
    command: list[str] | None = None
    stdout_path: str | None = None
    stderr_path: str | None = None
    environment: dict[str, str] | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_seconds: float | None = None
    parsing_error: str | None = None
    failure_reason: str | None = None
    artifacts_path: str | None = None
    tool_version: str | None = None


def _safe_read(path: Path) -> str:
    try:
        return path.read_text()
    except OSError:
        return ""


def run_command(
    cmd: List[str],
    *,
    timeout: int = 600,
    env: dict[str, str] | None = None,
    workdir: str | Path | None = None,
    log_dir: str | Path | None = None,
    max_runtime: int | None = None,
) -> ToolResult:
    """Run a command and capture stdout/stderr into log files.

    This helper is used by all tool adapters. It is intentionally agnostic
    to Docker; the adapters build `cmd` including `docker run ...` if needed.
    """
    log_dir_path = Path(log_dir or Path.cwd() / "logs")
    log_dir_path.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir_path / "stdout.log"
    stderr_path = log_dir_path / "stderr.log"

    environment = os.environ.copy()
    environment.update(env or {})

    started_at = datetime.utcnow()
    try:
        with stdout_path.open("w", encoding="utf-8", errors="ignore") as stdout, stderr_path.open(
            "w", encoding="utf-8", errors="ignore"
        ) as stderr:
            proc = subprocess.run(
                cmd,
                stdout=stdout,
                stderr=stderr,
                text=True,
                timeout=max_runtime or timeout,
                check=False,
                cwd=str(workdir) if workdir is not None else None,
                env=environment,
            )
        finished_at = datetime.utcnow()
        output = _safe_read(stdout_path)
        error_output = _safe_read(stderr_path)
        return ToolResult(
            success=proc.returncode == 0,
            output=output,
            error=error_output or None,
            return_code=proc.returncode,
            command=cmd,
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            environment=environment,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=(finished_at - started_at).total_seconds(),
            artifacts_path=str(log_dir_path),
            # Detailed failure_reason will be set by error_classifier.
            failure_reason=None,
        )
    except subprocess.TimeoutExpired:
        finished_at = datetime.utcnow()
        return ToolResult(
            success=False,
            output=_safe_read(stdout_path),
            error="timeout",
            return_code=None,
            command=cmd,
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            environment=environment,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=(finished_at - started_at).total_seconds(),
            artifacts_path=str(log_dir_path),
            failure_reason="timeout",
        )
    except OSError as exc:
        finished_at = datetime.utcnow()
        return ToolResult(
            success=False,
            output=_safe_read(stdout_path),
            error=str(exc),
            return_code=None,
            command=cmd,
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            environment=environment,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=(finished_at - started_at).total_seconds(),
            artifacts_path=str(log_dir_path),
            failure_reason="process-spawn-error",
        )


@lru_cache(maxsize=32)
def detect_tool_version(binary: str) -> str | None:
    """Best-effort version detection for non-Docker binaries."""
    try:
        proc = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        output = (proc.stdout or proc.stderr or "").strip()
        return output.splitlines()[0] if output else None
    except OSError:
        return None


@dataclass
class NormalizedFinding:
    """In-memory representation of a tool finding."""

    tool: str
    title: str
    description: str
    severity: str
    category: str | None = None
    file_path: str | None = None
    line_number: str | None = None
    function: str | None = None
    raw: Dict[str, Any] | None = None
    tool_version: str | None = None
    input_seed: str | None = None
    coverage: Dict[str, Any] | None = None
    assertions: Dict[str, Any] | None = None


def store_normalized_findings(
    db: Session,
    scan: models.Scan,
    findings: list[NormalizedFinding],
) -> int:
    """Persist a list of NormalizedFinding into the database."""
    count = 0
    for f in findings:
        db.add(
            models.Finding(
                scan_id=scan.id,
                tool=f.tool,
                title=f.title,
                description=f.description,
                severity=f.severity,
                category=f.category,
                file_path=f.file_path,
                line_number=f.line_number,
                function=f.function,
                raw=f.raw,
                tool_version=f.tool_version,
                input_seed=f.input_seed,
                coverage=f.coverage,
                assertions=f.assertions,
            )
        )
        count += 1
    db.commit()
    return count
