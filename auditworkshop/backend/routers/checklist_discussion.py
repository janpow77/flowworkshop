"""
flowworkshop · routers/checklist_discussion.py

Team-Diskussion, Knoten-Status, Unread-Tracking und Referenz-Dokumente fuer den
KOM-Checklisten-Designer.

Dieser Router ergaenzt die Kollaborations-Bausteine (Presence/Locking in
``checklist_collab.py``, CRUD in ``checklist_templates.py``) um die fachliche
Team-Abstimmung an einem einzelnen Knoten:

* **Knoten-Status** (pending/in_progress/resolved) als Workflow-Markierung.
* **Kommentar-Threads** je Knoten mit genau einer Antwort-Ebene
  (``parent_comment_id``), Soft-Delete und Autor-Anzeige.
* **Unread-Tracking** — pro Nutzer wird gezaehlt, welche Kommentare er noch
  nicht gelesen hat (fehlender ``ChecklistNoteRead``-Eintrag = ungelesen).
* **Referenz-Dokumente** je Knoten (Belegverweise mit Name/Pfad/Zitat).

Jede schreibende Aktion verteilt ein Live-Event ueber den prozesslokalen
SSE-Broker (``services.checklist_events.broker``), damit andere Bearbeiter den
neuen Stand sofort sehen. Optionale In-App-Hinweise (``Notification``,
Tabelle ``workshop_notifications``) informieren die uebrigen Mitglieder ueber
neue Diskussionsbeitraege — ganz ohne Mailversand.

Rechte werden bewusst mit einem LOKALEN ``_require_role``-Helfer geprueft (kein
Import aus ``checklist_templates.py``), um die Kopplung gering zu halten. Der
ganze Router haengt an ``require_session`` (Header-Token), sodass jede
Anfrage einen angemeldeten Nutzer voraussetzt.

Single-Worker-Limitierung der Live-Events: siehe ``services/checklist_events.py``.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models.automation import Notification
from models.checklist_template import (
    ChecklistMember,
    ChecklistNodeComment,
    ChecklistNodeReferenceDoc,
    ChecklistNoteRead,
    ChecklistTemplate,
    ChecklistTemplateNode,
    MemberRole,
    TemplateStatus,
)
from models.registration import Registration
from routers.auth import require_session
from services.checklist_events import broker

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/checklist-templates",
    tags=["checklist-discussion"],
    dependencies=[Depends(require_session)],
)


# ── Rollen-Rangfolge (lokal, NICHT aus checklist_templates importiert) ────────
# Hoeherer Rang = mehr Rechte. viewer < commenter < editor < owner.
_ROLE_RANK = {
    MemberRole.VIEWER.value: 1,
    MemberRole.COMMENTER.value: 2,
    MemberRole.EDITOR.value: 3,
    MemberRole.OWNER.value: 4,
}

# Erlaubte Knoten-Status-Werte (Team-Workflow).
_NODE_STATUS_VALUES = {"pending", "in_progress", "resolved"}


def _utcnow() -> datetime:
    """Naive UTC-Zeit (konsistent mit den tz-losen DateTime-Spalten)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _session_user_id(session: dict) -> str:
    """Liest die Nutzerkennung aus der Session (oder 401)."""
    uid = session.get("user_id")
    if not uid:
        raise HTTPException(401, "Sitzung ohne Nutzerkennung.")
    return uid


# ── Helfer: Rechtepruefung (lokal) ────────────────────────────────────────────

def _get_template(template_id: str, db: Session) -> ChecklistTemplate:
    """Laedt ein Template oder wirft 404."""
    tpl = (
        db.query(ChecklistTemplate)
        .filter(ChecklistTemplate.id == template_id)
        .first()
    )
    if not tpl:
        raise HTTPException(404, "Checklisten-Template nicht gefunden.")
    return tpl


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
    db: Session, template_id: str, user_id: str, min_role: MemberRole,
) -> ChecklistMember:
    """Stellt sicher, dass ``user_id`` am Template mindestens ``min_role`` hat.

    Wirft 404, wenn das Template fehlt, 403, wenn der Nutzer kein Mitglied ist
    oder seine Rolle nicht ausreicht. Gibt die Mitgliedschaft zurueck.

    Bewusst LOKAL gehalten (keine Abhaengigkeit zu ``checklist_templates``);
    Signatur ``(db, template_id, user_id, min_role)`` wie vom Modul vorgesehen.
    """
    _get_template(template_id, db)
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


