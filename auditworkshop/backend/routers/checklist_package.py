"""
flowworkshop · routers/checklist_package.py

Vollstaendiges Checklisten-Paket: Export/Import als eine portable .checklist.json.
Gespiegelt zum audit_designer-Paket; der Import akzeptiert auch audit_designer-
Pakete (Cross-Repo) ueber den Adapter im checklist_package_service.

Endpunkte (Prefix /api/checklist-templates):
  - GET  /{template_id}/package?discussions=&history=&versions=  → Paket-JSON
  - POST /package/validate   (multipart file)  → Vorschau + "existiert schon?"
  - POST /package            (multipart file, title?, target_template_id?) → Import

Bewusst eigenstaendig (lokale Rechtepruefung _require_member, analog
routers/checklist_export.py) zur Konfliktvermeidung mit checklist_templates.py.
"""

import json
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from database import get_db
from models.checklist_template import (
    ChecklistMember,
    ChecklistTemplate,
    TemplateStatus,
)
from routers.auth import require_session
from services.checklist_package_service import (
    ChecklistPackageError,
    ChecklistPackageService,
)

router = APIRouter(
    prefix="/api/checklist-templates",
    tags=["checklist-templates"],
    dependencies=[Depends(require_session)],
)
log = logging.getLogger(__name__)


def _session_user_id(session: dict) -> str:
    uid = session.get("user_id")
    if not uid:
        raise HTTPException(401, "Sitzung ohne Nutzerkennung.")
    return uid


def _require_member(
    template_id: str, request: Request, db: Session
) -> ChecklistTemplate:
    """Lese-Rechtepruefung: Mitglied ODER veroeffentlicht (analog Export)."""
    session = require_session(request)
    user_id = _session_user_id(session)
    tpl = (
        db.query(ChecklistTemplate).filter(ChecklistTemplate.id == template_id).first()
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


async def _read_json_upload(file: UploadFile) -> tuple[object, str]:
    if not file.filename or not file.filename.lower().endswith(".json"):
        raise HTTPException(400, "Nur JSON-Dateien erlaubt.")
    content = await file.read()
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(400, f"Ungueltiges JSON: {exc}")
    base = file.filename
    for suf in (".checklist.json", ".json"):
        if base.lower().endswith(suf):
            base = base[: -len(suf)]
            break
    return payload, base


@router.get("/{template_id}/package")
def export_package(
    template_id: str,
    request: Request,
    discussions: bool = True,
    history: bool = False,
    versions: bool = False,
    db: Session = Depends(get_db),
):
    """Vollstaendiges Checklisten-Paket einer Vorlage als JSON."""
    tpl = _require_member(template_id, request, db)
    return ChecklistPackageService.build_package(
        db,
        tpl,
        include_discussions=discussions,
        include_history=history,
        include_versions=versions,
    )


@router.post("/package/validate")
async def validate_package(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Paket pruefen (Struktur + ob die Checkliste schon existiert) — Vorschau."""
    require_session(request)
    payload, base = await _read_json_upload(file)
    return ChecklistPackageService.validate_package(db, payload, fallback_title=base)


@router.post("/package")
async def import_package(
    request: Request,
    file: UploadFile = File(...),
    title: str | None = Form(None),
    target_template_id: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """Paket importieren — neue Checkliste oder als Versions-Snapshot."""
    session = require_session(request)
    uid = _session_user_id(session)
    payload, base = await _read_json_upload(file)
    try:
        return ChecklistPackageService.import_package(
            db,
            payload,
            current_user_id=uid,
            target_template_id=target_template_id,
            title_override=title,
            fallback_title=base,
        )
    except ChecklistPackageError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))
