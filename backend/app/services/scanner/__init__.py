# backend/app/services/scanner/__init__.py
from __future__ import annotations

"""
Scanner service package.

This package provides:
- Workspace management helpers (workspace.py)
- Core scan runner orchestration (runner.py)
- A high-level execute_scan(scan_id) convenience helper

Concrete tool adapters (Slither, Echidna, Foundry) live under
app.services.tools and are wired in at runtime by execute_scan.
"""

from .workspace import Workspace, create_workspace  # noqa: F401
from .runner import ScanContext, ToolRunnerProtocol, run_scan_sync  # noqa: F401


def execute_scan(scan_id: str) -> None:
    """
    High-level entrypoint to execute a scan with all supported tools.

    This helper:
    - constructs the default set of tool runners from app.services.tools
    - calls run_scan_sync(scan_id, tool_runners)

    It is safe to call from:
    - Celery tasks
    - CLI utilities
    - synchronous scripts
    """
    # Import inside the function to avoid circular imports at module load time.
    from app.services.tools import get_default_tool_runners
    from app.services.scanner.runner import run_scan_sync as _run_scan_sync

    tool_runners = get_default_tool_runners()
    _run_scan_sync(scan_id, tool_runners)
