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
import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from database import get_db
from models.checklist_template import (
    ChecklistTemplate,
    ChecklistTemplateNode,
    ChecklistAnswerSet,
    ChecklistMember,
    ChecklistNodeComment,
    TemplateStatus,
)
from models.registration import Registration
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


def _load_comment_names(comments: list[ChecklistNodeComment], db: Session) -> dict[str, str | None]:
    """Map Autor-Kennung → Anzeigename fuer die gegebenen Kommentare.

    Schlanke Duplikation der Namens-Aufloesung aus checklist_discussion.py
    (bewusst kein Import, um die Kopplung gering zu halten): Registration-Join
    ueber author_id; fehlende/geloeschte Nutzer fehlen schlicht in der Map."""
    ids = {c.author_id for c in comments if c.author_id}
    if not ids:
        return {}
    rows = db.query(Registration).filter(Registration.id.in_(ids)).all()
    out: dict[str, str | None] = {}
    for r in rows:
        name = f"{r.first_name or ''} {r.last_name or ''}".strip()
        out[r.id] = name or None
    return out


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


@router.get("/{template_id}/export-discussion")
def export_discussion(
    template_id: str, request: Request, format: str = "docx",
    db: Session = Depends(get_db),
):
    """Exportiert das Diskussionsprotokoll der Checkliste als DOCX (Default) oder PDF.

    Enthaelt nur Knoten mit Kommentaren in Baum-Reihenfolge, je mit Status,
    Rechtsgrundlage und den threaded Kommentaren. Existieren keine Kommentare,
    wird trotzdem eine gueltige Datei mit Hinweis erzeugt (kein 404)."""
    tpl = _require_member(template_id, request, db)

    fmt = (format or "docx").strip().lower()
    if fmt not in ("docx", "pdf"):
        fmt = "docx"

    nodes = (
        db.query(ChecklistTemplateNode)
        .filter(ChecklistTemplateNode.template_id == template_id)
        .all()
    )
    comments = (
        db.query(ChecklistNodeComment)
        .filter(
            ChecklistNodeComment.template_id == template_id,
            ChecklistNodeComment.deleted_at.is_(None),
        )
        .order_by(ChecklistNodeComment.created_at.asc())
        .all()
    )
    names = _load_comment_names(comments, db)

    base = (tpl.title or "Checkliste").strip()
    safe = "".join(c if (c.isalnum() or c in " ._-") else "_" for c in base)
    safe = "_".join(safe.split()) or "Checkliste"

    if fmt == "pdf":
        data = export_svc.export_discussion_pdf(tpl, nodes, comments, names)
        media = PDF_MEDIA
        filename = f"Diskussionsprotokoll_{safe[:80]}.pdf"
    else:
        data = export_svc.export_discussion_docx(tpl, nodes, comments, names)
        media = DOCX_MEDIA
        filename = f"Diskussionsprotokoll_{safe[:80]}.docx"

    log.info(
        "Diskussions-Export %s: %s (%d Knoten, %d Kommentare)",
        fmt.upper(), template_id, len(nodes), len(comments),
    )
    return Response(content=data, media_type=media, headers=_content_disposition(filename))


# Daten-Basisverzeichnis (gemountetes Volume); Quelldokumente liegen darunter.
DATA_DIR = "/app/data"


@router.get("/{template_id}/source-document")
def download_source_document(
    template_id: str, request: Request, db: Session = Depends(get_db),
):
    """Liefert das hinterlegte Quelldokument (z. B. das englische KOM-Original)
    zum Download. Pfad-Traversal wird verhindert — die Datei muss unterhalb von
    DATA_DIR liegen."""
    tpl = _require_member(template_id, request, db)
    rel = (tpl.source_document_path or "").strip()
    if not rel:
        raise HTTPException(status_code=404, detail="Kein Quelldokument hinterlegt.")
    abs_path = os.path.normpath(os.path.join(DATA_DIR, rel))
    if not abs_path.startswith(DATA_DIR + os.sep) or not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="Quelldokument nicht gefunden.")
    with open(abs_path, "rb") as fh:
        data = fh.read()
    filename = tpl.source_document_name or os.path.basename(abs_path)
    ext = os.path.splitext(abs_path)[1].lower()
    media = {".docx": DOCX_MEDIA, ".xlsx": XLSX_MEDIA, ".pdf": PDF_MEDIA}.get(
        ext, "application/octet-stream"
    )
    log.info("Quelldokument-Download: %s (%s)", template_id, filename)
    return Response(content=data, media_type=media, headers=_content_disposition(filename))