def _require_read(db: Session, template_id: str, user_id: str) -> ChecklistTemplate:
    """Lesezugriff: erlaubt fuer Mitglieder ODER veroeffentlichte Templates.

    Liefert das Template zurueck (404, wenn es nicht existiert)."""
    tpl = _get_template(template_id, db)
    if tpl.status == TemplateStatus.PUBLISHED.value:
        return tpl
    if _get_member(template_id, user_id, db):
        return tpl
    raise HTTPException(403, "Kein Zugriff auf dieses Checklisten-Template.")


def _get_node(template_id: str, node_id: str, db: Session) -> ChecklistTemplateNode:
    """Laedt einen Knoten des Templates oder wirft 404."""
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


def _full_name(reg: Registration | None) -> str | None:
    """Zusammengesetzter Anzeigename eines Nutzers (oder None)."""
    if not reg:
        return None
    name = f"{reg.first_name or ''} {reg.last_name or ''}".strip()
    return name or None


def _load_names(user_ids: set[str], db: Session) -> dict[str, str | None]:
    """Map Nutzerkennung → Anzeigename fuer eine Menge von IDs.

    Fehlende/geloeschte Nutzer fehlen schlicht in der Map."""
    ids = {uid for uid in user_ids if uid}
    if not ids:
        return {}
    rows = db.query(Registration).filter(Registration.id.in_(ids)).all()
    return {r.id: _full_name(r) for r in rows}


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic-Schemas (lokal in dieser Datei gehalten)
# ─────────────────────────────────────────────────────────────────────────────

class NodeStatusUpdate(BaseModel):
    """Eingabe fuer das Setzen des Knoten-Status."""
    status: str = Field(..., description="pending | in_progress | resolved")


class NodeStatusOut(BaseModel):
    node_id: str
    status: str


# Obergrenze fuer Diskussionsbeitraege — verhindert unbeschraenkten Speicher-
# verbrauch (Storage-DoS) durch riesige Texte. 20.000 Zeichen sind fuer eine
# fachliche Abstimmung mehr als ausreichend.
_MAX_COMMENT_LEN = 20_000
_MAX_REF_TEXT_LEN = 20_000


class CommentCreate(BaseModel):
    """Eingabe fuer einen neuen Kommentar (optional als Antwort)."""
    message: str = Field(..., min_length=1, max_length=_MAX_COMMENT_LEN)
    parent_comment_id: str | None = Field(default=None, max_length=36)


class CommentUpdate(BaseModel):
    """Eingabe fuer die Bearbeitung eines Kommentars."""
    message: str = Field(..., min_length=1, max_length=_MAX_COMMENT_LEN)


class CommentOut(BaseModel):
    """Serialisierter Kommentar inkl. Antworten (eine Ebene)."""
    id: str
    template_id: str
    node_id: str
    author_id: str | None = None
    author_name: str | None = None
    message: str
    parent_comment_id: str | None = None
    is_deleted: bool = False
    created_at: datetime | None = None
    edited_at: datetime | None = None
    replies: list["CommentOut"] = Field(default_factory=list)


class RefDocCreate(BaseModel):
    """Eingabe fuer ein neues Referenz-Dokument."""
    document_name: str = Field(..., min_length=1, max_length=255)
    document_path: str | None = Field(default=None, max_length=500)
    reference_text: str | None = Field(default=None, max_length=_MAX_REF_TEXT_LEN)


class RefDocOut(BaseModel):
    id: str
    template_id: str
    node_id: str
    document_name: str
    document_path: str | None = None
    reference_text: str | None = None
    created_at: datetime | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Knoten-Status
# ─────────────────────────────────────────────────────────────────────────────

