"""
flowworkshop · routers/event.py
Anmeldung, Tagesordnung, Themenboard, Einladungslinks, Admin-Verwaltung.
"""
import hashlib
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models.registration import (
    WorkshopMeta, AgendaItem, AgendaItemType, AgendaItemStatus,
    Registration, TopicSubmission, SubmissionVisibility,
)

router = APIRouter(prefix="/api/event", tags=["event"])
log = logging.getLogger(__name__)

DAY_LABELS = {
    1: "Dienstag, 05.05.2026",
    2: "Mittwoch, 06.05.2026",
    3: "Donnerstag, 07.05.2026",
}


# ── Schemas ───────────────────────────────────────────────────────────────────

class MetaOut(BaseModel):
    title: str
    subtitle: str
    date: str
    time: str
    location_short: str
    location_full: str
    organizer: str
    registration_deadline: str
    qr_url: str
    workshop_mode: bool = False
    model_config = {"from_attributes": True}

class MetaUpdate(BaseModel):
    title: str | None = None
    subtitle: str | None = None
    date: str | None = None
    time: str | None = None
    location_short: str | None = None
    location_full: str | None = None
    organizer: str | None = None
    registration_deadline: str | None = None
    qr_url: str | None = None
    workshop_mode: bool | None = None

class AgendaItemOut(BaseModel):
    id: str
    day: int = 1
    time: str
    duration_minutes: int
    item_type: AgendaItemType
    title: str
    speaker: str | None = None
    note: str | None = None
    category: str = "plenary"
    status: AgendaItemStatus = AgendaItemStatus.PENDING
    started_at: datetime | None = None
    visible: bool = True
    scenario_id: int | None = None
    sort_order: int
    model_config = {"from_attributes": True}

class AgendaItemCreate(BaseModel):
    day: int = Field(1, ge=1, le=3)
    time: str = Field(..., max_length=20)
    duration_minutes: int = Field(30, ge=5, le=480)
    item_type: AgendaItemType = AgendaItemType.VORTRAG
    title: str = Field(..., max_length=500)
    speaker: str | None = Field(None, max_length=255)
    note: str | None = None
    category: str = "plenary"
    scenario_id: int | None = None

class AgendaItemUpdate(BaseModel):
    day: int | None = None
    time: str | None = None
    duration_minutes: int | None = None
    item_type: AgendaItemType | None = None
    title: str | None = None
    speaker: str | None = None
    note: str | None = None
    category: str | None = None
    status: AgendaItemStatus | None = None
    visible: bool | None = None
    scenario_id: int | None = None
    sort_order: int | None = None

class RegistrationCreate(BaseModel):
    first_name: str = Field(..., min_length=1)
    last_name: str = Field(..., min_length=1)
    organization: str = Field(..., min_length=1)
    email: str = Field(..., min_length=5)
    department: str | None = None
    fund: str | None = None
    privacy_accepted: bool = True
    anthropic_consent: bool = False

class InviteOut(BaseModel):
    first_name: str
    last_name: str
    organization: str
    email: str
    department: str | None = None
    fund: str | None = None
    already_registered: bool = False
    model_config = {"from_attributes": True}

class TopicCreate(BaseModel):
    topic: str = Field(..., min_length=1)
    question: str | None = None
    notes: str | None = None
    visibility: SubmissionVisibility = SubmissionVisibility.PUBLIC
    anonymous: bool = False

class TopicOut(BaseModel):
    id: str
    topic: str
    question: str | None = None
    organization: str | None = None
    visibility: SubmissionVisibility
    anonymous: bool
    votes: int
    created_at: datetime | None = None
    model_config = {"from_attributes": True}

