# backend/app/services/celery_app.py
from __future__ import annotations

"""
Celery application configuration for background scan execution.

This module defines a single Celery instance:

    celery_app = Celery(...)

It is used by:
- app.services.tasks (for task definitions)
- the worker entrypoint (Stage 10 Dockerization) via
  `celery -A app.services.celery_app.celery_app worker -Q scans`
"""

from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "scan_tasks",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.services.tasks"],
)

# Automatically discover tasks in any "tasks.py" under the `app` package
celery_app.autodiscover_tasks(["app"])

# Route scan-related tasks to a dedicated queue
celery_app.conf.task_routes = {
    "app.services.tasks.*": {"queue": "scans"},
}