@router.put("/{template_id}/nodes/{node_id}/status", response_model=NodeStatusOut)
def set_node_status(
    template_id: str, node_id: str, data: NodeStatusUpdate,
    request: Request, db: Session = Depends(get_db),
):
    """Setzt den Workflow-Status eines Knotens (mindestens editor).

    Erlaubte Werte: pending/in_progress/resolved. Verteilt ein
    ``node_updated``-Live-Event mit dem geaenderten Feld ``status``.
    """
    session = require_session(request)
    user_id = _session_user_id(session)
    _require_role(db, template_id, user_id, MemberRole.EDITOR)

    status = (data.status or "").strip()
    if status not in _NODE_STATUS_VALUES:
        raise HTTPException(
            422,
            "Ungueltiger Status — erlaubt: "
            + ", ".join(sorted(_NODE_STATUS_VALUES)) + ".",
        )

    node = _get_node(template_id, node_id, db)
    node.status = status
    db.commit()
    db.refresh(node)

    broker.publish(template_id, {
        "type": "node_updated", "user_id": user_id,
        "node": {"id": node.id, "template_id": template_id, "status": node.status},
        "changed_fields": ["status"],
    })
    return NodeStatusOut(node_id=node.id, status=node.status)


# ─────────────────────────────────────────────────────────────────────────────
# Team-Diskussion (Kommentar-Threads)
# ─────────────────────────────────────────────────────────────────────────────

def _comment_out(
    c: ChecklistNodeComment, names: dict[str, str | None],
) -> CommentOut:
    """Serialisiert einen Kommentar; geloeschte werden maskiert.

    Bei Soft-Delete (``deleted_at``) bleibt der Beitrag als Platzhalter im
    Thread erhalten (Threading-Struktur bleibt lesbar), die Nachricht wird
    aber durch einen Hinweis ersetzt und der Autor ausgeblendet.
    """
    deleted = c.deleted_at is not None
    return CommentOut(
        id=c.id,
        template_id=c.template_id,
        node_id=c.node_id,
        author_id=None if deleted else c.author_id,
        author_name=None if deleted else names.get(c.author_id or ""),
        message="[gelöscht]" if deleted else c.message,
        parent_comment_id=c.parent_comment_id,
        is_deleted=deleted,
        created_at=c.created_at,
        edited_at=None if deleted else c.edited_at,
        replies=[],
    )


@router.get("/{template_id}/nodes/{node_id}/comments", response_model=list[CommentOut])
def list_comments(
    template_id: str, node_id: str,
    request: Request, db: Session = Depends(get_db),
):
    """Liefert den Diskussions-Thread eines Knotens.

    Aufbau: Parent-Kommentare in zeitlicher Reihenfolge, je mit ihren
    Antworten (eine Ebene) verschachtelt. Geloeschte Beitraege bleiben als
    Platzhalter erhalten, damit Antworten nicht den Bezug verlieren.
    """
    session = require_session(request)
    user_id = _session_user_id(session)
    _require_read(db, template_id, user_id)
    _get_node(template_id, node_id, db)

    rows = (
        db.query(ChecklistNodeComment)
        .filter(
            ChecklistNodeComment.template_id == template_id,
            ChecklistNodeComment.node_id == node_id,
        )
        .order_by(ChecklistNodeComment.created_at.asc())
        .all()
    )

    names = _load_names({r.author_id for r in rows if r.author_id}, db)

    # Erst alle Kommentare serialisieren, dann Antworten den Eltern zuordnen.
    by_id: dict[str, CommentOut] = {r.id: _comment_out(r, names) for r in rows}
    roots: list[CommentOut] = []
    for r in rows:
        out = by_id[r.id]
        parent_id = r.parent_comment_id
        if parent_id and parent_id in by_id:
            by_id[parent_id].replies.append(out)
        else:
            # Parent-Kommentar (oder verwaister Beitrag) → Wurzel-Ebene.
            roots.append(out)
    return roots