class AdminAuth(BaseModel):
    pin: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _seed_default_agenda(db: Session) -> None:
    """Erstellt Vorbelegung fuer Tagesordnung (nur wenn leer)."""
    if db.query(AgendaItem).count() > 0:
        return
    defaults = [
        # ── Tag 1 (Dienstag 05.05.) — Plenum ────────────────────────────
        {"day": 1, "time": "12:00", "duration_minutes": 60, "item_type": "organisation", "title": "Begrüßung und Registrierung im Foyer des HCC", "note": "Bitte der Ausschilderung zum Future Meeting Space folgen.", "category": "plenary", "sort_order": 0},
        {"day": 1, "time": "13:00", "duration_minutes": 20, "item_type": "organisation", "title": "Beginn der Veranstaltung", "note": "Saal Future Meeting Space", "category": "plenary", "sort_order": 1},
        {"day": 1, "time": "13:20", "duration_minutes": 55, "item_type": "vortrag", "title": "Präsentation DAC zum Einsatz von Künstlicher Intelligenz im Rahmen der Prüftätigkeit", "category": "plenary", "sort_order": 2},
        {"day": 1, "time": "14:15", "duration_minutes": 45, "item_type": "vortrag", "title": "Einführungsvortrag zur Entwicklung der Personalkostenpauschalierung in Niedersachsen inkl. Ausblick auf die FP 28-35", "speaker": "Lena Xyländer (stellv. Referatsleiterin Prüfbehörde EFRE/ESF Niedersachsen)", "category": "plenary", "sort_order": 3},
        {"day": 1, "time": "15:00", "duration_minutes": 30, "item_type": "pause", "title": "Kaffeepause", "category": "plenary", "sort_order": 4},
        {"day": 1, "time": "15:30", "duration_minutes": 90, "item_type": "workshop", "title": "Beginn der Workshops", "category": "plenary", "sort_order": 5},
        {"day": 1, "time": "17:00", "duration_minutes": 5, "item_type": "organisation", "title": "Ende der Workshops (Tag 1)", "category": "plenary", "sort_order": 6},
        # ── Tag 2 (Mittwoch 06.05.) — Plenum ────────────────────────────
        {"day": 2, "time": "09:00", "duration_minutes": 480, "item_type": "workshop", "title": "Beginn der Workshops", "category": "plenary", "sort_order": 10},
        {"day": 2, "time": "17:00", "duration_minutes": 5, "item_type": "organisation", "title": "Ende der Workshops (Tag 2)", "category": "plenary", "sort_order": 11},
        {"day": 2, "time": "19:00", "duration_minutes": 180, "item_type": "organisation", "title": "Abendveranstaltung im Gartensaal des Neuen Rathauses", "note": "Rückseite des Gebäudes mit Blick auf den Maschteich. Adresse: Platz d. Menschenrechte 2, 30159 Hannover", "category": "plenary", "sort_order": 12},
        # ── Tag 3 (Donnerstag 07.05.) — Plenum ──────────────────────────
        {"day": 3, "time": "09:00", "duration_minutes": 60, "item_type": "workshop", "title": "Beginn der Workshops", "category": "plenary", "sort_order": 20},
        {"day": 3, "time": "10:00", "duration_minutes": 15, "item_type": "organisation", "title": "Zusammenfinden aller Teilnehmenden", "note": "Saal Future Meeting Space", "category": "plenary", "sort_order": 21},
        {"day": 3, "time": "10:15", "duration_minutes": 165, "item_type": "diskussion", "title": "Vorstellung der Workshop-Ergebnisse", "category": "plenary", "sort_order": 22},
        {"day": 3, "time": "13:00", "duration_minutes": 15, "item_type": "organisation", "title": "Verabschiedung und Ende der Veranstaltung", "category": "plenary", "sort_order": 23},
        # ── Tag 1 — Workshop 5 Detail (15:30–17:00) ─────────────────────
        {"day": 1, "time": "15:30", "duration_minutes": 20, "item_type": "vortrag", "title": "Einführung: KI in der EFRE-Prüfbehörde", "speaker": "Jan Riener", "category": "workshop5", "sort_order": 100, "scenario_id": None},
        {"day": 1, "time": "15:50", "duration_minutes": 20, "item_type": "workshop", "title": "Szenario 1: Dokumentenanalyse", "speaker": "Jan Riener", "category": "workshop5", "sort_order": 101, "scenario_id": 1},
        {"day": 1, "time": "16:10", "duration_minutes": 20, "item_type": "workshop", "title": "Szenario 2: Checklisten-Unterstützung (VKO)", "speaker": "Jan Riener", "category": "workshop5", "sort_order": 102, "scenario_id": 2},
        {"day": 1, "time": "16:30", "duration_minutes": 20, "item_type": "workshop", "title": "Szenario 3: Halluzinations-Demo (RAG)", "speaker": "Jan Riener", "category": "workshop5", "sort_order": 103, "scenario_id": 3},
        {"day": 1, "time": "16:50", "duration_minutes": 10, "item_type": "diskussion", "title": "Fragen und Diskussion Block 1", "category": "workshop5", "sort_order": 104},
        # ── Tag 2 — Workshop 5 Detail (09:00–17:00) ─────────────────────
        {"day": 2, "time": "09:00", "duration_minutes": 20, "item_type": "workshop", "title": "Szenario 4: Berichtsentwurf", "speaker": "Jan Riener", "category": "workshop5", "sort_order": 200, "scenario_id": 4},
        {"day": 2, "time": "09:20", "duration_minutes": 20, "item_type": "workshop", "title": "Szenario 5: Vorab-Upload & RAG", "speaker": "Jan Riener", "category": "workshop5", "sort_order": 201, "scenario_id": 5},
        {"day": 2, "time": "09:40", "duration_minutes": 25, "item_type": "workshop", "title": "Szenario 6: Begünstigtenverzeichnis", "speaker": "Jan Riener", "category": "workshop5", "sort_order": 202, "scenario_id": 6},
        {"day": 2, "time": "10:05", "duration_minutes": 25, "item_type": "diskussion", "title": "Eingereichte Themen aus dem Voting", "category": "workshop5", "sort_order": 203},
    ]
    for item_data in defaults:
        db.add(AgendaItem(**item_data))
    db.commit()
    log.info("Default-Agenda mit %d Programmpunkten erstellt.", len(defaults))


