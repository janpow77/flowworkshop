"""
flowworkshop · routers/demo_data.py
Demo-Daten Seeding und Reset fuer Workshop-Betrieb.
"""
import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.project import WorkshopProject, Foerderphase
from models.checklist import WorkshopChecklist, WorkshopQuestion, AnswerType

router = APIRouter(prefix="/api/demo", tags=["demo"])
log = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / "data" / "demo_templates"


@router.get("/templates")
def list_templates():
    """Verfuegbare Checklisten-Vorlagen auflisten."""
    templates = []
    for f in TEMPLATES_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            templates.append({
                "template_id": data.get("template_id", f.stem),
                "name": data.get("name", f.stem),
                "description": data.get("description", ""),
                "question_count": len(data.get("questions", [])),
            })
        except (json.JSONDecodeError, KeyError) as e:
            log.warning("Template %s fehlerhaft: %s", f.name, e)
    return {"templates": templates}


@router.post("/seed")
def seed_demo_data(db: Session = Depends(get_db)):
    """Demo-Projekt mit VKO-Checkliste und Fragen anlegen."""
    # Pruefen ob Demo-Projekt bereits existiert
    existing = (
        db.query(WorkshopProject)
        .filter(WorkshopProject.aktenzeichen == "DEMO-2024-001")
        .first()
    )
    if existing:
        return {
            "status": "exists",
            "project_id": existing.id,
            "message": "Demo-Projekt existiert bereits.",
        }

    # Projekt erstellen
    project = WorkshopProject(
        aktenzeichen="DEMO-2024-001",
        geschaeftsjahr="2024",
        program="EFRE Hessen",
        foerderphase=Foerderphase.FP_2021_2027,
        zuwendungsempfaenger="Musterstadt GmbH",
        projekttitel="Digitalisierung kommunaler Infrastruktur Musterstadt",
        foerderkennzeichen="20-3456-01",
        bewilligungszeitraum="01.01.2023 - 31.12.2025",
        gesamtkosten="1.250.000 EUR",
        foerdersumme="875.000 EUR",
    )
    db.add(project)
    db.flush()

    # VKO-Template laden
    template_path = TEMPLATES_DIR / "vko_efre_2021.json"
    if not template_path.exists():
        raise HTTPException(500, "VKO-Template nicht gefunden.")
    template = json.loads(template_path.read_text(encoding="utf-8"))

    # Checkliste erstellen
    checklist = WorkshopChecklist(
        project_id=project.id,
        name=template["name"],
        description=template["description"],
        template_id=template["template_id"],
    )
    db.add(checklist)
    db.flush()

    # Fragen erstellen
    for qd in template["questions"]:
        answer_type = AnswerType(qd.get("answer_type", "boolean"))
        q = WorkshopQuestion(
            checklist_id=checklist.id,
            question_key=qd["question_key"],
            question_text=qd["question_text"],
            answer_type=answer_type,
            category=qd.get("category"),
            sort_order=qd.get("sort_order", 0),
        )
        db.add(q)

    db.commit()
    log.info(
        "Demo-Daten erstellt: Projekt %s, Checkliste %s, %d Fragen",
        project.id, checklist.id, len(template["questions"]),
    )

    return {
        "status": "created",
        "project_id": project.id,
        "checklist_id": checklist.id,
        "questions_created": len(template["questions"]),
    }


@router.delete("/reset")
def reset_demo_data(db: Session = Depends(get_db)):
    """Alle Workshop-Daten loeschen (Projekte, Checklisten, Fragen, Evidenz)."""
    count = db.query(WorkshopProject).count()
    db.query(WorkshopProject).delete()
    db.commit()
    log.info("Demo-Reset: %d Projekte geloescht.", count)
    return {"status": "reset", "projects_deleted": count}
