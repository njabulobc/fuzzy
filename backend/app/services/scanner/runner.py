from __future__ import annotations

"""backend/app/services/scanner/runner.py

Core scan runner orchestration.

Responsibilities:
- Load a Scan and its Project from the database
- Create an isolated workspace for the scan
- Ensure ToolExecution records exist for each requested tool
- Drive per-tool execution through ToolRunnerProtocol implementations
- Update Scan and ToolExecution statuses deterministically
- Build a logs snapshot for quick inspection in the UI

The runner is *tool-agnostic*. Concrete tool adapters (Slither, Echidna,
Foundry) live under ``app.services.tools`` and implement ToolRunnerProtocol.
"""


from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Dict, Protocol

from sqlalchemy.orm import Session, selectinload

from app import models
from app.db.session import SessionLocal
from app.services.scanner.workspace import (
    Workspace,
    create_workspace,
    materialize_project_sources,
)


@dataclass
class ScanContext:
    """Data bundle passed to tool runners.

    Contains:
    - project: the ORM Project instance
    - scan: the ORM Scan instance
    - workspace: the Workspace object describing filesystem layout
    """

    project: models.Project
    scan: models.Scan
    workspace: Workspace
    project_root: Path


class ToolRunnerProtocol(Protocol):
    """Minimal interface that concrete tool runners must implement."""

    name: str

    def run(
        self,
        *,
        db: Session,
        context: ScanContext,
        execution: models.ToolExecution,
    ) -> None:
        """Execute the tool and update the ToolExecution row.

        Implementations are expected to:
        - run the tool (typically via Docker)
        - update ``execution`` with exit code, paths, findings_count, etc.
        - insert normalized findings into ``models.Finding`` for the scan

        This method must be deterministic and must not implement any
        random retry strategies. Any fuzzing randomness is handled by
        the tools themselves (Echidna/Foundry) via explicit seeds.
        """
        ...


def _load_scan_context(db: Session, scan_id: str) -> ScanContext:
    """Load Scan + Project and build a Workspace.

    Raises:
        ValueError: if the scan cannot be found.
    """
    scan = (
        db.query(models.Scan)
        .options(selectinload(models.Scan.project))
        .filter(models.Scan.id == scan_id)
        .first()
    )
    if not scan:
        raise ValueError(f"Scan {scan_id} not found")

    project = scan.project
    workspace = create_workspace(project_id=project.id, scan_id=scan.id)
    project_root = materialize_project_sources(project.path, workspace)
    return ScanContext(
        project=project,
        scan=scan,
        workspace=workspace,
        project_root=project_root,
    )


def _ensure_tool_executions(db: Session, scan: models.Scan) -> None:
    """Create ToolExecution rows for all tools in scan.tools if missing.

    This function is idempotent and can be safely called multiple times
    for the same scan.
    """
    existing = (
        db.query(models.ToolExecution)
        .filter(models.ToolExecution.scan_id == scan.id)
        .all()
    )
    existing_by_tool: Dict[str, models.ToolExecution] = {te.tool: te for te in existing}

    for tool_name in scan.tools:
        if tool_name in existing_by_tool:
            continue
        db.add(
            models.ToolExecution(
                scan_id=scan.id,
                tool=tool_name,
                status=models.ToolExecutionStatus.PENDING,
                attempt=0,
                findings_count=0,
            )
        )
    db.commit()


def _build_logs_snapshot(db: Session, scan_id: str) -> str:
    """Build a compact JSON summary of per-tool execution state."""
    executions = (
        db.query(models.ToolExecution)
        .filter(models.ToolExecution.scan_id == scan_id)
        .order_by(models.ToolExecution.tool.asc())
        .all()
    )

    snapshot: list[dict] = []
    for exec_ in executions:
        snapshot.append(
            {
                "tool": exec_.tool,
                "status": exec_.status.value if exec_.status else None,
                "attempt": exec_.attempt,
                "exit_code": exec_.exit_code,
                "error": exec_.error,
                "failure_reason": exec_.failure_reason,
                "stdout_path": exec_.stdout_path,
                "stderr_path": exec_.stderr_path,
                "artifacts_path": exec_.artifacts_path,
                "findings_count": exec_.findings_count,
                "started_at": exec_.started_at.isoformat() if exec_.started_at else None,
                "finished_at": exec_.finished_at.isoformat() if exec_.finished_at else None,
                "duration_seconds": exec_.duration_seconds,
            }
        )
    return json.dumps(snapshot)


