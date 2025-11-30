from __future__ import annotations

"""backend/app/services/tools/slither_tool.py

Adapter for running **Slither** via Docker and normalizing its findings.

Key points in this version:
- We distinguish between:
    * "host_project_root": path on the HOST filesystem (used in `docker run -v`).
    * "container_project_root": fixed `/project` path inside the Slither container.
- The host path is derived from `project.path` + an optional
  `settings.projects_host_root` base; this avoids trying to mount paths that
  only exist inside the worker container (the root cause of earlier failures).
- The scan's `target` is mapped to a path inside the Slither container
  (under `/project`) in a robust way, so "contracts", "./", "MyToken.sol",
  "contracts/MyToken.sol" all resolve sensibly.
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
    Determine the HOST path that should be bind-mounted into the Slither container.

    This function is critical for Docker-in-Docker setups:

    - Docker always interprets the left-hand side of `-v HOST_PATH:/project`
      as a path on the HOST, not inside the worker container.
    - Previously, we were passing a container-only path (e.g. `/contracts` or
      `/workspaces/...`), which does not exist on the host, so the analysis
      container saw an empty `/project` directory.

    Resolution strategy:
    1. If `project.path` clearly looks like a Windows-style absolute path
       (`"C:/..."` or `"D:\..."`), we treat it as the host path and use it
       directly.
    2. Otherwise, if `settings.projects_host_root` is defined, we treat
       `project.path` as a relative path under that base. This is the
       recommended setup for Docker Compose:

           PROJECTS_HOST_ROOT=C:/Users/you/yourrepo
           project.path="contracts"

       → host_project_root = "C:/Users/you/yourrepo/contracts"
    3. If neither of the above applies, we fall back to `project_root`,
       which preserves the previous behaviour for non-Docker or local runs.
    """
    raw_path = getattr(project, "path", None)
    base = getattr(settings, "projects_host_root", None)  # optional; may not exist

    if isinstance(raw_path, str) and raw_path.strip():
        raw_str = raw_path.strip()

        # Heuristic: if it contains a drive letter (e.g. "C:"), assume it's
        # already a host filesystem path that Docker can understand.
        if ":" in raw_str:
            return Path(raw_str)

        # Container-style absolute (e.g. "/contracts" or "/workspaces/..."):
        # treat as relative to the configured host base, if any.
        if base:
            # Strip leading slashes/backslashes so we can safely join.
            rel = Path(raw_str.lstrip("/\\"))
            return Path(base) / rel

    # Fallback: keep the old behaviour; this works for non-Docker environments
    # where project_root is already a host path.
    return project_root


def _resolve_container_target(
    *,
    scan_target: str | None,
    project_root: Path,
    container_root: str = "/project",
) -> str:
    """
    Map the scan's target (as stored in the DB) to a path inside the container.

    The Slither container always sees the code under `container_root`
    (typically `/project`). This helper makes sure various user inputs map
    sensibly:

    - None, "", ".", "/"  → scan the whole project: `/project`
    - "contracts"         → `/project` if project_root.name == "contracts`
    - "contracts/My.sol"  → `/project/My.sol` if project_root.name == "contracts`
    - "My.sol"            → `/project/My.sol`
    """
    raw_target = (scan_target or "").strip()
    if not raw_target or raw_target in (".", "/"):
        return container_root

    # Normalize to a relative path
    rel = Path(raw_target.lstrip("/"))

    # If the first segment matches the project root folder name (common case:
    # project_root == ".../contracts" and target == "contracts/MyToken.sol"),
    # strip it so that we don't end up with `/project/contracts/...`.
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


class SlitherToolRunner:
    """ToolRunner implementation for Slither (static analysis)."""

    name = "slither"

    def __init__(self) -> None:
        # Timeouts are still driven by settings; we reuse ToolSettings so this
        # behaves like other tools in the system.
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

        # Path the Slither container should analyze (inside the container).
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
            settings.slither_image,
            "slither",
            container_target,
            "--json",
            "-",  # emit JSON to stdout so we can capture it directly
        ]

        result: ToolResult = run_command(
            cmd,
            timeout=self.config.timeout_seconds,
            env=self.config.env,
            workdir=workspace.root,
            log_dir=log_dir,
            max_runtime=self.config.max_runtime_seconds,
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
        execution.tool_version = result.tool_version or f"docker:{settings.slither_image}"

        # Classify failure if tool did not succeed
        if not result.success:
            execution.failure_reason = classify_tool_failure(self.name, result)

        # --- 4. Parse Slither JSON output into NormalizedFinding -------------
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
                # Mark parsing failure but keep stdout/stderr/artifacts for debugging.
                result.parsing_error = str(exc)
                execution.parsing_error = str(exc)
                execution.failure_reason = classify_tool_failure(self.name, result)

        # --- 5. Persist findings & final status ------------------------------
        execution.findings_count = store_normalized_findings(db, scan, findings)
        execution.status = (
            models.ToolExecutionStatus.SUCCEEDED if result.success else models.ToolExecutionStatus.FAILED
        )
