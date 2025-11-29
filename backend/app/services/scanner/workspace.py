# backend/app/services/scanner/workspace.py
from __future__ import annotations

"""
Workspace management for scans.

Each scan gets its own isolated directory tree under the configured
workspace_root:

    <workspace_root>/<project_id>/<scan_id>/
      contracts/   - Solidity sources / project files
      logs/        - tool logs (stdout/stderr, JSON logs, etc.)
      artifacts/   - reports, coverage data, any generated files
      tmp/         - temporary working data

All paths are computed using pathlib, so this works cleanly on
Windows 11 (for local dev) and inside Linux containers.
"""

from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings


@dataclass
class Workspace:
    """
    Represents the on-disk layout for a single scan's workspace.

    The runner (runner.py) and individual tools (Stage 5) will use these
    paths to read/write inputs, logs, and artifacts.
    """

    root: Path
    contracts_dir: Path
    logs_dir: Path
    artifacts_dir: Path
    tmp_dir: Path

    def ensure_created(self) -> None:
        """
        Create all workspace directories if they do not already exist.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        self.contracts_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    def path_relative_to_root(self, path: Path) -> str:
        """
        Return a POSIX-style relative path from the workspace root.

        This is useful for storing paths in the database or logs in a
        portable way, regardless of the underlying OS path separators.
        """
        try:
            rel = path.relative_to(self.root)
        except ValueError:
            # If the path is not under root, just return its name
            rel = path.name
        return rel.as_posix()


def build_workspace_root(project_id: str, scan_id: str) -> Path:
    """
    Compute the root directory for a scan workspace.

    Uses Settings.workspace_root as the base directory, which is typically
    `/workspaces` inside the backend container, but can be overridden via
    environment variables.
    """
    settings = get_settings()
    return Path(settings.workspace_root) / project_id / scan_id


def create_workspace(project_id: str, scan_id: str) -> Workspace:
    """
    Create a Workspace object for the given project/scan and ensure that
    its directories exist on disk.

    This function is the main entrypoint used by the scan runner. It
    encapsulates the directory layout so that the runner and tools do not
    need to duplicate path logic.
    """
    root = build_workspace_root(project_id, scan_id)
    workspace = Workspace(
        root=root,
        contracts_dir=root / "contracts",
        logs_dir=root / "logs",
        artifacts_dir=root / "artifacts",
        tmp_dir=root / "tmp",
    )
    workspace.ensure_created()
    return workspace