def run_scan_sync(
    scan_id: str,
    tool_runners: Dict[str, ToolRunnerProtocol],
) -> None:
    """Run a scan synchronously in the current process.

    Higher-level orchestration (Celery tasks, CLI utilities, etc.)
    can call this function by providing a mapping from tool name to
    a concrete ToolRunner implementation.
    """
    db: Session | None = None
    try:
        db = SessionLocal()
        try:
            context = _load_scan_context(db, scan_id)
        except Exception as exc:  # noqa: BLE001
            scan = (
                db.query(models.Scan)
                .filter(models.Scan.id == scan_id)
                .first()
            )
            if scan:
                scan.status = models.ScanStatus.FAILED
                scan.finished_at = datetime.utcnow()
                scan.logs = json.dumps(
                    [
                        {
                            "tool": "runner",
                            "status": models.ToolExecutionStatus.FAILED.value,
                            "error": str(exc),
                        }
                    ]
                )
                db.commit()
            return

        scan = context.scan

        # Mark scan as running (only first time)
        scan.status = models.ScanStatus.RUNNING
        scan.started_at = scan.started_at or datetime.utcnow()
        db.commit()
        db.refresh(scan)

        # Ensure ToolExecution records exist
        _ensure_tool_executions(db, scan)

        executions = (
            db.query(models.ToolExecution)
            .filter(models.ToolExecution.scan_id == scan.id)
            .order_by(models.ToolExecution.tool.asc())
            .all()
        )

        for exec_ in executions:
            runner = tool_runners.get(exec_.tool)

            if runner is None:
                # Unsupported tool requested; mark as a deterministic failure.
                exec_.status = models.ToolExecutionStatus.FAILED
                exec_.failure_reason = "unsupported_tool"
                exec_.attempt += 1
                now = datetime.utcnow()
                exec_.started_at = exec_.started_at or now
                exec_.finished_at = now
                exec_.duration_seconds = exec_.duration_seconds or 0.0
                db.commit()
                db.refresh(exec_)
                continue

            # Mark as running for this attempt
            exec_.status = models.ToolExecutionStatus.RUNNING
            exec_.attempt += 1
            if exec_.started_at is None:
                exec_.started_at = datetime.utcnow()
            db.commit()
            db.refresh(exec_)

            try:
                runner.run(db=db, context=context, execution=exec_)
            except Exception as exc:  # noqa: BLE001
                # Defensive: convert any uncaught exception into a FAILED state.
                exec_.status = models.ToolExecutionStatus.FAILED
                exec_.error = str(exc)
                exec_.failure_reason = exec_.failure_reason or "runner_exception"

            # Finalize timing; prefer durations set by the tool adapter if any.
            finished_at = datetime.utcnow()
            exec_.finished_at = finished_at
            if exec_.started_at and exec_.duration_seconds is None:
                exec_.duration_seconds = (finished_at - exec_.started_at).total_seconds()

            # If the tool adapter forgot to set a terminal status, assume success.
            if exec_.status not in {
                models.ToolExecutionStatus.SUCCEEDED,
                models.ToolExecutionStatus.FAILED,
            }:
                exec_.status = models.ToolExecutionStatus.SUCCEEDED

            db.commit()
            db.refresh(exec_)

        # Finalize scan status based on tool results
        success_count = (
            db.query(models.ToolExecution)
            .filter(
                models.ToolExecution.scan_id == scan.id,
                models.ToolExecution.status == models.ToolExecutionStatus.SUCCEEDED,
            )
            .count()
        )
        scan.finished_at = datetime.utcnow()
        scan.status = (
            models.ScanStatus.SUCCESS if success_count > 0 else models.ScanStatus.FAILED
        )
        scan.logs = _build_logs_snapshot(db, scan.id)
        db.commit()
        db.refresh(scan)

    finally:
        if db is not None:
            db.close()
