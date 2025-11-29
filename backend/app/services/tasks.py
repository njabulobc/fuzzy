# backend/app/services/tasks.py
from __future__ import annotations

"""
Celery tasks for the fuzz backend.

Currently provides:
- run_scan_task: execute a scan (Slither, Echidna, Foundry) in the background.
"""

from celery import Task

from app.services.celery_app import celery_app
from app.services.scanner import execute_scan


@celery_app.task(bind=True, name="app.services.tasks.run_scan_task")
def run_scan_task(self: Task, scan_id: str) -> None:
    """
    Celery task: execute the full scan pipeline for a given scan_id.

    This calls app.services.scanner.execute_scan, which will:
    - load the scan and project from the database
    - create a workspace
    - run Slither, Echidna, Foundry (via Docker) as requested
    - persist ToolExecution and Finding records
    - update Scan status and logs
    """
    execute_scan(scan_id)
