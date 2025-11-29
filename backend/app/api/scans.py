from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from app import models, schemas
from app.db.session import get_db
from app.services.scanner import execute_scan

router = APIRouter(prefix="/scans", tags=["scans"])


def _dispatch_scan(db: Session, scan: models.Scan) -> None:
    """Kick off scan execution via Celery, with a synchronous fallback."""

    meta = scan.meta.copy() if scan.meta else {}

    try:
        from app.services.tasks import run_scan_task

        async_result = run_scan_task.delay(scan.id)
        meta["celery_task_id"] = async_result.id
        meta["execution_mode"] = "celery"
        scan.meta = meta
        db.commit()
        db.refresh(scan)
        return
    except Exception as exc:  # noqa: BLE001
        meta["execution_mode"] = "inline"
        meta["dispatch_error"] = str(exc)
        scan.meta = meta
        db.commit()
        db.refresh(scan)

    execute_scan(scan.id)


def _create_scan(
    db: Session,
    project_id: str,
    target: str,
    tools: list[str],
    name: str | None = None,
    chain: str | None = None,
    meta: dict | None = None,
) -> models.Scan:
    scan = models.Scan(
        project_id=project_id,
        target=target,
        tools=tools,
        name=name,
        chain=chain,
        meta=meta,
        status=models.ScanStatus.PENDING,
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)

    _dispatch_scan(db, scan)
    return scan


@router.post("", response_model=schemas.ScanRead)
def start_scan(
    payload: schemas.ScanRequest,
    db: Session = Depends(get_db),
) -> schemas.ScanRead:
    """
    General scan endpoint.

    - If payload.project_id is provided, attach scan to that project.
    - Otherwise, find or create project by name + path & meta.
    """
    project: models.Project | None = None

    if payload.project_id:
        project = (
            db.query(models.Project)
            .filter(models.Project.id == payload.project_id)
            .first()
        )
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
    else:
        project = (
            db.query(models.Project)
            .filter(models.Project.name == payload.project_name)
            .first()
        )

        meta = payload.meta.copy() if payload.meta else {}
        if payload.chain:
            meta.setdefault("chain", payload.chain)
        if payload.scan_name:
            meta.setdefault("scan_name", payload.scan_name)

        if not project:
            project = models.Project(
                name=payload.project_name,
                path=payload.project_path,
                meta=meta or None,
            )
            db.add(project)
            db.commit()
            db.refresh(project)
        else:
            updated = False
            if payload.project_path and project.path != payload.project_path:
                project.path = payload.project_path
                updated = True
            if meta:
                existing_meta = project.meta or {}
                merged_meta = {**existing_meta, **meta}
                if merged_meta != existing_meta:
                    project.meta = merged_meta
                    updated = True
            if updated:
                db.commit()
                db.refresh(project)

    scan = _create_scan(
        db=db,
        project_id=project.id,
        target=payload.target,
        tools=payload.tools,
        name=payload.scan_name,
        chain=payload.chain,
        meta=payload.meta,
    )
    return scan


@router.post("/quick", response_model=schemas.QuickScanResponse)
def quick_scan(
    payload: schemas.QuickScanRequest,
    db: Session = Depends(get_db),
) -> schemas.QuickScanResponse:
    """
    Convenience endpoint: ensures a project exists by name, then starts a scan.
    """
    project = (
        db.query(models.Project)
        .filter(models.Project.name == payload.project.name)
        .first()
    )

    if not project:
        project = models.Project(
            name=payload.project.name,
            path=payload.project.path,
            meta=payload.project.meta,
        )
        db.add(project)
        db.commit()
        db.refresh(project)
    else:
        # Keep project path/meta in sync with latest request
        updated = False
        if project.path != payload.project.path:
            project.path = payload.project.path
            updated = True
        if payload.project.meta is not None and payload.project.meta != project.meta:
            project.meta = payload.project.meta
            updated = True
        if updated:
            db.commit()
            db.refresh(project)

    scan = _create_scan(
        db=db,
        project_id=project.id,
        target=payload.target,
        tools=payload.tools,
        name=None,
    )

    return schemas.QuickScanResponse(project_id=project.id, scan_id=scan.id)


@router.get("", response_model=list[schemas.ScanRead])
def list_scans(db: Session = Depends(get_db)) -> list[schemas.ScanRead]:
    return (
        db.query(models.Scan)
        .order_by(models.Scan.created_at.desc())
        .all()
    )


@router.get("/{scan_id}", response_model=schemas.ScanDetail)
def get_scan(
    scan_id: str,
    db: Session = Depends(get_db),
) -> schemas.ScanDetail:
    scan = (
        db.query(models.Scan)
        .options(
            selectinload(models.Scan.findings),
            selectinload(models.Scan.tool_executions),
        )
        .filter(models.Scan.id == scan_id)
        .first()
    )
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    return scan