@router.post("/{template_id}/nodes/{node_id}/comments", response_model=CommentOut)
def create_comment(
    template_id: str, node_id: str, data: CommentCreate,
    request: Request, db: Session = Depends(get_db),
):
    """Legt einen Diskussionsbeitrag an (mindestens commenter).

    Antworten (``parent_comment_id``) sind nur eine Ebene tief erlaubt — wird
    auf einen Beitrag geantwortet, der selbst eine Antwort ist, wird der
    Bezug auf dessen Eltern-Kommentar umgehaengt. Verteilt ein
    ``comment_added``-Live-Event und benachrichtigt die uebrigen Mitglieder.
    """
    session = require_session(request)
    user_id = _session_user_id(session)
    _require_role(db, template_id, user_id, MemberRole.COMMENTER)
    _get_node(template_id, node_id, db)

    message = (data.message or "").strip()
    if not message:
        raise HTTPException(422, "Kommentartext darf nicht leer sein.")

    parent_id = data.parent_comment_id
    if parent_id:
        parent = (
            db.query(ChecklistNodeComment)
            .filter(
                ChecklistNodeComment.id == parent_id,
                ChecklistNodeComment.template_id == template_id,
                ChecklistNodeComment.node_id == node_id,
            )
            .first()
        )
        if not parent:
            raise HTTPException(404, "Antwort-Bezug (parent_comment_id) nicht gefunden.")
        # Nur eine Antwort-Ebene: auf den Wurzel-Kommentar umhaengen.
        if parent.parent_comment_id:
            parent_id = parent.parent_comment_id

    comment = ChecklistNodeComment(
        id=str(uuid.uuid4()),
        template_id=template_id,
        node_id=node_id,
        author_id=user_id,
        message=message,
        parent_comment_id=parent_id,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)

    names = _load_names({user_id}, db)
    out = _comment_out(comment, names)

    broker.publish(template_id, {
        "type": "comment_added", "user_id": user_id,
        "node_id": node_id, "template_id": template_id,
        "comment": out.model_dump(mode="json"),
    })

    # In-App-Hinweis an die uebrigen Mitglieder (kein Mailversand).
    _notify_members(
        db, template_id=template_id, node_id=node_id,
        author_id=user_id, author_name=names.get(user_id), message=message,
    )

    return out


def _notify_members(
    db: Session, *, template_id: str, node_id: str,
    author_id: str, author_name: str | None, message: str,
) -> None:
    """Legt fuer alle Mitglieder ausser dem Autor eine Notification an.

    Best-effort: Fehler hierbei duerfen den Kommentar nicht scheitern lassen,
    daher in eigener, fehlertoleranter Transaktion.
    """
    try:
        members = (
            db.query(ChecklistMember.user_id)
            .filter(ChecklistMember.template_id == template_id)
            .all()
        )
        recipients = {m[0] for m in members if m[0] and m[0] != author_id}
        if not recipients:
            return
        excerpt = (message[:140] + "…") if len(message) > 140 else message
        who = author_name or "Ein Teammitglied"
        link = f"/checklist-templates/{template_id}?node={node_id}"
        for uid in recipients:
            db.add(Notification(
                user_id=uid,
                kind="forum_reply",
                title="Neuer Diskussionsbeitrag in einer Checkliste",
                body=f"{who}: {excerpt}",
                link=link,
            ))
        db.commit()
    except Exception:  # noqa: BLE001 — Benachrichtigung ist nicht kritisch
        db.rollback()
        log.warning("Notification-Versand fuer Kommentar fehlgeschlagen.", exc_info=True)


@router.put("/{template_id}/comments/{comment_id}", response_model=CommentOut)
def edit_comment(
    template_id: str, comment_id: str, data: CommentUpdate,
    request: Request, db: Session = Depends(get_db),
):
    """Bearbeitet einen eigenen Kommentar (nur der Autor).

    Setzt ``edited_at``. Geloeschte Kommentare lassen sich nicht bearbeiten.
    Verteilt ein ``comment_updated``-Live-Event.
    """
    session = require_session(request)
    user_id = _session_user_id(session)
    # Lesezugriff genuegt fuer die Auflage; die eigentliche Pruefung ist Autor.
    _require_read(db, template_id, user_id)

    comment = (
        db.query(ChecklistNodeComment)
        .filter(
            ChecklistNodeComment.id == comment_id,
            ChecklistNodeComment.template_id == template_id,
        )
        .first()
    )
    if not comment:
        raise HTTPException(404, "Kommentar nicht gefunden.")
    if comment.deleted_at is not None:
        raise HTTPException(409, "Ein gelöschter Kommentar kann nicht bearbeitet werden.")
    if comment.author_id != user_id:
        raise HTTPException(403, "Nur der Autor darf diesen Kommentar bearbeiten.")

    message = (data.message or "").strip()
    if not message:
        raise HTTPException(422, "Kommentartext darf nicht leer sein.")

    comment.message = message
    comment.edited_at = _utcnow()
    db.commit()
    db.refresh(comment)

    names = _load_names({comment.author_id} if comment.author_id else set(), db)
    out = _comment_out(comment, names)
    broker.publish(template_id, {
        "type": "comment_updated", "user_id": user_id,
        "node_id": comment.node_id, "template_id": template_id,
        "comment": out.model_dump(mode="json"),
    })
    return out


