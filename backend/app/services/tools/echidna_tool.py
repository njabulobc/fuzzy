from __future__ import annotations

"""backend/app/services/tools/echidna_tool.py

Adapter for running **Echidna** via Docker and normalizing its findings.
"""

import json
from pathlib import Path
from typing import List

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


class EchidnaToolRunner:
    """ToolRunner implementation for Echidna (property-based fuzzing)."""

    name = "echidna"

    def __init__(self) -> None:
        self.config = ToolSettings(
            timeout_seconds=getattr(settings, "echidna_timeout_seconds", 900),
            max_runtime_seconds=getattr(settings, "echidna_max_runtime_seconds", 1200),
            fuzz_duration_seconds=getattr(settings, "echidna_fuzz_duration_seconds", None),
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
            settings.echidna_image,
            "echidna-test",
            container_target,
            "--format",
            "json",
        ]

        if self.config.fuzz_duration_seconds:
            cmd.extend(["--test-duration", str(self.config.fuzz_duration_seconds)])

        result: ToolResult = run_command(
            cmd,
            timeout=self.config.timeout_seconds,
            env=self.config.env,
            workdir=workspace.root,
            log_dir=log_dir,
            max_runtime=self.config.max_runtime_seconds or self.config.fuzz_duration_seconds,
        )

        execution.command = result.command
        execution.exit_code = result.return_code
        execution.stdout_path = workspace.path_relative_to_root(Path(result.stdout_path))
        execution.stderr_path = workspace.path_relative_to_root(Path(result.stderr_path))
        execution.environment = result.environment
        execution.error = result.error
        execution.parsing_error = result.parsing_error
        execution.artifacts_path = workspace.path_relative_to_root(Path(result.artifacts_path))
        execution.tool_version = result.tool_version or f"docker:{settings.echidna_image}"

        if not result.success:
            execution.failure_reason = classify_tool_failure(self.name, result)

        findings: List[NormalizedFinding] = []

        if result.success and result.output:
            try:
                data = json.loads(result.output)

                for issue in data.get("errors", []):
                    findings.append(
                        NormalizedFinding(
                            tool="echidna",
                            title=issue.get("test", "Echidna issue"),
                            description=issue.get("message", ""),
                            severity="HIGH",
                            category="echidna_property_failure",
                            file_path=issue.get("file"),
                            line_number=str(issue.get("line")) if issue.get("line") is not None else None,
                            function=issue.get("property"),
                            raw=issue,
                            tool_version=execution.tool_version,
                            input_seed=issue.get("seed"),
                            assertions={"property": issue.get("property")},
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
