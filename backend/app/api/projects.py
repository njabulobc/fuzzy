# backend/app/api/projects.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.db.session import get_db
from app.services.statsig_client import log_backend_event

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=schemas.ProjectRead)
def create_project(
    payload: schemas.ProjectCreate,
    db: Session = Depends(get_db),
) -> schemas.ProjectRead:
    # Enforce unique name at application level to produce nicer errors
    existing = (
        db.query(models.Project)
        .filter(models.Project.name == payload.name)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Project with name '{payload.name}' already exists.",
        )

    project = models.Project(
        name=payload.name,
        path=payload.path,
        meta=payload.meta,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    log_backend_event(
        "project_created",
        metadata={"project_id": project.id, "name": project.name},
    )
    return project


@router.get("", response_model=list[schemas.ProjectRead])
def list_projects(db: Session = Depends(get_db)) -> list[schemas.ProjectRead]:
    return db.query(models.Project).order_by(models.Project.created_at.desc()).all()


@router.get("/{project_id}", response_model=schemas.ProjectRead)
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
) -> schemas.ProjectRead:
    project = (
        db.query(models.Project)
        .filter(models.Project.id == project_id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.delete("/{project_id}")
def delete_project(
    project_id: str,
    db: Session = Depends(get_db),
) -> dict:
    project = (
        db.query(models.Project)
        .filter(models.Project.id == project_id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    db.delete(project)
    db.commit()
    return {"status": "deleted"}
