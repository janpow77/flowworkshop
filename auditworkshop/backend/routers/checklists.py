"""
flowworkshop · routers/checklists.py
CRUD-Endpunkte fuer Checklisten und Fragen.
"""
import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.project import WorkshopProject
from models.checklist import (
    WorkshopChecklist, WorkshopQuestion, WorkshopEvidence,
    RemarkAiStatus,
)
from schemas.checklist import (
    ChecklistCreate, ChecklistUpdate, ChecklistOut, ChecklistDetailOut,
    QuestionCreate, QuestionUpdate, QuestionOut, QuestionDetailOut,
    EvidenceOut,
)

router = APIRouter(prefix="/api/projects/{project_id}/checklists", tags=["checklists"])
TEMPLATES_DIR = Path(__file__).parent.parent / "data" / "demo_templates"


def _get_project(project_id: str, db: Session) -> WorkshopProject:
    project = db.query(WorkshopProject).filter(WorkshopProject.id == project_id).first()
    if not project:
        raise HTTPException(404, "Projekt nicht gefunden.")
    return project


def _checklist_out(cl: WorkshopChecklist) -> ChecklistOut:
    ai_count = sum(1 for q in cl.questions if q.remark_ai_status is not None)
    return ChecklistOut(
        id=cl.id,
        project_id=cl.project_id,
        name=cl.name,
        description=cl.description,
        template_id=cl.template_id,
        question_count=len(cl.questions),
        ai_assessed_count=ai_count,
        created_at=cl.created_at,
        updated_at=cl.updated_at,
    )


def _question_out(q: WorkshopQuestion) -> QuestionOut:
    out = QuestionOut.model_validate(q)
    out.evidence_count = len(q.evidence)
    return out


def _load_template(template_id: str) -> dict:
    for template_path in TEMPLATES_DIR.glob("*.json"):
        data = json.loads(template_path.read_text(encoding="utf-8"))
        if data.get("template_id") == template_id or template_path.stem == template_id:
            return data
    raise HTTPException(404, f"Vorlage '{template_id}' nicht gefunden.")


def _create_question(checklist_id: str, qd: QuestionCreate, fallback_sort_order: int) -> WorkshopQuestion:
    return WorkshopQuestion(
        id=str(uuid.uuid4()),
        checklist_id=checklist_id,
        question_key=qd.question_key,
        question_text=qd.question_text,
        answer_type=qd.answer_type,
        category=qd.category,
        sort_order=qd.sort_order if qd.sort_order else fallback_sort_order,
        answer_value=qd.answer_value,
        remark_manual=qd.remark_manual,
    )


# ── Checklisten CRUD ──────────────────────────────────────────────────────────

@router.post("/", response_model=ChecklistDetailOut, status_code=201)
def create_checklist(project_id: str, data: ChecklistCreate, db: Session = Depends(get_db)):
    _get_project(project_id, db)
    template = _load_template(data.template_id) if data.template_id else None
    description = data.description if data.description is not None else (template.get("description") if template else None)

    cl = WorkshopChecklist(
        project_id=project_id,
        name=data.name,
        description=description,
        template_id=data.template_id,
    )
    db.add(cl)
    db.flush()

    questions = list(data.questions or [])
    if not questions and template:
        questions = [QuestionCreate.model_validate(item) for item in template.get("questions", [])]

    for i, qd in enumerate(questions):
        db.add(_create_question(cl.id, qd, i))

    db.commit()
    db.refresh(cl)
    return ChecklistDetailOut(
        **_checklist_out(cl).model_dump(),
        questions=[_question_out(q) for q in cl.questions],
    )


@router.get("/", response_model=list[ChecklistOut])
def list_checklists(project_id: str, db: Session = Depends(get_db)):
    _get_project(project_id, db)
    checklists = (
        db.query(WorkshopChecklist)
        .filter(WorkshopChecklist.project_id == project_id)
        .order_by(WorkshopChecklist.created_at)
        .all()
    )
    return [_checklist_out(cl) for cl in checklists]


@router.get("/{checklist_id}", response_model=ChecklistDetailOut)
def get_checklist(project_id: str, checklist_id: str, db: Session = Depends(get_db)):
    cl = (
        db.query(WorkshopChecklist)
        .filter(WorkshopChecklist.id == checklist_id, WorkshopChecklist.project_id == project_id)
        .first()
    )
    if not cl:
        raise HTTPException(404, "Checkliste nicht gefunden.")
    return ChecklistDetailOut(
        **_checklist_out(cl).model_dump(),
        questions=[_question_out(q) for q in cl.questions],
    )


@router.put("/{checklist_id}", response_model=ChecklistOut)
def update_checklist(
    project_id: str, checklist_id: str, data: ChecklistUpdate, db: Session = Depends(get_db),
):
    cl = (
        db.query(WorkshopChecklist)
        .filter(WorkshopChecklist.id == checklist_id, WorkshopChecklist.project_id == project_id)
        .first()
    )
    if not cl:
        raise HTTPException(404, "Checkliste nicht gefunden.")
    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(cl, key, val)
    db.commit()
    db.refresh(cl)
    return _checklist_out(cl)


