from __future__ import annotations

"""backend/app/services/tools/echidna_tool.py

Adapter for running **Echidna** via Docker and normalizing its findings.

Key points in this version:
- We distinguish between:
    * "host_project_root": path on the HOST filesystem (used in `docker run -v`).
    * "container_root": fixed `/project` path inside the Echidna container.
- The host path is derived from `project.path` + an optional
  `settings.projects_host_root` base; this avoids trying to mount paths that
  only exist inside the worker container (the root cause of earlier failures).
- The scan's `target` is mapped to a path inside the Echidna container
  (under `/project`) in a robust way, so "contracts", "./", "MyToken.sol",
  "contracts/EchidnaTokenTest.sol" all resolve sensibly.
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


def _resolve_host_project_root(
    *,
    project: models.Project,
    project_root: Path,
) -> Path:
    """
    Determine the HOST path that should be bind-mounted into the Echidna container.

    This is the same logic as in the Slither adapter:

    - Docker always interprets the left-hand side of `-v HOST_PATH:/project`
      as a path on the HOST, not inside the worker container.
    - Previously, we were passing a container-only path (e.g. `/contracts`),
      which does not exist on the host, so the fuzzing container saw an
      empty `/project` directory.

    Resolution strategy:
    1. If `project.path` looks like a Windows-style absolute path
       (`"C:/..."` or `"D:\..."`), we treat it as the host path and use it
       directly.
    2. Otherwise, if `settings.projects_host_root` is defined, we treat
       `project.path` as a relative path under that base. For Docker Compose:

           PROJECTS_HOST_ROOT=C:/Users/you/yourrepo
           project.path="contracts"

       → host_project_root = "C:/Users/you/yourrepo/contracts"
    3. If neither of the above applies, we fall back to `project_root`,
       which preserves the previous behaviour for non-Docker or local runs.
    """
    raw_path = getattr(project, "path", None)
    base = getattr(settings, "projects_host_root", None)  # optional; may be None

    if isinstance(raw_path, str) and raw_path.strip():
        raw_str = raw_path.strip()

        # Heuristic: contains a drive letter (e.g. "C:") → already a host path.
        if ":" in raw_str:
            return Path(raw_str)

        # Container-style absolute ("/contracts" or "/workspaces/..."):
        # treat as relative to the configured host base, if provided.
        if base:
            rel = Path(raw_str.lstrip("/\\"))
            return Path(base) / rel

    # Fallback: keep the old behaviour for environments where project_root
    # is already a host path.
    return project_root


def _resolve_container_target(
    *,
    scan_target: str | None,
    project_root: Path,
    container_root: str = "/project",
) -> str:
    """
    Map the scan's target (as stored in the DB) to a path inside the Echidna container.

    The Echidna container always sees the project under `container_root`
    (typically `/project`). This helper makes sure various user inputs map
    nicely:

    - None, "", ".", "/"     → treat as "project root": `/project`
      (Echidna will then need config inside that folder.)
    - "contracts"            → `/project` if project_root.name == "contracts`
    - "contracts/Test.sol"   → `/project/Test.sol` if project_root.name == "contracts`
    - "EchidnaTokenTest.sol" → `/project/EchidnaTokenTest.sol`
    """
    raw_target = (scan_target or "").strip()
    if not raw_target or raw_target in (".", "/"):
        return container_root

    rel = Path(raw_target.lstrip("/"))

    # If the first segment matches the project root folder name (e.g. "contracts"),
    # strip it to avoid `/project/contracts/...` when `/project` is already that folder.
    parts = rel.parts
    if parts and parts[0] == project_root.name:
        if len(parts) == 1:
            # Target was exactly "contracts" → treat as project root
            rel = Path(".")
        else:
            rel = Path(*parts[1:])

    if str(rel) in ("", "."):
        return container_root

    return f"{container_root}/{rel.as_posix()}"


class EchidnaToolRunner:
    """ToolRunner implementation for Echidna (property-based fuzzing)."""

    name = "echidna"

    def __init__(self) -> None:
        # Timeouts and fuzz duration come from settings.
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
        project_root = context.project_root  # logical project directory for this scan

        log_dir = workspace.logs_dir / self.name
        log_dir.mkdir(parents=True, exist_ok=True)

        # --- 1. Resolve paths -------------------------------------------------
        container_root = "/project"

        # Host path used for `docker run -v HOST_PATH:/project`.
        host_project_root = _resolve_host_project_root(
            project=project,
            project_root=project_root,
        )

        # Path to pass to `echidna-test` inside the container.
        container_target = _resolve_container_target(
            scan_target=getattr(scan, "target", None),
            project_root=project_root,
            container_root=container_root,
        )

        # --- 2. Build the Docker command -------------------------------------
        # NOTE: The left side of `-v` *must* be a HOST path, not a container path.
        cmd: List[str] = [
            getattr(settings, "docker_binary", "docker"),
            "run",
            "--rm",
            "-v",
            f"{host_project_root}:{container_root}",
            settings.echidna_image,
            "echidna-test",
            container_target,
            "--format",
            "json",
        ]

        # Optional fuzz duration limit (seconds)
        if self.config.fuzz_duration_seconds:
            # Older Echidna versions use --timeout rather than --test-duration
            cmd.extend(["--timeout", str(self.config.fuzz_duration_seconds)])


        result: ToolResult = run_command(
            cmd,
            timeout=self.config.timeout_seconds,
            env=self.config.env,
            workdir=workspace.root,
            log_dir=log_dir,
            max_runtime=self.config.max_runtime_seconds or self.config.fuzz_duration_seconds,
        )

        # --- 3. Populate execution metadata ----------------------------------
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

        # --- 4. Parse Echidna JSON output into NormalizedFinding -------------
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

        # --- 5. Persist findings & final status ------------------------------
        execution.findings_count = store_normalized_findings(db, scan, findings)
        execution.status = (
            models.ToolExecutionStatus.SUCCEEDED if result.success else models.ToolExecutionStatus.FAILED
        )
