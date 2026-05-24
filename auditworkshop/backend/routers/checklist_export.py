"""
flowworkshop · routers/checklist_export.py

Export-Endpunkte fuer das KOM-Checklisten-Template-Subsystem (Designer).
Erzeugt eine ausfuellbare Pruefcheckliste in DOCX, XLSX und PDF — gespiegelt zum
audit_designer-Checklistendesigner.

Endpunkte (Prefix /api/checklist-templates):
  - GET /{template_id}/export-word   → DOCX
  - GET /{template_id}/export-excel  → XLSX
  - GET /{template_id}/export-pdf    → PDF

Jeweils mit Query-Parameter ``mode=blank|filled`` (Default ``blank``).

Bewusst eigenstaendig von routers/checklist_templates.py (Konfliktvermeidung):
eine lokale, schlanke Rechtepruefung (_require_member) prueft Mitgliedschaft
ODER veroeffentlichten Status, ohne die Helfer der CRUD-Datei zu importieren.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from database import get_db
from models.checklist_template import (
    ChecklistTemplate,
    ChecklistTemplateNode,
    ChecklistAnswerSet,
    ChecklistMember,
    TemplateStatus,
)
from routers.auth import require_session
from services import checklist_export_service as export_svc

router = APIRouter(
    prefix="/api/checklist-templates",
    tags=["checklist-templates"],
    dependencies=[Depends(require_session)],
)
log = logging.getLogger(__name__)


# Media-Types der Office-Formate.
DOCX_MEDIA = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF_MEDIA = "application/pdf"


def _session_user_id(session: dict) -> str:
    """Liest die Nutzerkennung aus der Session (401 bei Fehlen)."""
    uid = session.get("user_id")
    if not uid:
        raise HTTPException(401, "Sitzung ohne Nutzerkennung.")
    return uid


def _require_member(template_id: str, request: Request, db: Session) -> ChecklistTemplate:
    """Lese-Rechtepruefung fuer den Export.

    Erlaubt den Zugriff, wenn der Nutzer Mitglied des Templates ist ODER das
    Template veroeffentlicht (published) ist. Wirft 404, wenn das Template nicht
    existiert, sonst 403 ohne Berechtigung. Gibt das Template zurueck.

    Lokaler Helfer (kein Import aus checklist_templates.py) — fragt
    ChecklistMember direkt ab."""
    session = require_session(request)
    user_id = _session_user_id(session)

    tpl = (
        db.query(ChecklistTemplate)
        .filter(ChecklistTemplate.id == template_id)
        .first()
    )
    if not tpl:
        raise HTTPException(404, "Checklisten-Template nicht gefunden.")

    if tpl.status == TemplateStatus.PUBLISHED.value:
        return tpl

    member = (
        db.query(ChecklistMember)
        .filter(
            ChecklistMember.template_id == template_id,
            ChecklistMember.user_id == user_id,
        )
        .first()
    )
    if not member:
        raise HTTPException(403, "Kein Zugriff auf dieses Checklisten-Template.")
    return tpl


def _load_export_data(
    template_id: str, db: Session,
) -> tuple[list[ChecklistTemplateNode], list[ChecklistAnswerSet]]:
    """Laedt Knoten + Antwortsets eines Templates fuer den Export.

    Antwortsets umfassen die templategebundenen UND die zugewiesenen globalen
    Sets (template_id IS NULL), damit Knoten mit globalem Antwortset korrekt
    aufgeloest werden koennen."""
    nodes = (
        db.query(ChecklistTemplateNode)
        .filter(ChecklistTemplateNode.template_id == template_id)
        .all()
    )

    # IDs aller von Knoten referenzierten Antwortsets (auch globale).
    referenced_ids = {n.answer_set_id for n in nodes if n.answer_set_id}
    if referenced_ids:
        condition = (
            (ChecklistAnswerSet.template_id == template_id)
            | (ChecklistAnswerSet.id.in_(referenced_ids))
        )
    else:
        condition = ChecklistAnswerSet.template_id == template_id
    answer_sets = db.query(ChecklistAnswerSet).filter(condition).all()
    return nodes, answer_sets


def _normalize_mode(mode: str) -> str:
    """Validiert den Modus; faellt bei unbekanntem Wert auf ``blank`` zurueck."""
    m = (mode or "blank").strip().lower()
    return m if m in ("blank", "filled") else "blank"


def _safe_filename(title: str | None, ext: str) -> str:
    """Erzeugt einen sicheren Download-Dateinamen Pruefcheckliste_{title}.{ext}."""
    base = (title or "Checkliste").strip()
    safe = "".join(c if (c.isalnum() or c in " ._-") else "_" for c in base)
    safe = "_".join(safe.split()) or "Checkliste"
    return f"Pruefcheckliste_{safe[:80]}.{ext}"


def _content_disposition(filename: str) -> dict[str, str]:
    """Standard-Header fuer einen Datei-Download."""
    return {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-Content-Type-Options": "nosniff",
    }


@router.get("/{template_id}/export-word")
def export_word(
    template_id: str, request: Request, mode: str = "blank",
    db: Session = Depends(get_db),
):
    """Exportiert die Checkliste als ausfuellbares DOCX (echte Word-Formularfelder).

    ``mode=blank`` (Default) erzeugt leere, ankreuzbare Felder; ``mode=filled``
    befuellt vorhandene Antwort-/Bemerkungsdaten (bei Templates i.d.R. leer)."""
    tpl = _require_member(template_id, request, db)
    mode = _normalize_mode(mode)
    nodes, answer_sets = _load_export_data(template_id, db)

    data = export_svc.export_docx(tpl, nodes, answer_sets, mode=mode)
    filename = _safe_filename(tpl.title, "docx")
    log.info("Checklisten-Export DOCX: %s (mode=%s, %d Knoten)", template_id, mode, len(nodes))
    return Response(content=data, media_type=DOCX_MEDIA, headers=_content_disposition(filename))


@router.get("/{template_id}/export-excel")
def export_excel(
    template_id: str, request: Request, mode: str = "blank",
    db: Session = Depends(get_db),
):
    """Exportiert die Checkliste als XLSX (flache, gut lesbare Tabelle)."""
    tpl = _require_member(template_id, request, db)
    mode = _normalize_mode(mode)
    nodes, answer_sets = _load_export_data(template_id, db)

    data = export_svc.export_xlsx(tpl, nodes, answer_sets, mode=mode)
    filename = _safe_filename(tpl.title, "xlsx")
    log.info("Checklisten-Export XLSX: %s (mode=%s, %d Knoten)", template_id, mode, len(nodes))
    return Response(content=data, media_type=XLSX_MEDIA, headers=_content_disposition(filename))


@router.get("/{template_id}/export-pdf")
def export_pdf(
    template_id: str, request: Request, mode: str = "blank",
    db: Session = Depends(get_db),
):
    """Exportiert die Checkliste als PDF (strukturierte Tabelle, reportlab)."""
    tpl = _require_member(template_id, request, db)
    mode = _normalize_mode(mode)
    nodes, answer_sets = _load_export_data(template_id, db)

    data = export_svc.export_pdf(tpl, nodes, answer_sets, mode=mode)
    filename = _safe_filename(tpl.title, "pdf")
    log.info("Checklisten-Export PDF: %s (mode=%s, %d Knoten)", template_id, mode, len(nodes))
    return Response(content=data, media_type=PDF_MEDIA, headers=_content_disposition(filename))