@router.delete("/{template_id}/comments/{comment_id}", status_code=204)
def delete_comment(
    template_id: str, comment_id: str,
    request: Request, db: Session = Depends(get_db),
):
    """Loescht einen Kommentar weich (Autor ODER owner).

    Soft-Delete via ``deleted_at`` — der Kommentar bleibt als Platzhalter im
    Thread. Direkte Antworten (eine Ebene tiefer) werden mit-soft-geloescht,
    damit kein Antwortfaden ohne Kontext stehen bleibt. Verteilt ein
    ``comment_deleted``-Live-Event.
    """
    session = require_session(request)
    user_id = _session_user_id(session)
    _require_read(db, template_id, user_id)

    comment = (
        db.query(ChecklistNodeComment)
        .filter(
            ChecklistNodeComment.id == comment_id,
            ChecklistNodeComment.template_id == template_id,
        )
        .first()
    )
    if not comment:
        raise HTTPException(404, "Kommentar nicht gefunden.")

    is_author = comment.author_id == user_id
    is_owner = False
    member = _get_member(template_id, user_id, db)
    if member and member.role == MemberRole.OWNER.value:
        is_owner = True
    if not (is_author or is_owner):
        raise HTTPException(403, "Nur der Autor oder ein Owner darf löschen.")

    if comment.deleted_at is None:
        now = _utcnow()
        comment.deleted_at = now
        # Direkte Antworten ebenfalls weich loeschen.
        replies = (
            db.query(ChecklistNodeComment)
            .filter(
                ChecklistNodeComment.parent_comment_id == comment.id,
                ChecklistNodeComment.deleted_at.is_(None),
            )
            .all()
        )
        for r in replies:
            r.deleted_at = now
        db.commit()

    broker.publish(template_id, {
        "type": "comment_deleted", "user_id": user_id,
        "node_id": comment.node_id, "template_id": template_id,
        "comment_id": comment.id,
    })
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Unread-Tracking
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{template_id}/unread-counts")
def unread_counts(
    template_id: str, request: Request, db: Session = Depends(get_db),
) -> dict[str, int]:
    """Liefert je Knoten die Anzahl ungelesener Kommentare des Nutzers.

    Als ungelesen gilt jeder nicht-geloeschte Kommentar, fuer den kein
    ``ChecklistNoteRead``-Eintrag (user_id, comment_id) existiert. Eigene
    Beitraege zaehlen nicht als ungelesen. Rueckgabe: ``{node_id: anzahl}``;
    Knoten ohne ungelesene Kommentare fehlen in der Map.
    """
    session = require_session(request)
    user_id = _session_user_id(session)
    _require_read(db, template_id, user_id)

    # Bereits gelesene Kommentar-IDs des Nutzers.
    read_ids = {
        row[0]
        for row in db.query(ChecklistNoteRead.comment_id)
        .filter(ChecklistNoteRead.user_id == user_id,
                ChecklistNoteRead.template_id == template_id)
        .all()
    }

    rows = (
        db.query(ChecklistNodeComment.node_id, ChecklistNodeComment.id)
        .filter(
            ChecklistNodeComment.template_id == template_id,
            ChecklistNodeComment.deleted_at.is_(None),
            ChecklistNodeComment.author_id != user_id,
        )
        .all()
    )

    counts: dict[str, int] = {}
    for node_id, comment_id in rows:
        if comment_id in read_ids:
            continue
        counts[node_id] = counts.get(node_id, 0) + 1
    return counts


@router.post("/{template_id}/nodes/{node_id}/mark-read")
def mark_read(
    template_id: str, node_id: str,
    request: Request, db: Session = Depends(get_db),
) -> dict:
    """Markiert alle Kommentare eines Knotens fuer den Nutzer als gelesen.

    Legt fehlende ``ChecklistNoteRead``-Eintraege an (Upsert je
    ``(user_id, comment_id)``). Liefert die Anzahl neu markierter Kommentare.
    """
    session = require_session(request)
    user_id = _session_user_id(session)
    _require_read(db, template_id, user_id)
    _get_node(template_id, node_id, db)

    comment_ids = [
        row[0]
        for row in db.query(ChecklistNodeComment.id)
        .filter(
            ChecklistNodeComment.template_id == template_id,
            ChecklistNodeComment.node_id == node_id,
            ChecklistNodeComment.deleted_at.is_(None),
        )
        .all()
    ]
    if not comment_ids:
        return {"marked": 0}

    already = {
        row[0]
        for row in db.query(ChecklistNoteRead.comment_id)
        .filter(
            ChecklistNoteRead.user_id == user_id,
            ChecklistNoteRead.comment_id.in_(comment_ids),
        )
        .all()
    }

    marked = 0
    for cid in comment_ids:
        if cid in already:
            continue
        db.add(ChecklistNoteRead(
            id=str(uuid.uuid4()),
            user_id=user_id,
            template_id=template_id,
            node_id=node_id,
            comment_id=cid,
        ))
        marked += 1
    db.commit()
    return {"marked": marked}