def _get_meta(db: Session) -> WorkshopMeta:
    meta = db.query(WorkshopMeta).first()
    if not meta:
        meta = WorkshopMeta(
            id=1,
            title="Prüferworkshop der Prüfbehörden 2026",
            subtitle="Workshop 5",
            date="05.–07. Mai 2026",
            time="Di ab 12:00, Mi/Do ab 09:00 Uhr",
            location_short="Hannover",
            location_full="Hannover Congress Centrum (HCC), Future Meeting Space, Theodor-Heuss-Platz 1-3, 30175 Hannover",
            organizer="",
            registration_deadline="25. April 2026",
        )
        db.add(meta)
        db.commit()
        db.refresh(meta)
        # Auch Default-Agenda erstellen
        _seed_default_agenda(db)
    return meta

def _check_moderator(request: Request, pin: str, db: Session):
    """Prueft ob der Aufruf von einem Moderator (Token) oder Admin (PIN) kommt."""
    # 1. Token-basierte Auth
    from routers.auth import _sessions, MODERATOR_EMAILS
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    session = _sessions.get(token)
    if session and session.get("email", "").lower() in MODERATOR_EMAILS:
        return True
    # 2. PIN-basierte Auth (Fallback)
    meta = _get_meta(db)
    if pin and pin == meta.admin_pin:
        return True
    raise HTTPException(403, "Nicht berechtigt. Moderator-Login oder PIN erforderlich.")


def _make_invite_token(email: str) -> str:
    """Deterministischer Token aus E-Mail — gleiche E-Mail = gleicher Token."""
    return hashlib.sha256(f"workshop2026:{email.lower().strip()}".encode()).hexdigest()[:16]


# ── Public: Tagesordnung ─────────────────────────────────────────────────────

@router.get("/meta", response_model=MetaOut)
def get_meta(db: Session = Depends(get_db)):
    return _get_meta(db)

