# backend/app/api/findings.py
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import models, schemas
from app.db.session import get_db

router = APIRouter(prefix="/findings", tags=["findings"])


@router.get("", response_model=list[schemas.FindingRead])
def list_findings(
    db: Session = Depends(get_db),
    tool: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    scan_id: str | None = Query(default=None),
) -> list[schemas.FindingRead]:
    query = db.query(models.Finding)
    if tool:
        query = query.filter(models.Finding.tool == tool)
    if severity:
        query = query.filter(models.Finding.severity == severity)
    if scan_id:
        query = query.filter(models.Finding.scan_id == scan_id)
    return query.order_by(models.Finding.created_at.desc()).all()