@router.delete("/{checklist_id}", status_code=204)
def delete_checklist(project_id: str, checklist_id: str, db: Session = Depends(get_db)):
    cl = (
        db.query(WorkshopChecklist)
        .filter(WorkshopChecklist.id == checklist_id, WorkshopChecklist.project_id == project_id)
        .first()
    )
    if not cl:
        raise HTTPException(404, "Checkliste nicht gefunden.")
    db.delete(cl)
    db.commit()


# ── Fragen CRUD ───────────────────────────────────────────────────────────────

@router.post("/{checklist_id}/questions", response_model=QuestionOut, status_code=201)
def add_question(
    project_id: str, checklist_id: str, data: QuestionCreate, db: Session = Depends(get_db),
):
    cl = (
        db.query(WorkshopChecklist)
        .filter(WorkshopChecklist.id == checklist_id, WorkshopChecklist.project_id == project_id)
        .first()
    )
    if not cl:
        raise HTTPException(404, "Checkliste nicht gefunden.")
    q = WorkshopQuestion(checklist_id=checklist_id, **data.model_dump())
    db.add(q)
    db.commit()
    db.refresh(q)
    return _question_out(q)


@router.post("/{checklist_id}/questions/bulk", response_model=list[QuestionOut], status_code=201)
def add_questions_bulk(
    project_id: str, checklist_id: str, data: list[QuestionCreate], db: Session = Depends(get_db),
):
    cl = (
        db.query(WorkshopChecklist)
        .filter(WorkshopChecklist.id == checklist_id, WorkshopChecklist.project_id == project_id)
        .first()
    )
    if not cl:
        raise HTTPException(404, "Checkliste nicht gefunden.")
    questions = []
    for i, qd in enumerate(data):
        q = _create_question(checklist_id, qd, i)
        db.add(q)
        questions.append(q)
    db.commit()
    for q in questions:
        db.refresh(q)
    return [_question_out(q) for q in questions]


@router.get("/{checklist_id}/questions", response_model=list[QuestionOut])
def list_questions(project_id: str, checklist_id: str, db: Session = Depends(get_db)):
    questions = (
        db.query(WorkshopQuestion)
        .filter(WorkshopQuestion.checklist_id == checklist_id)
        .order_by(WorkshopQuestion.sort_order)
        .all()
    )
    return [_question_out(q) for q in questions]


@router.get("/{checklist_id}/questions/{question_id}", response_model=QuestionDetailOut)
def get_question(
    project_id: str, checklist_id: str, question_id: str, db: Session = Depends(get_db),
):
    q = (
        db.query(WorkshopQuestion)
        .filter(WorkshopQuestion.id == question_id, WorkshopQuestion.checklist_id == checklist_id)
        .first()
    )
    if not q:
        raise HTTPException(404, "Frage nicht gefunden.")
    out = QuestionDetailOut.model_validate(q)
    out.evidence_count = len(q.evidence)
    out.evidence = [EvidenceOut.model_validate(e) for e in q.evidence]
    return out


@router.put("/{checklist_id}/questions/{question_id}", response_model=QuestionOut)
def update_question(
    project_id: str, checklist_id: str, question_id: str,
    data: QuestionUpdate, db: Session = Depends(get_db),
):
    q = (
        db.query(WorkshopQuestion)
        .filter(WorkshopQuestion.id == question_id, WorkshopQuestion.checklist_id == checklist_id)
        .first()
    )
    if not q:
        raise HTTPException(404, "Frage nicht gefunden.")
    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(q, key, val)
    db.commit()
    db.refresh(q)
    return _question_out(q)


@router.delete("/{checklist_id}/questions/{question_id}", status_code=204)
def delete_question(
    project_id: str, checklist_id: str, question_id: str, db: Session = Depends(get_db),
):
    q = (
        db.query(WorkshopQuestion)
        .filter(WorkshopQuestion.id == question_id, WorkshopQuestion.checklist_id == checklist_id)
        .first()
    )
    if not q:
        raise HTTPException(404, "Frage nicht gefunden.")
    db.delete(q)
    db.commit()


# ── Export ────────────────────────────────────────────────────────────────────


@router.get("/{checklist_id}/export/csv")
def export_csv(project_id: str, checklist_id: str, db: Session = Depends(get_db)):
    """Exportiert Checkliste als CSV (Semikolon-getrennt, UTF-8 mit BOM)."""
    import csv
    import io
    from fastapi.responses import StreamingResponse

    cl = (
        db.query(WorkshopChecklist)
        .filter(
            WorkshopChecklist.id == checklist_id,
            WorkshopChecklist.project_id == project_id,
        )
        .first()
    )
    if not cl:
        raise HTTPException(404, "Checkliste nicht gefunden.")

    output = io.StringIO()
    # BOM fuer Excel-Kompatibilitaet
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";")
    writer.writerow(
        [
            "Nr.",
            "Kategorie",
            "Pruefpunkt",
            "Antwort",
            "KI-Status",
            "KI-Bemerkung",
            "Manuelle Bemerkung",
        ]
    )

    for q in sorted(cl.questions, key=lambda x: x.sort_order or 0):
        writer.writerow(
            [
                q.question_key or "",
                q.category or "",
                q.question_text or "",
                q.answer_value or "",
                q.remark_ai_status.value if q.remark_ai_status else "",
                q.remark_ai or "",
                q.remark_manual or "",
            ]
        )

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=checkliste_{checklist_id}.csv"
        },
    )
