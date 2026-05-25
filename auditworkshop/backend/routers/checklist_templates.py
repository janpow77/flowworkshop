"""
flowworkshop · routers/checklist_templates.py

API fuer das KOM-Checklisten-Template-Subsystem (Designer). Eigenstaendig und
projekt-ungebunden — siehe models/checklist_template.py.

Umfang dieser Phase (CRUD + Tree + Rechtepruefung + Versionierung):
  - Template-CRUD (Ersteller wird owner)
  - Knoten-CRUD + rekursiver Baum + Move (Reparent/Reorder)
  - Antwortsets (global + checklistenspezifisch) + Optionen
  - Kategorien je Template
  - Rollenbasierte Rechtepruefung (viewer/commenter/editor/owner)
  - Jede schreibende Knoten-Operation schreibt einen Verlaufseintrag
    (ChecklistNodeHistory) mit Snapshot, Diff und Versionszaehler.

NICHT enthalten: Einladungs-/Notification-Flow, Locks/Presence, Export,
Uebersetzung — siehe spaetere Phasen.
"""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models.checklist_template import (
    ChecklistTemplate,
    ChecklistTemplateNode,
    ChecklistAnswerSet,
    ChecklistAnswerOption,
    ChecklistQuestionCategory,
    ChecklistNodeHistory,
    ChecklistMember,
    ChecklistInvite,
    MemberRole,
    InviteStatus,
    NodeChangeType,
    TemplateStatus,
)
from models.registration import Registration, SecurityAuditLog
from models.automation import Notification
from schemas.checklist_template import (
    TemplateCreate, TemplateUpdate, TemplateOut, TemplateDetailOut,
    NodeCreate, NodeUpdate, NodeMove, NodeOut, NodeTreeOut,
    AnswerSetCreate, AnswerSetUpdate, AnswerSetOut,
    AnswerOptionCreate, AnswerOptionUpdate, AnswerOptionOut,
    CategoryCreate, CategoryUpdate, CategoryOut,
    MemberOut, InviteOut, InviteCreate, MemberRoleUpdate,
)
from routers.auth import require_session, ADMIN_EMAILS, MODERATOR_EMAILS
from services.checklist_events import broker as _collab_broker

router = APIRouter(
    prefix="/api/checklist-templates",
    tags=["checklist-templates"],
    dependencies=[Depends(require_session)],
)
log = logging.getLogger(__name__)


# ── Rollen-Rangfolge fuer die Rechtepruefung ──────────────────────────────────
# Hoeherer Rang = mehr Rechte. viewer < commenter < editor < owner.
_ROLE_RANK = {
    MemberRole.VIEWER.value: 1,
    MemberRole.COMMENTER.value: 2,
    MemberRole.EDITOR.value: 3,
    MemberRole.OWNER.value: 4,
}


