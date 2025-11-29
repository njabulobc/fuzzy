from __future__ import annotations

"""backend/app/services/tools/foundry_tool.py

Adapter for running **Foundry (forge)** via Docker and normalizing its findings.
"""

import json
from pathlib import Path
from typing import Iterable, List

from sqlalchemy.orm import Session

from app import models
from app.config import get_settings
from app.services.diagnostics.error_classifier import classify_tool_failure
from app.services.scanner.runner import ScanContext
from app.services.scanner.workspace import Workspace
from app.services.tools.base import (
    NormalizedFinding,
    ToolResult,
    ToolSettings,
    run_command,
    store_normalized_findings,
)

settings = get_settings()

_FAILURE_STATUSES = {"fail", "failed", "failure", "error", "panic"}


def _iter_dicts(obj: object) -> Iterable[dict]:
    """Recursive helper to iterate over all dict-like entries in a JSON tree."""
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from _iter_dicts(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_dicts(item)


def _extract_findings(payload: object, tool_version: str | None) -> List[NormalizedFinding]:
    """Convert Foundry JSON output into NormalizedFinding instances."""
    findings: List[NormalizedFinding] = []
    for entry in _iter_dicts(payload):
        status_raw = entry.get("status")
        status = str(status_raw).lower() if isinstance(status_raw, str) else ""
        success = entry.get("success")
        is_failure = status in _FAILURE_STATUSES or success is False

        if not is_failure:
            continue

        name = entry.get("name") or entry.get("test")
        description = (
            entry.get("reason")
            or entry.get("error_message")
            or entry.get("stdout")
            or "Foundry reported a failing test"
        )

        findings.append(
            NormalizedFinding(
                tool="foundry",
                title=str(name),
                description=str(description),
                severity="HIGH",
                category=str(entry.get("kind") or "test_failure"),
                file_path=entry.get("file") or entry.get("source") or entry.get("path"),
                line_number=str(entry.get("line")) if entry.get("line") else None,
                function=entry.get("contract") or entry.get("test_contract") or entry.get("function"),
                raw=entry,
                tool_version=tool_version,
            )
        )
    return findings


def _parse_foundry_output(output: str, tool_version: str | None) -> List[NormalizedFinding]:
    """Parse Foundry's line-delimited JSON output."""
    findings: List[NormalizedFinding] = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            # Non-JSON lines are ignored but preserved in stdout logs.
            continue
        findings.extend(_extract_findings(payload, tool_version))
    return findings


class FoundryToolRunner:
    """ToolRunner implementation for Foundry (forge test/fuzz/invariants)."""

    name = "foundry"

    def __init__(self) -> None:
        self.config = ToolSettings(
            timeout_seconds=getattr(settings, "foundry_timeout_seconds", 900),
            max_runtime_seconds=getattr(settings, "foundry_max_runtime_seconds", 1200),
        )

    def run(
        self,
        *,
        db: Session,
        context: ScanContext,
        execution: models.ToolExecution,
    ) -> None:
        project = context.project
        scan = context.scan
        workspace: Workspace = context.workspace

        log_dir = workspace.logs_dir / self.name
        log_dir.mkdir(parents=True, exist_ok=True)

        project_path = Path(project.path).resolve()
        target_rel = scan.target
        target_path = Path(target_rel)

        container_root = "/project"
        container_target = f"{container_root}/{target_rel}"

        cmd: List[str] = [
            getattr(settings, "docker_binary", "docker"),
            "run",
            "--rm",
            "-v",
            f"{project_path}:{container_root}",
            settings.foundry_image,
            "forge",
            "test",
            "--json",
            "--root",
            container_root,
        ]

        if target_path.suffix:
            cmd.extend(["--match-path", container_target])

        result: ToolResult = run_command(
            cmd,
            timeout=self.config.timeout_seconds,
            env=self.config.env,
            workdir=workspace.root,
            log_dir=log_dir,
            max_runtime=self.config.max_runtime_seconds,
        )

        execution.command = result.command
        execution.exit_code = result.return_code
        execution.stdout_path = workspace.path_relative_to_root(Path(result.stdout_path))
        execution.stderr_path = workspace.path_relative_to_root(Path(result.stderr_path))
        execution.environment = result.environment
        execution.error = result.error
        execution.parsing_error = result.parsing_error
        execution.artifacts_path = workspace.path_relative_to_root(Path(result.artifacts_path))
        execution.tool_version = result.tool_version or f"docker:{settings.foundry_image}"

        if not result.success:
            execution.failure_reason = classify_tool_failure(self.name, result)

        findings = _parse_foundry_output(result.output or "", execution.tool_version)

        if not findings and not result.success and not execution.failure_reason:
            execution.failure_reason = "command-failed"

        execution.findings_count = store_normalized_findings(db, scan, findings)
        execution.status = (
            models.ToolExecutionStatus.SUCCEEDED if result.success else models.ToolExecutionStatus.FAILED
        )