@router.get("/agenda", response_model=list[AgendaItemOut])
def get_agenda(category: str | None = None, show_hidden: bool = False, db: Session = Depends(get_db)):
    """Tagesordnung, optional gefiltert nach Kategorie (plenary, workshop5)."""
    q = db.query(AgendaItem)
    if not show_hidden:
        q = q.filter(AgendaItem.visible == True)
    if category:
        q = q.filter(AgendaItem.category == category)
    return q.order_by(AgendaItem.day, AgendaItem.sort_order).all()

@router.get("/agenda/days")
def get_agenda_by_days(category: str | None = None, show_hidden: bool = False, db: Session = Depends(get_db)):
    """Tagesordnung gruppiert nach Tagen."""
    q = db.query(AgendaItem)
    if not show_hidden:
        q = q.filter(AgendaItem.visible == True)
    if category:
        q = q.filter(AgendaItem.category == category)
    items = q.order_by(AgendaItem.day, AgendaItem.sort_order).all()

    days = {}
    for item in items:
        d = item.day or 1
        if d not in days:
            days[d] = {"day": d, "label": DAY_LABELS.get(d, f"Tag {d}"), "items": []}
        days[d]["items"].append(AgendaItemOut.model_validate(item).model_dump())
    return list(days.values())


# ── Public: Einladungslink ──────────────────────────────────────────────────

@router.get("/invite/{token}", response_model=InviteOut)
def get_invite(token: str, db: Session = Depends(get_db)):
    """Liest vorausgefuellte Daten fuer einen Einladungslink."""
    reg = db.query(Registration).filter(Registration.invite_token == token).first()
    if not reg:
        raise HTTPException(404, "Einladungslink ungueltig oder abgelaufen.")
    return InviteOut(
        first_name=reg.first_name,
        last_name=reg.last_name,
        organization=reg.organization,
        email=reg.email,
        department=reg.department,
        fund=reg.fund,
        already_registered=reg.privacy_accepted,
    )


# ── Public: Anmeldung ────────────────────────────────────────────────────────

@router.post("/register", status_code=201)
def register(data: RegistrationCreate, token: str | None = None, db: Session = Depends(get_db)):
    if not data.privacy_accepted:
        raise HTTPException(400, "Datenschutzhinweis muss akzeptiert werden.")

    # Bei Einladungslink: bestehende Registrierung aktualisieren
    if token:
        reg = db.query(Registration).filter(Registration.invite_token == token).first()
        if reg:
            reg.privacy_accepted = data.privacy_accepted
            reg.anthropic_consent = data.anthropic_consent
            if data.department:
                reg.department = data.department
            db.commit()
            db.refresh(reg)
            return {"status": "registered", "registration_id": reg.id}

    # Pruefen ob E-Mail schon registriert
    existing = db.query(Registration).filter(Registration.email.ilike(data.email.strip())).first()
    if existing:
        existing.privacy_accepted = data.privacy_accepted
        existing.anthropic_consent = data.anthropic_consent
        if data.department:
            existing.department = data.department
        if data.fund:
            existing.fund = data.fund
        if not existing.invite_token:
            existing.invite_token = _make_invite_token(data.email)
        db.commit()
        db.refresh(existing)
        return {"status": "registered", "registration_id": existing.id}

    reg = Registration(
        first_name=data.first_name,
        last_name=data.last_name,
        organization=data.organization,
        email=data.email,
        department=data.department,
        fund=data.fund,
        privacy_accepted=data.privacy_accepted,
        anthropic_consent=data.anthropic_consent,
        invite_token=_make_invite_token(data.email),
    )
    db.add(reg)
    db.commit()
    db.refresh(reg)
    return {"status": "registered", "registration_id": reg.id}