def _utcnow() -> datetime:
    """Naive UTC-Zeit (konsistent mit den DateTime-Spalten ohne tz)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── Helfer: Rechtepruefung ────────────────────────────────────────────────────

def _get_member(template_id: str, user_id: str, db: Session) -> ChecklistMember | None:
    """Liefert die Mitgliedschaft eines Nutzers an einem Template (oder None)."""
    return (
        db.query(ChecklistMember)
        .filter(
            ChecklistMember.template_id == template_id,
            ChecklistMember.user_id == user_id,
        )
        .first()
    )


def _require_role(
    template_id: str, user_id: str, min_role: MemberRole, db: Session,
) -> ChecklistMember:
    """Stellt sicher, dass der Nutzer am Template mindestens ``min_role`` hat.

    Wirft 404, wenn das Template nicht existiert, 403, wenn der Nutzer kein
    Mitglied ist oder seine Rolle nicht ausreicht. Gibt die Mitgliedschaft
    zurueck.
    """
    template = db.query(ChecklistTemplate).filter(ChecklistTemplate.id == template_id).first()
    if not template:
        raise HTTPException(404, "Checklisten-Template nicht gefunden.")
    member = _get_member(template_id, user_id, db)
    if not member:
        raise HTTPException(403, "Kein Zugriff auf dieses Checklisten-Template.")
    have = _ROLE_RANK.get(member.role, 0)
    need = _ROLE_RANK.get(min_role.value, 99)
    if have < need:
        raise HTTPException(
            403,
            f"Unzureichende Berechtigung — erforderlich: {min_role.value}, "
            f"vorhanden: {member.role}.",
        )
    return member


def _session_user_id(session: dict) -> str:
    uid = session.get("user_id")
    if not uid:
        raise HTTPException(401, "Sitzung ohne Nutzerkennung.")
    return uid


# ── Helfer: Audit-Trail ───────────────────────────────────────────────────────

def _audit(
    db: Session, *, actor_user_id: str, action: str,
    target_id: str | None = None, target_type: str = "checklist_template",
    metadata: dict | None = None,
) -> None:
    """Schreibt einen SecurityAuditLog-Eintrag (Plan v3.2 §3.5).

    Wird innerhalb derselben Transaktion wie die Fachaenderung committed, damit
    Audit-Eintrag und Aktion atomar zusammenhaengen."""
    db.add(SecurityAuditLog(
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        metadata_json=metadata,
    ))


# ── Helfer: Nutzer-Stammdaten (fuer angereicherte Ausgaben) ───────────────────

def _load_registrations(user_ids: set[str], db: Session) -> dict[str, Registration]:
    """Laedt Registration-Stammdaten fuer eine Menge von Nutzer-IDs als Map.

    Fehlende IDs (z.B. geloeschte Nutzer) fehlen schlicht in der Map."""
    ids = {uid for uid in user_ids if uid}
    if not ids:
        return {}
    rows = db.query(Registration).filter(Registration.id.in_(ids)).all()
    return {r.id: r for r in rows}


def _full_name(reg: Registration | None) -> str | None:
    """Zusammengesetzter Anzeigename eines Nutzers (oder None)."""
    if not reg:
        return None
    name = f"{reg.first_name or ''} {reg.last_name or ''}".strip()
    return name or None


def _member_out(member: ChecklistMember, regs: dict[str, Registration]) -> MemberOut:
    """Serialisiert eine Mitgliedschaft inkl. Nutzer-Stammdaten."""
    reg = regs.get(member.user_id)
    return MemberOut(
        id=member.id,
        template_id=member.template_id,
        user_id=member.user_id,
        role=member.role,
        invited_by_id=member.invited_by_id,
        created_at=member.created_at,
        user_name=_full_name(reg),
        user_email=reg.email if reg else None,
        organization=reg.organization if reg else None,
        bundesland=reg.bundesland if reg else None,
        function_role=reg.function_role if reg else None,
    )


def _invite_out(invite: ChecklistInvite, regs: dict[str, Registration]) -> InviteOut:
    """Serialisiert eine Einladung inkl. Stammdaten des eingeladenen Nutzers."""
    reg = regs.get(invite.invited_user_id)
    inviter = regs.get(invite.invited_by_id) if invite.invited_by_id else None
    return InviteOut(
        id=invite.id,
        template_id=invite.template_id,
        invited_user_id=invite.invited_user_id,
        invited_by_id=invite.invited_by_id,
        role=invite.role,
        status=invite.status,
        created_at=invite.created_at,
        responded_at=invite.responded_at,
        invited_user_name=_full_name(reg),
        invited_user_email=reg.email if reg else None,
        organization=reg.organization if reg else None,
        bundesland=reg.bundesland if reg else None,
        function_role=reg.function_role if reg else None,
        invited_by_name=_full_name(inviter),
    )


# ── Helfer: Serialisierung ────────────────────────────────────────────────────

def _template_out(
    tpl: ChecklistTemplate, my_role: str | None, node_count: int | None = None,
) -> TemplateOut:
    """Serialisiert ein Template fuer die Ausgabe.

    ``node_count`` kann von aussen vorgegeben werden (z.B. aus einer vorab
    berechneten COUNT(*)-Aggregation in der Listenansicht, F-011); ohne Vorgabe
    wird die Lazy-Beziehung ``tpl.nodes`` ausgewertet (Detailansicht, in der die
    Knoten ohnehin geladen sind)."""
    return TemplateOut(
        id=tpl.id,
        owner_id=tpl.owner_id,
        title=tpl.title,
        description=tpl.description,
        source_language=tpl.source_language,
        target_language=tpl.target_language,
        source_document_name=tpl.source_document_name,
        properties_json=tpl.properties_json,
        statistics_json=tpl.statistics_json,
        status=tpl.status,
        node_count=node_count if node_count is not None else len(tpl.nodes),
        my_role=my_role,
        created_at=tpl.created_at,
        updated_at=tpl.updated_at,
    )


# Knoten-Felder, die fuer Snapshot/Diff der Versionierung relevant sind.
_NODE_TRACKED_FIELDS = (
    "parent_id", "node_type", "branch", "ja_label", "nein_label",
    "decision_parent_id", "sort_order", "title", "public_remark",
    "remark_snippets_json", "eingabetyp", "answer_type", "answer_set_id",
    "category_id", "legal_reference", "relevant_documents_json", "is_header_field",
)


def _node_snapshot(node: ChecklistTemplateNode) -> dict:
    """Voll-Snapshot eines Knotens als JSON-faehiges Dict."""
    return {field: getattr(node, field) for field in _NODE_TRACKED_FIELDS}


def _node_event_payload(node: ChecklistTemplateNode) -> dict:
    """Kompakte, JSON-faehige Knoten-Darstellung fuer Live-Events (SSE).

    Enthaelt id + template_id zusaetzlich zum Snapshot, damit das Frontend den
    betroffenen Knoten eindeutig zuordnen kann."""
    return {"id": node.id, "template_id": node.template_id, **_node_snapshot(node)}


def _latest_node_version(template_id: str, node_id: str, db: Session) -> int:
    """Hoechste bisher vergebene node_version fuer einen Knoten (0 = keine)."""
    latest = (
        db.query(func.max(ChecklistNodeHistory.node_version))
        .filter(
            ChecklistNodeHistory.template_id == template_id,
            ChecklistNodeHistory.node_id == node_id,
        )
        .scalar()
    )
    return int(latest or 0)


def _write_history(
    *,
    db: Session,
    template_id: str,
    node_id: str,
    change_type: NodeChangeType,
    changed_by_id: str,
    snapshot: dict | None = None,
    changed_fields: dict | None = None,
    old_parent_id: str | None = None,
    new_parent_id: str | None = None,
    old_position: int | None = None,
    new_position: int | None = None,
) -> None:
    """Schreibt einen Verlaufseintrag und zaehlt die node_version hoch."""
    version = _latest_node_version(template_id, node_id, db) + 1
    entry = ChecklistNodeHistory(
        id=str(uuid.uuid4()),
        template_id=template_id,
        node_id=node_id,
        node_version=version,
        change_type=change_type.value,
        node_snapshot=snapshot,
        changed_fields=changed_fields,
        old_parent_id=old_parent_id,
        new_parent_id=new_parent_id,
        old_position=old_position,
        new_position=new_position,
        changed_by_id=changed_by_id,
    )
    db.add(entry)


def _diff_fields(before: dict, after: dict) -> dict:
    """Berechnet ein {feld: {old, new}}-Diff fuer geaenderte Felder."""
    diff: dict = {}
    for field in _NODE_TRACKED_FIELDS:
        old_val = before.get(field)
        new_val = after.get(field)
        if old_val != new_val:
            diff[field] = {"old": old_val, "new": new_val}
    return diff


# ── Template-CRUD ─────────────────────────────────────────────────────────────

@router.post("/", response_model=TemplateDetailOut, status_code=201)
def create_template(
    data: TemplateCreate, request: Request, db: Session = Depends(get_db),
):
    """Legt ein neues Template an; der Ersteller wird owner (Mitgliedschaft)."""
    session = require_session(request)
    user_id = _session_user_id(session)

    tpl = ChecklistTemplate(
        id=str(uuid.uuid4()),
        owner_id=user_id,
        title=data.title,
        description=data.description,
        source_language=data.source_language,
        target_language=data.target_language,
        source_document_name=data.source_document_name,
        properties_json=data.properties_json,
        status=data.status.value,
    )
    db.add(tpl)
    db.flush()

    member = ChecklistMember(
        id=str(uuid.uuid4()),
        template_id=tpl.id,
        user_id=user_id,
        role=MemberRole.OWNER.value,
        invited_by_id=user_id,
    )
    db.add(member)
    db.commit()
    db.refresh(tpl)
    log.info("Checklisten-Template erstellt: %s durch %s", tpl.id, user_id)
    return _template_detail_out(tpl, MemberRole.OWNER.value, db)


def _template_detail_out(
    tpl: ChecklistTemplate, my_role: str | None, db: Session | None = None,
) -> TemplateDetailOut:
    # Mitglieder mit Nutzer-Stammdaten anreichern (sofern eine Session vorliegt).
    if db is not None:
        regs = _load_registrations({m.user_id for m in tpl.members}, db)
        members_out = [_member_out(m, regs) for m in tpl.members]
    else:
        members_out = [MemberOut.model_validate(m) for m in tpl.members]
    return TemplateDetailOut(
        **_template_out(tpl, my_role).model_dump(),
        members=members_out,
        categories=[
            CategoryOut.model_validate(c)
            for c in sorted(tpl.categories, key=lambda x: (x.sort_order or 0, x.name or ""))
        ],
        answer_sets=[
            AnswerSetOut.model_validate(s)
            for s in sorted(tpl.answer_sets, key=lambda x: (x.sort_order or 0, x.name or ""))
        ],
    )


@router.get("/", response_model=list[TemplateOut])
def list_templates(request: Request, db: Session = Depends(get_db)):
    """Listet Templates, an denen der Nutzer Mitglied ist, sowie veroeffentlichte."""
    session = require_session(request)
    user_id = _session_user_id(session)

    my_memberships = (
        db.query(ChecklistMember)
        .filter(ChecklistMember.user_id == user_id)
        .all()
    )
    member_template_ids = {m.template_id for m in my_memberships}
    role_by_template = {m.template_id: m.role for m in my_memberships}

    templates = (
        db.query(ChecklistTemplate)
        .filter(
            (ChecklistTemplate.id.in_(member_template_ids))
            | (ChecklistTemplate.status == TemplateStatus.PUBLISHED.value)
        )
        .order_by(ChecklistTemplate.updated_at.desc().nullslast())
        .all()
    )

    # F-011: Knotenzahl je Template per COUNT(*)-Aggregation in EINEM Query
    # bestimmen, statt fuer jedes Template die komplette nodes-Beziehung zu laden
    # (N+1 + grosse Ergebnismengen in der Uebersicht). Nur fuer die hier
    # gelisteten Template-IDs.
    template_ids = [t.id for t in templates]
    node_counts: dict[str, int] = {}
    if template_ids:
        count_rows = (
            db.query(
                ChecklistTemplateNode.template_id,
                func.count(ChecklistTemplateNode.id),
            )
            .filter(ChecklistTemplateNode.template_id.in_(template_ids))
            .group_by(ChecklistTemplateNode.template_id)
            .all()
        )
        node_counts = {tid: int(cnt or 0) for tid, cnt in count_rows}

    return [
        _template_out(t, role_by_template.get(t.id), node_count=node_counts.get(t.id, 0))
        for t in templates
    ]


# ── Globale Antwortset-Bibliothek ─────────────────────────────────────────────
# WICHTIG: vor den /{template_id}-Routen definiert, sonst wuerde das literale
# Segment "answer-sets" als template_id gematcht (FastAPI matcht in Reihenfolge).

@router.get("/answer-sets", response_model=list[AnswerSetOut])
def list_global_answer_sets(request: Request, db: Session = Depends(get_db)):
    """Globale Antwortset-Bibliothek (template_id IS NULL) — fuer alle lesbar."""
    require_session(request)
    sets = (
        db.query(ChecklistAnswerSet)
        .filter(ChecklistAnswerSet.template_id.is_(None))
        .order_by(ChecklistAnswerSet.sort_order, ChecklistAnswerSet.name)
        .all()
    )
    return [AnswerSetOut.model_validate(s) for s in sets]


@router.post("/answer-sets", response_model=AnswerSetOut, status_code=201)
def create_global_answer_set(
    data: AnswerSetCreate, request: Request, db: Session = Depends(get_db),
):
    """Legt ein globales Antwortset an (jeder angemeldete Nutzer)."""
    require_session(request)
    return _create_answer_set(None, data, db)


@router.get("/{template_id}", response_model=TemplateDetailOut)
def get_template(template_id: str, request: Request, db: Session = Depends(get_db)):
    """Liefert ein Template inkl. Mitglieder, Kategorien und Antwortsets."""
    session = require_session(request)
    user_id = _session_user_id(session)

    tpl = db.query(ChecklistTemplate).filter(ChecklistTemplate.id == template_id).first()
    if not tpl:
        raise HTTPException(404, "Checklisten-Template nicht gefunden.")
    member = _get_member(template_id, user_id, db)
    if not member and tpl.status != TemplateStatus.PUBLISHED.value:
        raise HTTPException(403, "Kein Zugriff auf dieses Checklisten-Template.")
    return _template_detail_out(tpl, member.role if member else None, db)


@router.put("/{template_id}", response_model=TemplateDetailOut)
def update_template(
    template_id: str, data: TemplateUpdate, request: Request, db: Session = Depends(get_db),
):
    """Aendert Template-Metadaten (mindestens editor)."""
    session = require_session(request)
    user_id = _session_user_id(session)
    member = _require_role(template_id, user_id, MemberRole.EDITOR, db)

    tpl = db.query(ChecklistTemplate).filter(ChecklistTemplate.id == template_id).first()
    payload = data.model_dump(exclude_unset=True)
    if "status" in payload and payload["status"] is not None:
        payload["status"] = (
            payload["status"].value
            if isinstance(payload["status"], TemplateStatus)
            else payload["status"]
        )
    for key, val in payload.items():
        setattr(tpl, key, val)
    db.commit()
    db.refresh(tpl)
    return _template_detail_out(tpl, member.role, db)


@router.delete("/{template_id}", status_code=204)
def delete_template(template_id: str, request: Request, db: Session = Depends(get_db)):
    """Loescht ein Template samt Knoten/Antwortsets (owner-only)."""
    session = require_session(request)
    user_id = _session_user_id(session)
    _require_role(template_id, user_id, MemberRole.OWNER, db)

    tpl = db.query(ChecklistTemplate).filter(ChecklistTemplate.id == template_id).first()
    db.delete(tpl)
    db.commit()
    log.info("Checklisten-Template geloescht: %s durch %s", template_id, user_id)


# ── Mitglieder (Lese-Ausgabe + Verwaltung) ────────────────────────────────────

@router.get("/{template_id}/members", response_model=list[MemberOut])
def list_members(template_id: str, request: Request, db: Session = Depends(get_db)):
    """Listet die Mitglieder eines Templates (mindestens viewer).

    Liefert Bundesland und Funktion (function_role) je Mitglied mit, damit die
    Bund-Laender-Arbeitskreis-Anzeige im Frontend die Herkunft darstellen kann."""
    session = require_session(request)
    user_id = _session_user_id(session)
    _require_role(template_id, user_id, MemberRole.VIEWER, db)
    members = db.query(ChecklistMember).filter(ChecklistMember.template_id == template_id).all()
    regs = _load_registrations({m.user_id for m in members}, db)
    return [_member_out(m, regs) for m in members]


def _count_owners(template_id: str, db: Session) -> int:
    """Anzahl der owner-Mitglieder eines Templates."""
    return (
        db.query(ChecklistMember)
        .filter(
            ChecklistMember.template_id == template_id,
            ChecklistMember.role == MemberRole.OWNER.value,
        )
        .count()
    )


@router.put("/{template_id}/members/{member_user_id}", response_model=MemberOut)
def update_member_role(
    template_id: str, member_user_id: str, data: MemberRoleUpdate,
    request: Request, db: Session = Depends(get_db),
):
    """Aendert die Rolle eines Mitglieds (owner-only).

    Schutzregeln:
      - Der einzige owner kann sich nicht selbst herabstufen (sonst verwaist
        das Template ohne Eigentuemer).
      - Wird ein Mitglied zum owner befoerdert, ist das ausdruecklich erlaubt
        (Co-Ownership), die bisherige Owner-Mitgliedschaft bleibt bestehen.
    """
    session = require_session(request)
    actor_id = _session_user_id(session)
    _require_role(template_id, actor_id, MemberRole.OWNER, db)

    member = _get_member(template_id, member_user_id, db)
    if not member:
        raise HTTPException(404, "Mitglied nicht gefunden.")

    old_role = member.role
    new_role = data.role.value
    if old_role == new_role:
        regs = _load_registrations({member.user_id}, db)
        return _member_out(member, regs)

    # Letzten owner nicht herabstufen.
    if old_role == MemberRole.OWNER.value and new_role != MemberRole.OWNER.value:
        if _count_owners(template_id, db) <= 1:
            raise HTTPException(
                422,
                "Der letzte Eigentuemer kann nicht herabgestuft werden — "
                "ernennen Sie zuvor einen weiteren Eigentuemer.",
            )

    member.role = new_role
    _audit(
        db, actor_user_id=actor_id, action="checklist_member_role_changed",
        target_id=template_id,
        metadata={"member_user_id": member_user_id, "old_role": old_role, "new_role": new_role},
    )
    db.commit()
    db.refresh(member)
    log.info(
        "Checklisten-Mitglied %s an %s: Rolle %s → %s durch %s",
        member_user_id, template_id, old_role, new_role, actor_id,
    )
    regs = _load_registrations({member.user_id}, db)
    return _member_out(member, regs)


@router.delete("/{template_id}/members/{member_user_id}", status_code=204)
def remove_member(
    template_id: str, member_user_id: str,
    request: Request, db: Session = Depends(get_db),
):
    """Entfernt ein Mitglied aus dem Template (owner-only).

    Der einzige owner kann sich nicht selbst entfernen (Template wuerde ohne
    Eigentuemer zurueckbleiben)."""
    session = require_session(request)
    actor_id = _session_user_id(session)
    _require_role(template_id, actor_id, MemberRole.OWNER, db)

    member = _get_member(template_id, member_user_id, db)
    if not member:
        raise HTTPException(404, "Mitglied nicht gefunden.")

    if member.role == MemberRole.OWNER.value and _count_owners(template_id, db) <= 1:
        raise HTTPException(
            422,
            "Der letzte Eigentuemer kann sich nicht selbst entfernen — "
            "ernennen Sie zuvor einen weiteren Eigentuemer.",
        )

    db.delete(member)
    _audit(
        db, actor_user_id=actor_id, action="checklist_member_removed",
        target_id=template_id,
        metadata={"member_user_id": member_user_id, "role": member.role},
    )
    db.commit()
    log.info(
        "Checklisten-Mitglied %s aus %s entfernt durch %s",
        member_user_id, template_id, actor_id,
    )


# ── Einladungs-/Rollen-Flow (In-App-Notification, kein Mail) ──────────────────

@router.get("/{template_id}/invites", response_model=list[InviteOut])
def list_invites(
    template_id: str, request: Request,
    only_pending: bool = False, db: Session = Depends(get_db),
):
    """Listet Einladungen einer Checkliste (owner-only).

    ``only_pending=true`` filtert auf offene (pending) Einladungen. Jede
    Einladung wird mit den Stammdaten des eingeladenen Nutzers angereichert."""
    session = require_session(request)
    user_id = _session_user_id(session)
    _require_role(template_id, user_id, MemberRole.OWNER, db)

    q = db.query(ChecklistInvite).filter(ChecklistInvite.template_id == template_id)
    if only_pending:
        q = q.filter(ChecklistInvite.status == InviteStatus.PENDING.value)
    invites = q.order_by(ChecklistInvite.created_at.desc()).all()

    ids = {i.invited_user_id for i in invites} | {
        i.invited_by_id for i in invites if i.invited_by_id
    }
    regs = _load_registrations(ids, db)
    return [_invite_out(i, regs) for i in invites]


@router.post("/{template_id}/invites", response_model=InviteOut, status_code=201)
def create_invite(
    template_id: str, data: InviteCreate, request: Request, db: Session = Depends(get_db),
):
    """Laedt einen Nutzer zur Mitarbeit ein (owner-only).

    Legt eine ChecklistInvite (status=pending) an und erzeugt eine In-App-
    Notification (kind="checklist_invite") fuer den eingeladenen Nutzer — KEIN
    Mailversand. Faengt Doppel-Einladungen (bereits offene Einladung) sowie
    bereits aktive Mitgliedschaften ab. Die owner-Rolle kann nicht eingeladen
    werden."""
    session = require_session(request)
    actor_id = _session_user_id(session)
    _require_role(template_id, actor_id, MemberRole.OWNER, db)

    tpl = db.query(ChecklistTemplate).filter(ChecklistTemplate.id == template_id).first()

    if data.role == MemberRole.OWNER:
        raise HTTPException(422, "Die Eigentuemer-Rolle kann nicht per Einladung vergeben werden.")

    invited_user_id = data.user_id

    # Eingeladenen Nutzer pruefen (muss existieren).
    invited_reg = db.query(Registration).filter(Registration.id == invited_user_id).first()
    if not invited_reg:
        raise HTTPException(404, "Eingeladener Nutzer nicht gefunden.")

    # Sich selbst einladen ist sinnlos (Owner ist bereits Mitglied).
    if invited_user_id == actor_id:
        raise HTTPException(422, "Sie sind bereits Mitglied dieser Checkliste.")

    # Bereits aktives Mitglied?
    if _get_member(template_id, invited_user_id, db):
        raise HTTPException(409, "Dieser Nutzer ist bereits Mitglied der Checkliste.")

    # Bereits offene Einladung?
    existing = (
        db.query(ChecklistInvite)
        .filter(
            ChecklistInvite.template_id == template_id,
            ChecklistInvite.invited_user_id == invited_user_id,
            ChecklistInvite.status == InviteStatus.PENDING.value,
        )
        .first()
    )
    if existing:
        raise HTTPException(409, "Fuer diesen Nutzer existiert bereits eine offene Einladung.")

    invite = ChecklistInvite(
        id=str(uuid.uuid4()),
        template_id=template_id,
        invited_user_id=invited_user_id,
        invited_by_id=actor_id,
        role=data.role.value,
        status=InviteStatus.PENDING.value,
    )
    db.add(invite)
    db.flush()

    # In-App-Notification fuer den eingeladenen Nutzer (kein Mail).
    inviter_name = session.get("name") or "Eine Kollegin/ein Kollege"
    tpl_title = tpl.title if tpl else "Checkliste"
    notif = Notification(
        user_id=invited_user_id,
        kind="checklist_invite",
        title=f"Einladung zur Checkliste «{tpl_title}»",
        body=(
            f"{inviter_name} hat Sie als «{data.role.value}» zur Mitarbeit an der "
            f"Checkliste «{tpl_title}» eingeladen."
        ),
        link=f"/checklisten/{template_id}?invite={invite.id}",
    )
    db.add(notif)

    _audit(
        db, actor_user_id=actor_id, action="checklist_invite_created",
        target_id=template_id,
        metadata={"invite_id": invite.id, "invited_user_id": invited_user_id, "role": data.role.value},
    )
    db.commit()
    db.refresh(invite)
    log.info(
        "Checklisten-Einladung %s fuer %s an Template %s durch %s",
        invite.id, invited_user_id, template_id, actor_id,
    )
    regs = _load_registrations({invited_user_id, actor_id}, db)
    return _invite_out(invite, regs)


@router.delete("/{template_id}/invites/{invite_id}", status_code=204)
def revoke_invite(
    template_id: str, invite_id: str, request: Request, db: Session = Depends(get_db),
):
    """Widerruft eine offene Einladung (owner-only) — status=revoked."""
    session = require_session(request)
    actor_id = _session_user_id(session)
    _require_role(template_id, actor_id, MemberRole.OWNER, db)

    invite = (
        db.query(ChecklistInvite)
        .filter(ChecklistInvite.id == invite_id, ChecklistInvite.template_id == template_id)
        .first()
    )
    if not invite:
        raise HTTPException(404, "Einladung nicht gefunden.")
    if invite.status != InviteStatus.PENDING.value:
        raise HTTPException(
            422, f"Nur offene Einladungen koennen widerrufen werden (Status: {invite.status})."
        )

    invite.status = InviteStatus.REVOKED.value
    invite.responded_at = _utcnow()
    _audit(
        db, actor_user_id=actor_id, action="checklist_invite_revoked",
        target_id=template_id,
        metadata={"invite_id": invite_id, "invited_user_id": invite.invited_user_id},
    )
    db.commit()
    log.info("Checklisten-Einladung %s widerrufen durch %s", invite_id, actor_id)


def _load_own_invite(invite_id: str, user_id: str, db: Session) -> ChecklistInvite:
    """Laedt eine Einladung und stellt sicher, dass sie an ``user_id`` gerichtet
    und noch offen ist. Wirft 404/403/422 entsprechend."""
    invite = db.query(ChecklistInvite).filter(ChecklistInvite.id == invite_id).first()
    if not invite:
        raise HTTPException(404, "Einladung nicht gefunden.")
    if invite.invited_user_id != user_id:
        raise HTTPException(403, "Diese Einladung ist nicht an Sie gerichtet.")
    if invite.status != InviteStatus.PENDING.value:
        raise HTTPException(
            422, f"Die Einladung ist nicht mehr offen (Status: {invite.status})."
        )
    return invite


def _mark_invite_notification_read(invite: ChecklistInvite, db: Session) -> None:
    """Markiert die zur Einladung gehoerende In-App-Notification als gelesen.

    Verknuepfung ueber den Link, der die invite_id enthaelt — robust auch ohne
    Fremdschluessel zwischen Notification und Invite."""
    link_fragment = f"invite={invite.id}"
    (
        db.query(Notification)
        .filter(
            Notification.user_id == invite.invited_user_id,
            Notification.kind == "checklist_invite",
            Notification.read_at.is_(None),
            Notification.link.like(f"%{link_fragment}%"),
        )
        .update({Notification.read_at: _utcnow()}, synchronize_session=False)
    )


@router.post("/invites/{invite_id}/accept", response_model=MemberOut)
def accept_invite(invite_id: str, request: Request, db: Session = Depends(get_db)):
    """Nimmt eine Einladung an (nur der eingeladene Nutzer).

    Legt eine ChecklistMember-Mitgliedschaft mit der Rolle aus der Einladung an,
    setzt die Einladung auf accepted (+responded_at) und markiert die zugehoerige
    Notification als gelesen."""
    session = require_session(request)
    user_id = _session_user_id(session)
    invite = _load_own_invite(invite_id, user_id, db)

    # Falls inzwischen bereits Mitglied: Einladung trotzdem schliessen.
    existing = _get_member(invite.template_id, user_id, db)
    if existing:
        invite.status = InviteStatus.ACCEPTED.value
        invite.responded_at = _utcnow()
        _mark_invite_notification_read(invite, db)
        db.commit()
        regs = _load_registrations({user_id}, db)
        return _member_out(existing, regs)

    member = ChecklistMember(
        id=str(uuid.uuid4()),
        template_id=invite.template_id,
        user_id=user_id,
        role=invite.role,
        invited_by_id=invite.invited_by_id,
    )
    db.add(member)
    invite.status = InviteStatus.ACCEPTED.value
    invite.responded_at = _utcnow()
    _mark_invite_notification_read(invite, db)
    _audit(
        db, actor_user_id=user_id, action="checklist_invite_accepted",
        target_id=invite.template_id,
        metadata={"invite_id": invite_id, "role": invite.role},
    )
    db.commit()
    db.refresh(member)
    log.info(
        "Checklisten-Einladung %s angenommen durch %s (Template %s)",
        invite_id, user_id, invite.template_id,
    )
    regs = _load_registrations({user_id}, db)
    return _member_out(member, regs)


@router.post("/invites/{invite_id}/decline", response_model=InviteOut)
def decline_invite(invite_id: str, request: Request, db: Session = Depends(get_db)):
    """Lehnt eine Einladung ab (nur der eingeladene Nutzer) — status=declined.

    Markiert die zugehoerige Notification als gelesen."""
    session = require_session(request)
    user_id = _session_user_id(session)
    invite = _load_own_invite(invite_id, user_id, db)

    invite.status = InviteStatus.DECLINED.value
    invite.responded_at = _utcnow()
    _mark_invite_notification_read(invite, db)
    _audit(
        db, actor_user_id=user_id, action="checklist_invite_declined",
        target_id=invite.template_id,
        metadata={"invite_id": invite_id},
    )
    db.commit()
    db.refresh(invite)
    log.info("Checklisten-Einladung %s abgelehnt durch %s", invite_id, user_id)
    regs = _load_registrations({user_id, invite.invited_by_id}, db)
    return _invite_out(invite, regs)


# ── Knoten: Baum + Liste ──────────────────────────────────────────────────────

def _sort_key(node: ChecklistTemplateNode) -> tuple:
    """Sortierung: HINT-Knoten am Ende ihrer Geschwister-Ebene, sonst nach
    sort_order. So erscheint ein HINT direkt unterhalb seiner Frage, wenn er
    als Geschwister mit hoeherem sort_order modelliert ist; HINT-Kinder einer
    Frage sortieren ohnehin innerhalb des children-Arrays der Frage."""
    is_hint = 1 if (node.node_type or "").upper() == "HINT" else 0
    return (node.sort_order or 0, is_hint, node.created_at or datetime.min)


def _build_tree(nodes: list[ChecklistTemplateNode]) -> list[NodeTreeOut]:
    """Baut aus einer flachen Knotenliste den verschachtelten Baum.

    Geordnet nach parent_id + sort_order; HINT-Knoten erscheinen hinter ihrer
    Frage auf derselben Ebene. Knoten mit unbekanntem/fehlendem parent_id
    werden als Wurzelknoten behandelt (robuste Ausgabe bei verwaisten Kanten).
    """
    children_map: dict[str | None, list[ChecklistTemplateNode]] = {}
    known_ids = {n.id for n in nodes}
    for node in nodes:
        parent = node.parent_id if node.parent_id in known_ids else None
        children_map.setdefault(parent, []).append(node)

    def to_out(node: ChecklistTemplateNode) -> NodeTreeOut:
        out = NodeTreeOut.model_validate(node)
        kids = sorted(children_map.get(node.id, []), key=_sort_key)
        out.children = [to_out(k) for k in kids]
        return out

    roots = sorted(children_map.get(None, []), key=_sort_key)
    return [to_out(r) for r in roots]


@router.get("/{template_id}/tree", response_model=list[NodeTreeOut])
def get_tree(template_id: str, request: Request, db: Session = Depends(get_db)):
    """Liefert den vollstaendigen Knotenbaum als verschachtelte Struktur."""
    session = require_session(request)
    user_id = _session_user_id(session)

    tpl = db.query(ChecklistTemplate).filter(ChecklistTemplate.id == template_id).first()
    if not tpl:
        raise HTTPException(404, "Checklisten-Template nicht gefunden.")
    member = _get_member(template_id, user_id, db)
    if not member and tpl.status != TemplateStatus.PUBLISHED.value:
        raise HTTPException(403, "Kein Zugriff auf dieses Checklisten-Template.")

    nodes = (
        db.query(ChecklistTemplateNode)
        .filter(ChecklistTemplateNode.template_id == template_id)
        .all()
    )
    return _build_tree(nodes)


@router.get("/{template_id}/nodes", response_model=list[NodeOut])
def list_nodes(template_id: str, request: Request, db: Session = Depends(get_db)):
    """Flache, sortierte Liste aller Knoten eines Templates."""
    session = require_session(request)
    user_id = _session_user_id(session)
    tpl = db.query(ChecklistTemplate).filter(ChecklistTemplate.id == template_id).first()
    if not tpl:
        raise HTTPException(404, "Checklisten-Template nicht gefunden.")
    member = _get_member(template_id, user_id, db)
    if not member and tpl.status != TemplateStatus.PUBLISHED.value:
        raise HTTPException(403, "Kein Zugriff auf dieses Checklisten-Template.")
    nodes = (
        db.query(ChecklistTemplateNode)
        .filter(ChecklistTemplateNode.template_id == template_id)
        .order_by(ChecklistTemplateNode.sort_order)
        .all()
    )
    return [NodeOut.model_validate(n) for n in nodes]


def _get_node(template_id: str, node_id: str, db: Session) -> ChecklistTemplateNode:
    node = (
        db.query(ChecklistTemplateNode)
        .filter(
            ChecklistTemplateNode.id == node_id,
            ChecklistTemplateNode.template_id == template_id,
        )
        .first()
    )
    if not node:
        raise HTTPException(404, "Knoten nicht gefunden.")
    return node


def _validate_node_references(
    template_id: str, answer_set_id: str | None, category_id: str | None, db: Session,
) -> None:
    """Stellt sicher, dass referenziertes Antwortset/Kategorie zum Template passen.

    Verhindert IDOR ueber Fremd-IDs: ein ``answer_set_id`` muss entweder zum
    selben Template gehoeren ODER ein globales Set sein (``template_id IS NULL``);
    ein ``category_id`` muss zum selben Template gehoeren. Andernfalls 422."""
    if answer_set_id:
        aset = (
            db.query(ChecklistAnswerSet)
            .filter(ChecklistAnswerSet.id == answer_set_id)
            .first()
        )
        if not aset or (aset.template_id is not None and aset.template_id != template_id):
            raise HTTPException(
                422, "Das zugewiesene Antwortset gehoert nicht zu dieser Checkliste."
            )
    if category_id:
        cat = (
            db.query(ChecklistQuestionCategory)
            .filter(
                ChecklistQuestionCategory.id == category_id,
                ChecklistQuestionCategory.template_id == template_id,
            )
            .first()
        )
        if not cat:
            raise HTTPException(
                422, "Die zugewiesene Kategorie gehoert nicht zu dieser Checkliste."
            )


# ── Knoten-CRUD ───────────────────────────────────────────────────────────────

@router.post("/{template_id}/nodes", response_model=NodeOut, status_code=201)
def create_node(
    template_id: str, data: NodeCreate, request: Request, db: Session = Depends(get_db),
):
    """Legt einen neuen Knoten an (mindestens editor) + Verlaufseintrag."""
    session = require_session(request)
    user_id = _session_user_id(session)
    _require_role(template_id, user_id, MemberRole.EDITOR, db)

    # parent_id (falls gesetzt) muss zum selben Template gehoeren.
    if data.parent_id:
        _get_node(template_id, data.parent_id, db)
    # Antwortset/Kategorie muessen zum Template passen (kein Fremd-Bezug).
    _validate_node_references(template_id, data.answer_set_id, data.category_id, db)

    node = ChecklistTemplateNode(
        id=str(uuid.uuid4()),
        template_id=template_id,
        parent_id=data.parent_id,
        node_type=data.node_type.value,
        branch=data.branch.value if data.branch else None,
        ja_label=data.ja_label,
        nein_label=data.nein_label,
        decision_parent_id=data.decision_parent_id,
        sort_order=data.sort_order,
        title=data.title,
        public_remark=data.public_remark,
        remark_snippets_json=data.remark_snippets_json,
        eingabetyp=data.eingabetyp,
        answer_type=data.answer_type.value if data.answer_type else None,
        answer_set_id=data.answer_set_id,
        category_id=data.category_id,
        legal_reference=data.legal_reference,
        relevant_documents_json=data.relevant_documents_json,
        is_header_field=data.is_header_field,
    )
    db.add(node)
    db.flush()
    _write_history(
        db=db, template_id=template_id, node_id=node.id,
        change_type=NodeChangeType.CREATED, changed_by_id=user_id,
        snapshot=_node_snapshot(node),
        new_parent_id=node.parent_id, new_position=node.sort_order,
    )
    db.commit()
    db.refresh(node)
    # Live-Update an verbundene SSE-Clients.
    _collab_broker.publish(template_id, {
        "type": "node_created", "user_id": user_id, "node": _node_event_payload(node),
    })
    return NodeOut.model_validate(node)


@router.put("/{template_id}/nodes/{node_id}", response_model=NodeOut)
def update_node(
    template_id: str, node_id: str, data: NodeUpdate,
    request: Request, db: Session = Depends(get_db),
):
    """Aendert einen Knoten. Reines public_remark-Update darf auch commenter,
    alles andere erfordert editor. Schreibt einen Verlaufseintrag mit Diff."""
    session = require_session(request)
    user_id = _session_user_id(session)

    payload = data.model_dump(exclude_unset=True)
    only_remark = set(payload.keys()) <= {"public_remark"}
    min_role = MemberRole.COMMENTER if only_remark else MemberRole.EDITOR
    _require_role(template_id, user_id, min_role, db)

    node = _get_node(template_id, node_id, db)
    before = _node_snapshot(node)

    # Enum-Werte zu Strings aufloesen, parent_id validieren.
    if "node_type" in payload and payload["node_type"] is not None:
        payload["node_type"] = payload["node_type"].value
    if "branch" in payload:
        payload["branch"] = payload["branch"].value if payload["branch"] else None
    if "answer_type" in payload:
        payload["answer_type"] = payload["answer_type"].value if payload["answer_type"] else None
    if payload.get("parent_id"):
        if payload["parent_id"] == node_id:
            raise HTTPException(422, "Ein Knoten kann nicht sein eigener Elternknoten sein.")
        _get_node(template_id, payload["parent_id"], db)
    # Geaenderte Antwortset-/Kategorie-Zuweisung muss zum Template passen.
    if "answer_set_id" in payload or "category_id" in payload:
        _validate_node_references(
            template_id,
            payload.get("answer_set_id", node.answer_set_id),
            payload.get("category_id", node.category_id),
            db,
        )

    for key, val in payload.items():
        setattr(node, key, val)
    db.flush()

    after = _node_snapshot(node)
    diff = _diff_fields(before, after)
    if diff:
        _write_history(
            db=db, template_id=template_id, node_id=node.id,
            change_type=NodeChangeType.UPDATED, changed_by_id=user_id,
            snapshot=after, changed_fields=diff,
        )
    db.commit()
    db.refresh(node)
    # Live-Update an verbundene SSE-Clients (nur wenn sich etwas geaendert hat).
    if diff:
        _collab_broker.publish(template_id, {
            "type": "node_updated", "user_id": user_id,
            "node": _node_event_payload(node), "changed_fields": list(diff.keys()),
        })
    return NodeOut.model_validate(node)


@router.delete("/{template_id}/nodes/{node_id}", status_code=204)
def delete_node(
    template_id: str, node_id: str, request: Request, db: Session = Depends(get_db),
):
    """Loescht einen Knoten (mindestens editor) + Verlaufseintrag.

    Cascade auf parent_id loescht Kindknoten in der DB; fuer diese werden hier
    keine separaten Verlaufseintraege geschrieben (Kaskaden-Loeschung)."""
    session = require_session(request)
    user_id = _session_user_id(session)
    _require_role(template_id, user_id, MemberRole.EDITOR, db)

    node = _get_node(template_id, node_id, db)
    snapshot = _node_snapshot(node)
    _write_history(
        db=db, template_id=template_id, node_id=node_id,
        change_type=NodeChangeType.DELETED, changed_by_id=user_id,
        snapshot=snapshot,
        old_parent_id=node.parent_id, old_position=node.sort_order,
    )
    db.delete(node)
    db.commit()
    # Live-Update an verbundene SSE-Clients.
    _collab_broker.publish(template_id, {
        "type": "node_deleted", "user_id": user_id, "node_id": node_id,
        "template_id": template_id,
    })


@router.post("/{template_id}/nodes/{node_id}/move", response_model=NodeOut)
def move_node(
    template_id: str, node_id: str, data: NodeMove,
    request: Request, db: Session = Depends(get_db),
):
    """Verschiebt einen Knoten (Reparent + Reorder) + Verlaufseintrag."""
    session = require_session(request)
    user_id = _session_user_id(session)
    _require_role(template_id, user_id, MemberRole.EDITOR, db)

    node = _get_node(template_id, node_id, db)

    # Zielelternknoten validieren + Zyklus verhindern.
    if data.parent_id:
        if data.parent_id == node_id:
            raise HTTPException(422, "Ein Knoten kann nicht sein eigener Elternknoten sein.")
        _get_node(template_id, data.parent_id, db)
        if _is_descendant(template_id, ancestor_id=node_id, candidate_id=data.parent_id, db=db):
            raise HTTPException(422, "Zielknoten ist ein Nachfahre — wuerde einen Zyklus erzeugen.")

    old_parent = node.parent_id
    old_position = node.sort_order
    node.parent_id = data.parent_id
    node.sort_order = data.sort_order
    db.flush()

    _write_history(
        db=db, template_id=template_id, node_id=node_id,
        change_type=NodeChangeType.MOVED, changed_by_id=user_id,
        snapshot=_node_snapshot(node),
        old_parent_id=old_parent, new_parent_id=node.parent_id,
        old_position=old_position, new_position=node.sort_order,
    )
    db.commit()
    db.refresh(node)
    # Live-Update an verbundene SSE-Clients.
    _collab_broker.publish(template_id, {
        "type": "node_moved", "user_id": user_id, "node": _node_event_payload(node),
        "old_parent_id": old_parent, "new_parent_id": node.parent_id,
    })
    return NodeOut.model_validate(node)


def _is_descendant(
    template_id: str, ancestor_id: str, candidate_id: str, db: Session,
) -> bool:
    """Prueft, ob ``candidate_id`` ein Nachfahre von ``ancestor_id`` ist."""
    nodes = (
        db.query(ChecklistTemplateNode.id, ChecklistTemplateNode.parent_id)
        .filter(ChecklistTemplateNode.template_id == template_id)
        .all()
    )
    parent_of = {row[0]: row[1] for row in nodes}
    cur = parent_of.get(candidate_id)
    seen = set()
    while cur and cur not in seen:
        if cur == ancestor_id:
            return True
        seen.add(cur)
        cur = parent_of.get(cur)
    return False


# ── Antwortsets (checklistenspezifisch) ───────────────────────────────────────
# Hinweis: die globalen /answer-sets-Routen sind weiter oben (vor /{template_id})
# definiert, damit das literale Segment "answer-sets" nicht als template_id matcht.

@router.get("/{template_id}/answer-sets", response_model=list[AnswerSetOut])
def list_template_answer_sets(
    template_id: str, request: Request, db: Session = Depends(get_db),
):
    """Checklistenspezifische Antwortsets eines Templates (mindestens viewer)."""
    session = require_session(request)
    user_id = _session_user_id(session)
    _require_role(template_id, user_id, MemberRole.VIEWER, db)
    sets = (
        db.query(ChecklistAnswerSet)
        .filter(ChecklistAnswerSet.template_id == template_id)
        .order_by(ChecklistAnswerSet.sort_order, ChecklistAnswerSet.name)
        .all()
    )
    return [AnswerSetOut.model_validate(s) for s in sets]


@router.post("/{template_id}/answer-sets", response_model=AnswerSetOut, status_code=201)
def create_template_answer_set(
    template_id: str, data: AnswerSetCreate, request: Request, db: Session = Depends(get_db),
):
    """Legt ein checklistenspezifisches Antwortset an (mindestens editor)."""
    session = require_session(request)
    user_id = _session_user_id(session)
    _require_role(template_id, user_id, MemberRole.EDITOR, db)
    return _create_answer_set(template_id, data, db)


def _create_answer_set(
    template_id: str | None, data: AnswerSetCreate, db: Session,
) -> AnswerSetOut:
    aset = ChecklistAnswerSet(
        id=str(uuid.uuid4()),
        template_id=template_id,
        name=data.name,
        description=data.description,
        sort_order=data.sort_order,
    )
    db.add(aset)
    db.flush()
    for i, opt in enumerate(data.options or []):
        db.add(ChecklistAnswerOption(
            id=str(uuid.uuid4()),
            answer_set_id=aset.id,
            name=opt.name,
            sort_order=opt.sort_order if opt.sort_order else i,
            is_standard=opt.is_standard,
            is_entfaellt=opt.is_entfaellt,
            value_number=opt.value_number,
            threshold=opt.threshold,
            bemerkung=opt.bemerkung,
        ))
    db.commit()
    db.refresh(aset)
    return AnswerSetOut.model_validate(aset)


def _load_answer_set(answer_set_id: str, db: Session) -> ChecklistAnswerSet:
    aset = (
        db.query(ChecklistAnswerSet)
        .filter(ChecklistAnswerSet.id == answer_set_id)
        .first()
    )
    if not aset:
        raise HTTPException(404, "Antwortset nicht gefunden.")
    return aset


def _authorize_answer_set_write(
    aset: ChecklistAnswerSet, session: dict, db: Session,
) -> None:
    """Autorisiert eine schreibende Aenderung an einem Antwortset.

    Templategebundene Antwortsets erfordern die editor-Rolle am zugehoerigen
    Template. Globale Antwortsets (``template_id IS NULL``) sind eine GETEILTE
    Bibliothek, von der andere Checklisten abhaengen — sie duerfen daher nur von
    Moderatoren/Admins veraendert/geloescht werden (Least Privilege; verhindert,
    dass ein beliebiger Teilnehmer geteilte Bibliotheks-Eintraege manipuliert
    oder loescht). Lesen und Anlegen bleibt fuer alle Angemeldeten erlaubt.
    """
    user_id = _session_user_id(session)
    if aset.template_id is not None:
        _require_role(aset.template_id, user_id, MemberRole.EDITOR, db)
        return
    role = str(session.get("role") or "").lower()
    email = str(session.get("email") or "").lower()
    if role in ("moderator", "admin") or email in MODERATOR_EMAILS or email in ADMIN_EMAILS:
        return
    raise HTTPException(
        403,
        "Globale Antwortsets gehoeren zur geteilten Bibliothek und koennen nur "
        "von Moderatoren/Admins geaendert oder geloescht werden.",
    )


@router.put("/answer-sets/{answer_set_id}", response_model=AnswerSetOut)
def update_answer_set(
    answer_set_id: str, data: AnswerSetUpdate, request: Request, db: Session = Depends(get_db),
):
    """Aendert Metadaten eines Antwortsets (global oder templategebunden)."""
    session = require_session(request)
    _session_user_id(session)
    aset = _load_answer_set(answer_set_id, db)
    _authorize_answer_set_write(aset, session, db)
    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(aset, key, val)
    db.commit()
    db.refresh(aset)
    return AnswerSetOut.model_validate(aset)


@router.delete("/answer-sets/{answer_set_id}", status_code=204)
def delete_answer_set(
    answer_set_id: str, request: Request, db: Session = Depends(get_db),
):
    """Loescht ein Antwortset samt Optionen."""
    session = require_session(request)
    _session_user_id(session)
    aset = _load_answer_set(answer_set_id, db)
    _authorize_answer_set_write(aset, session, db)
    db.delete(aset)
    db.commit()


@router.post(
    "/answer-sets/{answer_set_id}/options",
    response_model=AnswerOptionOut, status_code=201,
)
def add_answer_option(
    answer_set_id: str, data: AnswerOptionCreate, request: Request, db: Session = Depends(get_db),
):
    """Fuegt einem Antwortset eine Option hinzu."""
    session = require_session(request)
    _session_user_id(session)
    aset = _load_answer_set(answer_set_id, db)
    _authorize_answer_set_write(aset, session, db)
    opt = ChecklistAnswerOption(
        id=str(uuid.uuid4()),
        answer_set_id=answer_set_id,
        name=data.name,
        sort_order=data.sort_order,
        is_standard=data.is_standard,
        is_entfaellt=data.is_entfaellt,
        value_number=data.value_number,
        threshold=data.threshold,
        bemerkung=data.bemerkung,
    )
    db.add(opt)
    db.commit()
    db.refresh(opt)
    return AnswerOptionOut.model_validate(opt)


def _load_answer_option(option_id: str, db: Session) -> ChecklistAnswerOption:
    opt = (
        db.query(ChecklistAnswerOption)
        .filter(ChecklistAnswerOption.id == option_id)
        .first()
    )
    if not opt:
        raise HTTPException(404, "Antwortoption nicht gefunden.")
    return opt


@router.put("/answer-options/{option_id}", response_model=AnswerOptionOut)
def update_answer_option(
    option_id: str, data: AnswerOptionUpdate, request: Request, db: Session = Depends(get_db),
):
    """Aendert eine Antwortoption."""
    session = require_session(request)
    _session_user_id(session)
    opt = _load_answer_option(option_id, db)
    aset = _load_answer_set(opt.answer_set_id, db)
    _authorize_answer_set_write(aset, session, db)
    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(opt, key, val)
    db.commit()
    db.refresh(opt)
    return AnswerOptionOut.model_validate(opt)


@router.delete("/answer-options/{option_id}", status_code=204)
def delete_answer_option(
    option_id: str, request: Request, db: Session = Depends(get_db),
):
    """Loescht eine Antwortoption."""
    session = require_session(request)
    _session_user_id(session)
    opt = _load_answer_option(option_id, db)
    aset = _load_answer_set(opt.answer_set_id, db)
    _authorize_answer_set_write(aset, session, db)
    db.delete(opt)
    db.commit()


# ── Kategorien (je Template) ──────────────────────────────────────────────────

@router.get("/{template_id}/categories", response_model=list[CategoryOut])
def list_categories(template_id: str, request: Request, db: Session = Depends(get_db)):
    """Listet die Fragenkategorien eines Templates (mindestens viewer)."""
    session = require_session(request)
    user_id = _session_user_id(session)
    _require_role(template_id, user_id, MemberRole.VIEWER, db)
    cats = (
        db.query(ChecklistQuestionCategory)
        .filter(ChecklistQuestionCategory.template_id == template_id)
        .order_by(ChecklistQuestionCategory.sort_order, ChecklistQuestionCategory.name)
        .all()
    )
    return [CategoryOut.model_validate(c) for c in cats]


@router.post("/{template_id}/categories", response_model=CategoryOut, status_code=201)
def create_category(
    template_id: str, data: CategoryCreate, request: Request, db: Session = Depends(get_db),
):
    """Legt eine Fragenkategorie an (mindestens editor)."""
    session = require_session(request)
    user_id = _session_user_id(session)
    _require_role(template_id, user_id, MemberRole.EDITOR, db)
    cat = ChecklistQuestionCategory(
        id=str(uuid.uuid4()),
        template_id=template_id,
        name=data.name,
        sort_order=data.sort_order,
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return CategoryOut.model_validate(cat)


@router.put("/{template_id}/categories/{category_id}", response_model=CategoryOut)
def update_category(
    template_id: str, category_id: str, data: CategoryUpdate,
    request: Request, db: Session = Depends(get_db),
):
    """Aendert eine Fragenkategorie (mindestens editor)."""
    session = require_session(request)
    user_id = _session_user_id(session)
    _require_role(template_id, user_id, MemberRole.EDITOR, db)
    cat = (
        db.query(ChecklistQuestionCategory)
        .filter(
            ChecklistQuestionCategory.id == category_id,
            ChecklistQuestionCategory.template_id == template_id,
        )
        .first()
    )
    if not cat:
        raise HTTPException(404, "Kategorie nicht gefunden.")
    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(cat, key, val)
    db.commit()
    db.refresh(cat)
    return CategoryOut.model_validate(cat)


@router.delete("/{template_id}/categories/{category_id}", status_code=204)
def delete_category(
    template_id: str, category_id: str, request: Request, db: Session = Depends(get_db),
):
    """Loescht eine Fragenkategorie (mindestens editor)."""
    session = require_session(request)
    user_id = _session_user_id(session)
    _require_role(template_id, user_id, MemberRole.EDITOR, db)
    cat = (
        db.query(ChecklistQuestionCategory)
        .filter(
            ChecklistQuestionCategory.id == category_id,
            ChecklistQuestionCategory.template_id == template_id,
        )
        .first()
    )
    if not cat:
        raise HTTPException(404, "Kategorie nicht gefunden.")
    db.delete(cat)
    db.commit()
