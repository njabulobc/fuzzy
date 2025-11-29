from __future__ import annotations

"""backend/app/services/tools/slither_tool.py

Adapter for running **Slither** via Docker and normalizing its findings.
"""

import json
from pathlib import Path
from typing import List

from sqlalchemy.orm import Session

from app import models
from app.config import get_settings
from app.services.diagnostics.error_classifier import classify_tool_failure
from app.services.scanner.runner import ScanContext, ToolRunnerProtocol
from app.services.scanner.workspace import Workspace
from app.services.tools.base import (
    NormalizedFinding,
    ToolResult,
    ToolSettings,
    run_command,
    store_normalized_findings,
)

settings = get_settings()


class SlitherToolRunner:
    """ToolRunner implementation for Slither (static analysis)."""

    name = "slither"

    def __init__(self) -> None:
        self.config = ToolSettings(
            timeout_seconds=getattr(settings, "slither_timeout_seconds", 600),
            max_runtime_seconds=getattr(settings, "slither_max_runtime_seconds", 900),
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
        container_target = f"/project/{target_rel}"

        cmd: List[str] = [
            getattr(settings, "docker_binary", "docker"),
            "run",
            "--rm",
            "-v",
            f"{project_path}:/project",
            settings.slither_image,
            "slither",
            container_target,
            "--json",
            "-",
        ]

        result: ToolResult = run_command(
            cmd,
            timeout=self.config.timeout_seconds,
            env=self.config.env,
            workdir=workspace.root,
            log_dir=log_dir,
            max_runtime=self.config.max_runtime_seconds,
        )

        # Populate execution metadata
        execution.command = result.command
        execution.exit_code = result.return_code
        execution.stdout_path = workspace.path_relative_to_root(Path(result.stdout_path))
        execution.stderr_path = workspace.path_relative_to_root(Path(result.stderr_path))
        execution.environment = result.environment
        execution.error = result.error
        execution.parsing_error = result.parsing_error
        execution.artifacts_path = workspace.path_relative_to_root(Path(result.artifacts_path))
        execution.tool_version = result.tool_version or f"docker:{settings.slither_image}"

        # Classify failure if tool did not succeed
        if not result.success:
            execution.failure_reason = classify_tool_failure(self.name, result)

        findings: List[NormalizedFinding] = []

        if result.success and result.output:
            try:
                data = json.loads(result.output)
                for issue in data.get("results", {}).get("detectors", []):
                    elements = issue.get("elements", [{}])
                    src_map = elements[0].get("source_mapping", {}) if elements else {}
                    filename = src_map.get("filename_relative") or src_map.get("filename_absolute")
                    lines = src_map.get("lines") or ["?"]

                    findings.append(
                        NormalizedFinding(
                            tool="slither",
                            title=issue.get("check", "slither finding"),
                            description=issue.get("description", ""),
                            severity=str(issue.get("impact", "INFO")).upper(),
                            category=issue.get("check"),
                            file_path=filename,
                            line_number=str(lines[0]) if lines else None,
                            function=elements[0].get("type") if elements else None,
                            raw=issue,
                            tool_version=execution.tool_version,
                        )
                    )
            except json.JSONDecodeError as exc:
                result.parsing_error = str(exc)
                execution.parsing_error = str(exc)
                execution.failure_reason = classify_tool_failure(self.name, result)

        execution.findings_count = store_normalized_findings(db, scan, findings)
        execution.status = (
            models.ToolExecutionStatus.SUCCEEDED if result.success else models.ToolExecutionStatus.FAILED
        )