@router.post("/register/upload/{registration_id}")
async def upload_attachment(
    registration_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Datei-Upload fuer eine Anmeldung (diverse Formate, max 50 MB)."""
    reg = db.query(Registration).filter(Registration.id == registration_id).first()
    if not reg:
        raise HTTPException(404, "Anmeldung nicht gefunden.")

    MAX_SIZE = 10 * 1024 * 1024  # 10 MB fuer Registrierungs-Uploads
    allowed = {".pdf", ".docx"}

    import os
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed:
        raise HTTPException(400, f"Dateityp '{ext}' nicht erlaubt. Erlaubt: PDF, DOCX.")

    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(400, "Datei zu gross (max. 10 MB).")

    upload_dir = "/app/data/uploads"
    os.makedirs(upload_dir, exist_ok=True)

    import re as _re
    clean_name = _re.sub(r'[^a-zA-Z0-9._-]', '_', file.filename or 'upload')
    safe_name = f"{registration_id}_{clean_name}"
    filepath = os.path.join(upload_dir, safe_name)
    if not os.path.realpath(filepath).startswith(os.path.realpath(upload_dir)):
        raise HTTPException(400, "Ungültiger Dateiname.")
    with open(filepath, "wb") as f:
        f.write(content)

    reg.filename = safe_name
    db.commit()

    return {"status": "uploaded", "filename": safe_name}


# ── Public: Themenboard ──────────────────────────────────────────────────────

@router.post("/topics", status_code=201)
def submit_topic(
    registration_id: str,
    data: TopicCreate,
    db: Session = Depends(get_db),
):
    reg = db.query(Registration).filter(Registration.id == registration_id).first()
    if not reg:
        raise HTTPException(404, "Anmeldung nicht gefunden.")
    submission = TopicSubmission(
        registration_id=registration_id,
        topic=data.topic,
        question=data.question,
        notes=data.notes,
        visibility=data.visibility,
        anonymous=data.anonymous,
        organization=reg.organization if reg and not data.anonymous else None,
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)
    return {"status": "submitted", "topic_id": submission.id}


@router.get("/topics", response_model=list[TopicOut])
def list_topics(db: Session = Depends(get_db)):
    """Oeffentliche Themen (sortiert nach Votes)."""
    topics = (
        db.query(TopicSubmission)
        .filter(TopicSubmission.visibility == SubmissionVisibility.PUBLIC)
        .order_by(TopicSubmission.votes.desc(), TopicSubmission.created_at)
        .all()
    )
    results = []
    for t in topics:
        out = TopicOut.model_validate(t)
        if t.anonymous:
            out.organization = None
        results.append(out)
    return results


@router.post("/topics/{topic_id}/vote")
def vote_topic(topic_id: str, db: Session = Depends(get_db)):
    topic = db.query(TopicSubmission).filter(TopicSubmission.id == topic_id).first()
    if not topic:
        raise HTTPException(404, "Thema nicht gefunden.")
    if topic.visibility != SubmissionVisibility.PUBLIC:
        raise HTTPException(403, "Nur oeffentliche Themen koennen gevotet werden.")
    topic.votes = (topic.votes or 0) + 1
    db.commit()
    return {"votes": topic.votes}


# ── Admin: PIN-Authentifizierung ──────────────────────────────────────────────

@router.post("/admin/auth")
def admin_auth(body: AdminAuth, request: Request, db: Session = Depends(get_db)):
    # Auth-Endpoint: Token ODER PIN akzeptieren
    from routers.auth import _sessions, MODERATOR_EMAILS
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    session = _sessions.get(token)
    if session and session.get("email", "").lower() in MODERATOR_EMAILS:
        return {"status": "ok"}
    meta = _get_meta(db)
    if body.pin != meta.admin_pin:
        raise HTTPException(403, "Falscher PIN.")
    return {"status": "ok"}


# ── Admin: Meta ───────────────────────────────────────────────────────────────

@router.put("/admin/meta", response_model=MetaOut)
def update_meta(data: MetaUpdate, request: Request, pin: str = "", db: Session = Depends(get_db)):
    _check_moderator(request, pin, db)
    meta = _get_meta(db)
    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(meta, key, val)
    db.commit()
    db.refresh(meta)
    return meta


# ── Admin: Agenda CRUD ────────────────────────────────────────────────────────

@router.post("/admin/agenda", response_model=AgendaItemOut, status_code=201)
def create_agenda_item(data: AgendaItemCreate, request: Request, pin: str = "", db: Session = Depends(get_db)):
    _check_moderator(request, pin, db)
    max_order = db.query(AgendaItem).count()
    item = AgendaItem(
        day=data.day,
        time=data.time,
        duration_minutes=data.duration_minutes,
        item_type=data.item_type,
        title=data.title,
        speaker=data.speaker,
        note=data.note,
        category=data.category,
        scenario_id=data.scenario_id,
        sort_order=max_order,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/admin/agenda/reorder")
def reorder_agenda(order: list[str], request: Request, pin: str = "", db: Session = Depends(get_db)):
    """Aktualisiert die Reihenfolge der Programmpunkte."""
    _check_moderator(request, pin, db)
    for idx, item_id in enumerate(order):
        item = db.query(AgendaItem).filter(AgendaItem.id == item_id).first()
        if item:
            item.sort_order = idx
    db.commit()
    return {"status": "reordered"}


@router.put("/admin/agenda/{item_id}", response_model=AgendaItemOut)
def update_agenda_item(item_id: str, data: AgendaItemUpdate, request: Request, pin: str = "", db: Session = Depends(get_db)):
    _check_moderator(request, pin, db)
    item = db.query(AgendaItem).filter(AgendaItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "Programmpunkt nicht gefunden.")
    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(item, key, val)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/admin/agenda/{item_id}", status_code=204)
def delete_agenda_item(item_id: str, request: Request, pin: str = "", db: Session = Depends(get_db)):
    _check_moderator(request, pin, db)
    item = db.query(AgendaItem).filter(AgendaItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "Programmpunkt nicht gefunden.")
    db.delete(item)
    db.commit()


@router.post("/admin/agenda/{item_id}/toggle-visible", response_model=AgendaItemOut)
def toggle_visible(item_id: str, request: Request, pin: str = "", db: Session = Depends(get_db)):
    """Schaltet die Sichtbarkeit eines Agenda-Punkts um."""
    _check_moderator(request, pin, db)
    item = db.query(AgendaItem).filter(AgendaItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "Programmpunkt nicht gefunden.")
    item.visible = not item.visible
    db.commit()
    db.refresh(item)
    return item


# ── Admin: Agenda-Status steuern (Moderator-Controls) ────────────────────────

@router.put("/admin/agenda/{item_id}/status")
def set_agenda_status(item_id: str, status: AgendaItemStatus, request: Request, pin: str = "", db: Session = Depends(get_db)):
    """Setzt den Status eines Agenda-Punkts (pending/active/done/skipped)."""
    _check_moderator(request, pin, db)
    item = db.query(AgendaItem).filter(AgendaItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "Programmpunkt nicht gefunden.")
    # Wenn auf 'active' gesetzt, alle anderen aktiven auf 'pending' zuruecksetzen
    if status == AgendaItemStatus.ACTIVE:
        db.query(AgendaItem).filter(
            AgendaItem.status == AgendaItemStatus.ACTIVE,
            AgendaItem.category == item.category,
        ).update({"status": AgendaItemStatus.PENDING})
    item.status = status
    db.commit()
    db.refresh(item)
    return AgendaItemOut.model_validate(item)


@router.post("/admin/agenda/{item_id}/start")
def start_agenda_item(item_id: str, request: Request, pin: str = "", db: Session = Depends(get_db)):
    """Markiert einen Punkt als aktiv und den vorherigen als erledigt."""
    _check_moderator(request, pin, db)
    item = db.query(AgendaItem).filter(AgendaItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "Programmpunkt nicht gefunden.")
    # Aktuell aktiven Punkt auf done setzen
    db.query(AgendaItem).filter(
        AgendaItem.status == AgendaItemStatus.ACTIVE,
        AgendaItem.category == item.category,
    ).update({"status": AgendaItemStatus.DONE})
    item.status = AgendaItemStatus.ACTIVE
    item.started_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(item)
    return AgendaItemOut.model_validate(item)


@router.post("/admin/agenda/{item_id}/reset-timer")
def reset_timer(item_id: str, request: Request, pin: str = "", db: Session = Depends(get_db)):
    """Setzt den Timer eines aktiven Punkts zurueck (startet die Zeit neu)."""
    _check_moderator(request, pin, db)
    item = db.query(AgendaItem).filter(AgendaItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "Programmpunkt nicht gefunden.")
    if item.status != AgendaItemStatus.ACTIVE:
        raise HTTPException(400, "Timer kann nur bei aktiven Punkten zurueckgesetzt werden.")
    item.started_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(item)
    return AgendaItemOut.model_validate(item)


@router.post("/admin/agenda/{item_id}/adjust-time")
def adjust_time(item_id: str, minutes: int = 5, request: Request = None, pin: str = "", db: Session = Depends(get_db)):
    """Verlaengert oder verkuerzt die Dauer eines Agenda-Punkts um X Minuten."""
    _check_moderator(request, pin, db)
    item = db.query(AgendaItem).filter(AgendaItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "Programmpunkt nicht gefunden.")
    new_duration = max(5, min(480, item.duration_minutes + minutes))
    item.duration_minutes = new_duration
    db.commit()
    db.refresh(item)
    return AgendaItemOut.model_validate(item)


@router.post("/admin/agenda/reset-status")
def reset_agenda_status(request: Request, pin: str = "", category: str | None = None, db: Session = Depends(get_db)):
    """Setzt alle Status auf pending zurueck (z.B. vor Tagesbeginn)."""
    _check_moderator(request, pin, db)
    q = db.query(AgendaItem)
    if category:
        q = q.filter(AgendaItem.category == category)
    count = q.update({"status": AgendaItemStatus.PENDING})
    db.commit()
    return {"reset": count}


# ── Admin: Anmeldungen einsehen ───────────────────────────────────────────────

@router.get("/admin/registrations")
def list_registrations(request: Request, pin: str = "", db: Session = Depends(get_db)):
    _check_moderator(request, pin, db)
    regs = db.query(Registration).order_by(Registration.created_at.desc()).all()
    return {
        "count": len(regs),
        "registrations": [
            {
                "id": r.id,
                "first_name": r.first_name,
                "last_name": r.last_name,
                "organization": r.organization,
                "email": r.email,
                "department": r.department,
                "fund": r.fund,
                "invite_token": r.invite_token,
                "privacy_accepted": r.privacy_accepted,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in regs
        ],
    }


# ── Admin: Einladungslinks generieren ────────────────────────────────────────

@router.post("/admin/generate-invites")
def generate_invites(request: Request, pin: str = "", db: Session = Depends(get_db)):
    """Generiert Einladungs-Tokens fuer alle Registrierungen ohne Token."""
    _check_moderator(request, pin, db)
    regs = db.query(Registration).filter(Registration.invite_token.is_(None)).all()
    for reg in regs:
        reg.invite_token = _make_invite_token(reg.email)
    db.commit()
    return {"updated": len(regs)}


# ── Admin: Alle Themen (auch nicht-oeffentliche) ──────────────────────────────

@router.get("/admin/topics")
def list_all_topics(request: Request, pin: str = "", db: Session = Depends(get_db)):
    _check_moderator(request, pin, db)
    topics = db.query(TopicSubmission).order_by(TopicSubmission.votes.desc()).all()
    return {
        "count": len(topics),
        "topics": [
            {
                "id": t.id,
                "topic": t.topic,
                "question": t.question,
                "notes": t.notes,
                "organization": t.organization,
                "visibility": t.visibility,
                "anonymous": t.anonymous,
                "votes": t.votes,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in topics
        ],
    }