# ─────────────────────────────────────────────────────────────────────────────
# Referenz-Dokumente je Knoten
# ─────────────────────────────────────────────────────────────────────────────

def _refdoc_out(d: ChecklistNodeReferenceDoc) -> RefDocOut:
    return RefDocOut(
        id=d.id,
        template_id=d.template_id,
        node_id=d.node_id,
        document_name=d.document_name,
        document_path=d.document_path,
        reference_text=d.reference_text,
        created_at=d.created_at,
    )


@router.get("/{template_id}/nodes/{node_id}/refdocs", response_model=list[RefDocOut])
def list_refdocs(
    template_id: str, node_id: str,
    request: Request, db: Session = Depends(get_db),
):
    """Liefert die Referenz-Dokumente eines Knotens (Lesezugriff)."""
    session = require_session(request)
    user_id = _session_user_id(session)
    _require_read(db, template_id, user_id)
    _get_node(template_id, node_id, db)

    rows = (
        db.query(ChecklistNodeReferenceDoc)
        .filter(
            ChecklistNodeReferenceDoc.template_id == template_id,
            ChecklistNodeReferenceDoc.node_id == node_id,
        )
        .order_by(ChecklistNodeReferenceDoc.created_at.asc())
        .all()
    )
    return [_refdoc_out(d) for d in rows]


@router.post("/{template_id}/nodes/{node_id}/refdocs", response_model=RefDocOut)
def create_refdoc(
    template_id: str, node_id: str, data: RefDocCreate,
    request: Request, db: Session = Depends(get_db),
):
    """Verknuepft ein Referenz-Dokument mit einem Knoten (mindestens editor).

    Verteilt ein ``refdoc_added``-Live-Event an verbundene Clients.
    """
    session = require_session(request)
    user_id = _session_user_id(session)
    _require_role(db, template_id, user_id, MemberRole.EDITOR)
    _get_node(template_id, node_id, db)

    name = (data.document_name or "").strip()
    if not name:
        raise HTTPException(422, "document_name darf nicht leer sein.")

    doc = ChecklistNodeReferenceDoc(
        id=str(uuid.uuid4()),
        template_id=template_id,
        node_id=node_id,
        document_name=name,
        document_path=(data.document_path or None),
        reference_text=(data.reference_text or None),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    out = _refdoc_out(doc)
    broker.publish(template_id, {
        "type": "refdoc_added", "user_id": user_id,
        "node_id": node_id, "template_id": template_id,
        "refdoc": out.model_dump(mode="json"),
    })
    return out


@router.delete("/{template_id}/refdocs/{refdoc_id}", status_code=204)
def delete_refdoc(
    template_id: str, refdoc_id: str,
    request: Request, db: Session = Depends(get_db),
):
    """Loescht ein Referenz-Dokument hart (mindestens editor).

    Verteilt ein ``refdoc_deleted``-Live-Event an verbundene Clients.
    """
    session = require_session(request)
    user_id = _session_user_id(session)
    _require_role(db, template_id, user_id, MemberRole.EDITOR)

    doc = (
        db.query(ChecklistNodeReferenceDoc)
        .filter(
            ChecklistNodeReferenceDoc.id == refdoc_id,
            ChecklistNodeReferenceDoc.template_id == template_id,
        )
        .first()
    )
    if not doc:
        raise HTTPException(404, "Referenz-Dokument nicht gefunden.")

    node_id = doc.node_id
    db.delete(doc)
    db.commit()

    broker.publish(template_id, {
        "type": "refdoc_deleted", "user_id": user_id,
        "node_id": node_id, "template_id": template_id,
        "refdoc_id": refdoc_id,
    })
    return None


# Forward-Reference fuer das selbstreferenzielle CommentOut aufloesen.
CommentOut.model_rebuild()
