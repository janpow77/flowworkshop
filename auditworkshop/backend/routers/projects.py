"""
flowworkshop · routers/projects.py
CRUD-Endpunkte fuer Workshop-Projekte.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.project import WorkshopProject
from schemas.project import ProjectCreate, ProjectUpdate, ProjectOut, ProjectListOut

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("/", response_model=ProjectOut, status_code=201)
def create_project(data: ProjectCreate, db: Session = Depends(get_db)):
    project = WorkshopProject(**data.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    out = ProjectOut.model_validate(project)
    out.checklist_count = len(project.checklists)
    return out


@router.get("/", response_model=ProjectListOut)
def list_projects(db: Session = Depends(get_db)):
    projects = db.query(WorkshopProject).order_by(WorkshopProject.created_at.desc()).all()
    items = []
    for p in projects:
        out = ProjectOut.model_validate(p)
        out.checklist_count = len(p.checklists)
        items.append(out)
    return ProjectListOut(projects=items, total=len(items))


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, db: Session = Depends(get_db)):
    project = db.query(WorkshopProject).filter(WorkshopProject.id == project_id).first()
    if not project:
        raise HTTPException(404, "Projekt nicht gefunden.")
    out = ProjectOut.model_validate(project)
    out.checklist_count = len(project.checklists)
    return out


@router.put("/{project_id}", response_model=ProjectOut)
def update_project(project_id: str, data: ProjectUpdate, db: Session = Depends(get_db)):
    project = db.query(WorkshopProject).filter(WorkshopProject.id == project_id).first()
    if not project:
        raise HTTPException(404, "Projekt nicht gefunden.")
    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(project, key, val)
    db.commit()
    db.refresh(project)
    out = ProjectOut.model_validate(project)
    out.checklist_count = len(project.checklists)
    return out


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, db: Session = Depends(get_db)):
    project = db.query(WorkshopProject).filter(WorkshopProject.id == project_id).first()
    if not project:
        raise HTTPException(404, "Projekt nicht gefunden.")
    db.delete(project)
    db.commit()
