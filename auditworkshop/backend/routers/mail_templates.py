"""
flowworkshop · routers/mail_templates.py

Admin-CRUD für die editierbaren Mail-Vorlagen aus services/email_service.py.

Endpoints:
  GET    /api/admin/mail-templates                  → Liste aller Templates
  GET    /api/admin/mail-templates/{key}            → Detail (Subject + Body)
  PUT    /api/admin/mail-templates/{key}            → Update Subject/Body
  POST   /api/admin/mail-templates/{key}/preview    → Render mit Dummy-Daten
  POST   /api/admin/mail-templates/{key}/reset      → Zurück auf Default
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models.registration import EmailTemplate
from routers.auth import require_admin
from services.email_service import DEFAULT_TEMPLATES, _jinja

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/mail-templates", tags=["mail-templates"])


# ── Schemas ─────────────────────────────────────────────────────────────────

class TemplateListEntry(BaseModel):
    key: str
    subject: str
    description: str | None = None
    placeholders: list[str]
    updated_at: str | None = None
    is_overridden: bool  # True wenn DB-Override existiert


class TemplateDetail(BaseModel):
    key: str
    subject: str
    body: str
    description: str | None = None
    placeholders: list[str]
    updated_at: str | None = None
    is_overridden: bool
    default_subject: str
    default_body: str


class TemplateUpdate(BaseModel):
    subject: str
    body: str


class TemplatePreviewRequest(BaseModel):
    subject: str | None = None
    body: str | None = None
    sample_data: dict | None = None  # optionale Overrides für Demo-Werte


class TemplatePreviewResponse(BaseModel):
    subject: str
    body: str
    used_sample_data: dict


# ── Demo-Daten für Vorschau (pro Template) ──────────────────────────────────

_SAMPLE_DATA: dict[str, dict] = {
    "invite": {
        "first_name": "Erika",
        "last_name": "Musterfrau",
        "setup_url": "https://workshop.flowaudit.de/account/setup-password?token=DEMO-VORSCHAU-TOKEN",
        "public_url": "https://workshop.flowaudit.de",
    },
    "confirmation": {
        "first_name": "Erika",
        "last_name": "Musterfrau",
        "email": "erika.musterfrau@behoerde.de",
        "organization": "Beispiel-Prüfbehörde",
        "department": "Referat 1",
        "fund": "EFRE",
        "ai_paragraph": "",
        "workshop_title": "Prüferworkshop 2026",
        "public_url": "https://workshop.flowaudit.de",
        "reply_to": "administration@vwvg.de",
        "organizer": "Prüferworkshop",
    },
    "admin_notify": {
        "registration_id": "demo-uuid-1234-5678",
        "first_name": "Erika",
        "last_name": "Musterfrau",
        "email": "erika.musterfrau@behoerde.de",
        "organization": "Beispiel-Prüfbehörde",
        "department": "Referat 1",
        "fund": "EFRE",
        "confirmation_sent": True,
        "ai_consent": False,
        "public_url": "https://workshop.flowaudit.de",
    },
    "signup_alert": {
        "user_id": "demo-uuid-1234-5678",
        "first_name": "Erika",
        "last_name": "Musterfrau",
        "email": "erika.musterfrau@behoerde.de",
        "organization": "Beispiel-Prüfbehörde",
        "bundesland": "Hessen",
        "function_role": "Prüferin",
        "signup_reason": "Interesse an der Recherche-Funktionalität und am Sanktionslisten-Abgleich.",
        "public_url": "https://workshop.flowaudit.de",
    },
    "signup_received": {
        "first_name": "Erika",
        "last_name": "Musterfrau",
        "email": "erika.musterfrau@behoerde.de",
        "organization": "Beispiel-Prüfbehörde",
        "workshop_title": "Prüferworkshop 2026",
        "public_url": "https://workshop.flowaudit.de",
        "reply_to": "administration@vwvg.de",
        "organizer": "Prüferworkshop",
    },
    "account_approved": {
        "first_name": "Erika",
        "last_name": "Musterfrau",
        "email": "erika.musterfrau@behoerde.de",
        "login_url": "https://workshop.flowaudit.de/login",
        "workshop_title": "Prüferworkshop 2026",
        "public_url": "https://workshop.flowaudit.de",
        "reply_to": "administration@vwvg.de",
        "organizer": "Prüferworkshop",
    },
}


def _default_for(key: str) -> dict:
    d = DEFAULT_TEMPLATES.get(key)
    if not d:
        raise HTTPException(404, f"Unbekanntes Template: {key}")
    return d


def _entry_from(key: str, row: EmailTemplate | None) -> TemplateListEntry:
    default = _default_for(key)
    if row:
        return TemplateListEntry(
            key=key,
            subject=row.subject,
            description=str(default.get("description") or ""),
            placeholders=list(default.get("placeholders") or []),
            updated_at=row.updated_at.isoformat() if row.updated_at else None,
            is_overridden=True,
        )
    return TemplateListEntry(
        key=key,
        subject=str(default["subject"]),
        description=str(default.get("description") or ""),
        placeholders=list(default.get("placeholders") or []),
        updated_at=None,
        is_overridden=False,
    )


# ── Endpoints ───────────────────────────────────────────────────────────────

@router.get("", response_model=list[TemplateListEntry])
def list_templates(request: Request, db: Session = Depends(get_db)):
    """Liste aller Templates (Default + DB-Override-Status)."""
    require_admin(request)
    rows = {r.key: r for r in db.query(EmailTemplate).all()}
    return [_entry_from(key, rows.get(key)) for key in DEFAULT_TEMPLATES.keys()]


@router.get("/{key}", response_model=TemplateDetail)
def get_template(key: str, request: Request, db: Session = Depends(get_db)):
    """Detail eines Templates inkl. Default-Werte zum Vergleich."""
    require_admin(request)
    default = _default_for(key)
    row = db.query(EmailTemplate).filter(EmailTemplate.key == key).first()
    return TemplateDetail(
        key=key,
        subject=row.subject if row else str(default["subject"]),
        body=row.body if row else str(default["body"]),
        description=str(default.get("description") or ""),
        placeholders=list(default.get("placeholders") or []),
        updated_at=row.updated_at.isoformat() if (row and row.updated_at) else None,
        is_overridden=row is not None,
        default_subject=str(default["subject"]),
        default_body=str(default["body"]),
    )


@router.put("/{key}", response_model=TemplateDetail)
def update_template(
    key: str,
    body: TemplateUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    """Subject + Body überschreiben (oder neuen Eintrag anlegen)."""
    actor = require_admin(request)
    default = _default_for(key)
    if not body.subject.strip() or not body.body.strip():
        raise HTTPException(422, "Betreff und Body dürfen nicht leer sein.")

    # Jinja-Syntax validieren — kein Versand mit broken Template
    try:
        _jinja.from_string(body.subject)
        _jinja.from_string(body.body)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(422, f"Template-Syntax ungültig: {e}") from e

    row = db.query(EmailTemplate).filter(EmailTemplate.key == key).first()
    if row:
        row.subject = body.subject
        row.body = body.body
        row.updated_by_id = actor.get("user_id")
    else:
        row = EmailTemplate(
            key=key,
            subject=body.subject,
            body=body.body,
            description=str(default.get("description") or "")[:255] or None,
            updated_by_id=actor.get("user_id"),
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    log.info("mail-template %r aktualisiert von %s", key, actor.get("email"))
    return TemplateDetail(
        key=key,
        subject=row.subject,
        body=row.body,
        description=str(default.get("description") or ""),
        placeholders=list(default.get("placeholders") or []),
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
        is_overridden=True,
        default_subject=str(default["subject"]),
        default_body=str(default["body"]),
    )


@router.post("/{key}/preview", response_model=TemplatePreviewResponse)
def preview_template(
    key: str,
    payload: TemplatePreviewRequest,
    request: Request,
):
    """Rendert Subject/Body mit Demo-Daten — wahlweise mit Live-Editor-Werten
    aus dem Frontend (subject/body in `payload`), sonst aus der DB/dem Default.
    """
    require_admin(request)
    default = _default_for(key)
    sample = dict(_SAMPLE_DATA.get(key) or {})
    if payload.sample_data:
        sample.update(payload.sample_data)

    subject_tmpl = payload.subject if payload.subject is not None else str(default["subject"])
    body_tmpl = payload.body if payload.body is not None else str(default["body"])

    try:
        subject = _jinja.from_string(subject_tmpl).render(**sample).strip()
        body = _jinja.from_string(body_tmpl).render(**sample)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(422, f"Render-Fehler: {e}") from e

    return TemplatePreviewResponse(
        subject=subject,
        body=body,
        used_sample_data=sample,
    )


@router.post("/{key}/reset", response_model=TemplateDetail)
def reset_template(key: str, request: Request, db: Session = Depends(get_db)):
    """Löscht den DB-Override — der hartcodierte Default wirkt wieder."""
    actor = require_admin(request)
    default = _default_for(key)
    row = db.query(EmailTemplate).filter(EmailTemplate.key == key).first()
    if row:
        db.delete(row)
        db.commit()
        log.info("mail-template %r auf Default zurückgesetzt von %s", key, actor.get("email"))
    return TemplateDetail(
        key=key,
        subject=str(default["subject"]),
        body=str(default["body"]),
        description=str(default.get("description") or ""),
        placeholders=list(default.get("placeholders") or []),
        updated_at=None,
        is_overridden=False,
        default_subject=str(default["subject"]),
        default_body=str(default["body"]),
    )


# ── Seed-Helper (von main.py beim Lifespan aufgerufen) ──────────────────────

def seed_default_templates(db: Session) -> None:
    """Beim Start-up: legt keine Overrides an, sondern stellt nur sicher, dass
    die Tabelle existiert und ggf. log-fähig ist. Der eigentliche Default-Text
    lebt in services/email_service.DEFAULT_TEMPLATES — nur wenn der Admin
    aktiv editiert, entsteht eine DB-Zeile.
    """
    # Bewusst keine INSERT-Operation: ungeänderte Templates bleiben in
    # Python, geänderte überschreiben dort per Lookup. Spart Migrations-
    # Aufwand wenn sich Defaults ändern.
    _ = db
    return None
