"""
flowworkshop · routers/checklist_history.py

Versionierungs-Lese- und Restore-API fuer das KOM-Checklisten-Template-
Subsystem (Designer). Liest die node-level Aenderungshistorie
(ChecklistNodeHistory), die von den Mutations-Handlern in
routers/checklist_templates.py (Phase 2/8) geschrieben wird, und erlaubt das
Zuruecksetzen eines Knotens auf einen frueheren Snapshot.

Bewusst entkoppelt: dieser Router importiert KEINE Helfer aus
checklist_templates.py. Rechtepruefung, Snapshot-Felder und das Schreiben des
Restore-Verlaufseintrags sind hier lokal definiert, damit beide Router
unabhaengig wartbar bleiben. Gemeinsame Quelle der Wahrheit ist allein das
Datenmodell (models/checklist_template.py).

Umfang:
  - GET    /{id}/history                      — Commit-artiger Gesamtverlauf
  - GET    /{id}/nodes/{node_id}/history      — Verlauf eines einzelnen Knotens
  - GET    /{id}/history/{history_id}         — Detail inkl. Snapshot + Diff
  - POST   /{id}/history/{history_id}/restore — Knoten auf Snapshot zuruecksetzen

Rechte: Lese-Endpunkte fuer Mitglieder (oder veroeffentlichte Templates),
Restore nur fuer editor/owner.
"""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models.checklist_template import (
    ChecklistTemplate,
    ChecklistTemplateNode,
    ChecklistNodeHistory,
    ChecklistMember,
    MemberRole,
    NodeChangeType,
    TemplateStatus,
)
from models.registration import Registration
from routers.auth import require_session

router = APIRouter(
    prefix="/api/checklist-templates",
    tags=["checklist-history"],
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

# Knoten-Felder, die in den Snapshot eingehen und beim Restore zurueckgeschrieben
# werden. Identisch zur Tracked-Field-Liste der Mutations-Handler — hier bewusst
# lokal dupliziert, um keine Import-Kopplung an checklist_templates.py zu
# erzeugen. Quelle der Wahrheit bleibt das Modell ChecklistTemplateNode.
_NODE_TRACKED_FIELDS = (
    "parent_id", "node_type", "branch", "ja_label", "nein_label",
    "decision_parent_id", "sort_order", "title", "public_remark",
    "remark_snippets_json", "eingabetyp", "answer_type", "answer_set_id",
    "category_id", "legal_reference", "relevant_documents_json", "is_header_field",
)


def _utcnow() -> datetime:
    """Naive UTC-Zeit (konsistent mit den DateTime-Spalten ohne tz)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── Pydantic-Schemas (lokal, da nur fuer diesen Router relevant) ──────────────

class HistoryEntryOut(BaseModel):
    """Ein Verlaufseintrag in der Commit-artigen Listenansicht."""
    id: str
    template_id: str
    node_id: str
    node_version: int
    change_type: str
    change_reason: str | None = None
    summary: str  # knappe, menschenlesbare Zusammenfassung
    changed_by_id: str | None = None
    changed_by_name: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class HistoryDetailOut(HistoryEntryOut):
    """Detailansicht eines Verlaufseintrags fuer die Diff-Anzeige."""
    node_snapshot: dict | None = None
    changed_fields: dict | None = None
    old_parent_id: str | None = None
    new_parent_id: str | None = None
    old_position: int | None = None
    new_position: int | None = None


class RestoreRequest(BaseModel):
    """Optionaler Begruendungstext fuer die Wiederherstellung."""
    change_reason: str | None = None


class RestoreResult(BaseModel):
    """Ergebnis einer Wiederherstellung."""
    status: str  # "restored" oder "recreated"
    node_id: str
    new_version: int
    history_id: str


# ── Helfer: Rechtepruefung ────────────────────────────────────────────────────

def _get_template(template_id: str, db: Session) -> ChecklistTemplate:
    """Laedt das Template oder wirft 404."""
    tpl = db.query(ChecklistTemplate).filter(ChecklistTemplate.id == template_id).first()
    if not tpl:
        raise HTTPException(404, "Checkliste nicht gefunden.")
    return tpl


def _require_role(
    db: Session, template_id: str, user_id: str, min_role: MemberRole,
) -> ChecklistMember | None:
    """Stellt sicher, dass der Nutzer am Template mindestens ``min_role`` hat.

    Fuer Lese-Zugriff (min_role=VIEWER) gilt zusaetzlich: ist das Template
    ``published``, darf jeder angemeldete Nutzer lesen — auch ohne explizite
    Mitgliedschaft. Schreibende Aktionen (Restore, min_role=EDITOR) erfordern
    immer eine Mitgliedschaft mit ausreichendem Rang.

    Liefert die Mitgliedschaft zurueck (oder ``None`` beim published-Lesezugriff
    ohne Mitgliedschaft). Wirft 403 bei unzureichender Berechtigung.
    """
    member = (
        db.query(ChecklistMember)
        .filter(
            ChecklistMember.template_id == template_id,
            ChecklistMember.user_id == user_id,
        )
        .first()
    )
    need = _ROLE_RANK.get(min_role.value, 99)

    if member is not None:
        have = _ROLE_RANK.get(member.role, 0)
        if have >= need:
            return member
        raise HTTPException(
            403,
            f"Unzureichende Berechtigung — erforderlich: {min_role.value}, "
            f"vorhanden: {member.role}.",
        )

    # Kein Mitglied: nur lesender Zugriff auf veroeffentlichte Templates erlaubt.
    if need <= _ROLE_RANK[MemberRole.VIEWER.value]:
        tpl = _get_template(template_id, db)
        if (tpl.status or "").lower() == TemplateStatus.PUBLISHED.value:
            return None
    raise HTTPException(403, "Kein Zugriff auf diese Checkliste.")


# ── Helfer: Anreicherung & Zusammenfassung ────────────────────────────────────

def _load_user_names(user_ids: set[str], db: Session) -> dict[str, str]:
    """Laedt Vor-/Nachnamen fuer eine Menge von Registration-IDs als Map."""
    ids = {uid for uid in user_ids if uid}
    if not ids:
        return {}
    rows = db.query(Registration).filter(Registration.id.in_(ids)).all()
    names: dict[str, str] = {}
    for reg in rows:
        full = f"{reg.first_name or ''} {reg.last_name or ''}".strip()
        names[reg.id] = full or (reg.organization or reg.id)
    return names


# Menschenlesbare Beschriftung der Aenderungsarten.
_CHANGE_LABELS = {
    NodeChangeType.CREATED.value: "Knoten angelegt",
    NodeChangeType.UPDATED.value: "Knoten bearbeitet",
    NodeChangeType.DELETED.value: "Knoten geloescht",
    NodeChangeType.MOVED.value: "Knoten verschoben",
    NodeChangeType.DUPLICATED.value: "Knoten dupliziert",
    NodeChangeType.RESTORED.value: "Knoten wiederhergestellt",
    NodeChangeType.TRANSLATED.value: "Uebersetzung erzeugt",
    NodeChangeType.REVIEWED.value: "Uebersetzung geprueft",
}


def _summarize(entry: ChecklistNodeHistory) -> str:
    """Erzeugt eine knappe Zusammenfassung eines Verlaufseintrags.

    Nutzt — falls vorhanden — den Knotentitel aus dem Snapshot und die Anzahl
    geaenderter Felder, um eine Commit-artige Zeile zu bilden.
    """
    label = _CHANGE_LABELS.get(entry.change_type, entry.change_type)
    snapshot = entry.node_snapshot or {}
    title = (snapshot.get("title") or "").strip() if isinstance(snapshot, dict) else ""
    parts = [label]
    if title:
        kurz = title if len(title) <= 60 else title[:57] + "…"
        parts.append(f"„{kurz}“")
    if entry.change_type == NodeChangeType.UPDATED.value and isinstance(entry.changed_fields, dict):
        n = len(entry.changed_fields)
        if n:
            parts.append(f"({n} Feld{'er' if n != 1 else ''} geaendert)")
    if entry.change_type == NodeChangeType.MOVED.value:
        parts.append("(Verschiebung im Baum)")
    return " ".join(parts)


def _entry_out(entry: ChecklistNodeHistory, names: dict[str, str]) -> HistoryEntryOut:
    """Baut das Listen-Schema fuer einen Verlaufseintrag."""
    return HistoryEntryOut(
        id=entry.id,
        template_id=entry.template_id,
        node_id=entry.node_id,
        node_version=entry.node_version,
        change_type=entry.change_type,
        change_reason=entry.change_reason,
        summary=_summarize(entry),
        changed_by_id=entry.changed_by_id,
        changed_by_name=names.get(entry.changed_by_id) if entry.changed_by_id else None,
        created_at=entry.created_at,
    )


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


# ── Lese-Endpunkte ────────────────────────────────────────────────────────────

@router.get("/{template_id}/history", response_model=list[HistoryEntryOut])
def get_template_history(
    template_id: str,
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    node_id: str | None = Query(None, description="Optional auf einen Knoten filtern."),
    db: Session = Depends(get_db),
):
    """Commit-artiger Gesamtverlauf einer Checkliste (neueste zuerst).

    Liefert alle ChecklistNodeHistory-Eintraege zum ``template_id``, angereichert
    um den Namen des Aendernden und eine knappe Zusammenfassung. Optional ueber
    ``node_id`` auf einen einzelnen Knoten gefiltert. Paginierung ueber
    ``limit``/``offset``. Sichtbar fuer Mitglieder oder bei veroeffentlichten
    Checklisten.
    """
    session = require_session(request)
    _get_template(template_id, db)
    _require_role(db, template_id, session.get("user_id"), MemberRole.VIEWER)

    q = db.query(ChecklistNodeHistory).filter(
        ChecklistNodeHistory.template_id == template_id
    )
    if node_id:
        q = q.filter(ChecklistNodeHistory.node_id == node_id)
    rows = (
        q.order_by(ChecklistNodeHistory.created_at.desc(), ChecklistNodeHistory.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    names = _load_user_names({r.changed_by_id for r in rows}, db)
    return [_entry_out(r, names) for r in rows]


@router.get("/{template_id}/nodes/{node_id}/history", response_model=list[HistoryEntryOut])
def get_node_history(
    template_id: str,
    node_id: str,
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Vollstaendiger Verlauf eines einzelnen Knotens (neueste zuerst)."""
    session = require_session(request)
    _get_template(template_id, db)
    _require_role(db, template_id, session.get("user_id"), MemberRole.VIEWER)

    rows = (
        db.query(ChecklistNodeHistory)
        .filter(
            ChecklistNodeHistory.template_id == template_id,
            ChecklistNodeHistory.node_id == node_id,
        )
        .order_by(
            ChecklistNodeHistory.node_version.desc(),
            ChecklistNodeHistory.created_at.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )
    names = _load_user_names({r.changed_by_id for r in rows}, db)
    return [_entry_out(r, names) for r in rows]


@router.get("/{template_id}/history/{history_id}", response_model=HistoryDetailOut)
def get_history_detail(
    template_id: str,
    history_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Detail eines Verlaufseintrags inkl. Voll-Snapshot und Feld-Diff.

    Grundlage fuer die Diff-Anzeige im Frontend (alter/neuer Wert je Feld).
    """
    session = require_session(request)
    _get_template(template_id, db)
    _require_role(db, template_id, session.get("user_id"), MemberRole.VIEWER)

    entry = (
        db.query(ChecklistNodeHistory)
        .filter(
            ChecklistNodeHistory.id == history_id,
            ChecklistNodeHistory.template_id == template_id,
        )
        .first()
    )
    if not entry:
        raise HTTPException(404, "Verlaufseintrag nicht gefunden.")

    names = _load_user_names({entry.changed_by_id}, db)
    base = _entry_out(entry, names)
    return HistoryDetailOut(
        **base.model_dump(),
        node_snapshot=entry.node_snapshot if isinstance(entry.node_snapshot, dict) else None,
        changed_fields=entry.changed_fields if isinstance(entry.changed_fields, dict) else None,
        old_parent_id=entry.old_parent_id,
        new_parent_id=entry.new_parent_id,
        old_position=entry.old_position,
        new_position=entry.new_position,
    )


# ── Restore-Endpunkt ──────────────────────────────────────────────────────────

@router.post("/{template_id}/history/{history_id}/restore", response_model=RestoreResult)
def restore_history(
    template_id: str,
    history_id: str,
    request: Request,
    body: RestoreRequest | None = None,
    db: Session = Depends(get_db),
):
    """Setzt einen Knoten auf den Stand des Snapshots dieses Verlaufseintrags.

    Ablauf:
      1. Rechtepruefung (mindestens editor).
      2. Verlaufseintrag laden, Snapshot muss vorhanden sein.
      3. Existiert der Knoten noch → die Tracked-Felder aus dem Snapshot
         zurueckschreiben. Existiert er nicht mehr → aus dem Snapshot neu
         anlegen (sofern dieser vollstaendig ist), mit derselben node_id.
      4. Einen NEUEN ChecklistNodeHistory-Eintrag ``restored`` schreiben
         (changed_by_id = aktueller Nutzer, node_version hochgezaehlt,
         Snapshot = neuer Knotenstand).

    Nur fuer editor/owner.
    """
    session = require_session(request)
    user_id = session.get("user_id")
    _get_template(template_id, db)
    _require_role(db, template_id, user_id, MemberRole.EDITOR)

    entry = (
        db.query(ChecklistNodeHistory)
        .filter(
            ChecklistNodeHistory.id == history_id,
            ChecklistNodeHistory.template_id == template_id,
        )
        .first()
    )
    if not entry:
        raise HTTPException(404, "Verlaufseintrag nicht gefunden.")

    snapshot = entry.node_snapshot
    if not isinstance(snapshot, dict) or not snapshot:
        raise HTTPException(
            409,
            "Dieser Verlaufseintrag enthaelt keinen Snapshot und kann nicht "
            "wiederhergestellt werden.",
        )

    node = (
        db.query(ChecklistTemplateNode)
        .filter(
            ChecklistTemplateNode.id == entry.node_id,
            ChecklistTemplateNode.template_id == template_id,
        )
        .first()
    )

    if node is not None:
        # Bestehenden Knoten auf den Snapshot-Stand zuruecksetzen.
        for field in _NODE_TRACKED_FIELDS:
            if field in snapshot:
                setattr(node, field, snapshot[field])
        node.updated_at = _utcnow()
        result_status = "restored"
    else:
        # Knoten existiert nicht mehr → aus dem Snapshot neu anlegen.
        # node_type ist Pflicht (NOT NULL) und reicht als Minimalvoraussetzung.
        if not snapshot.get("node_type"):
            raise HTTPException(
                409,
                "Snapshot ist unvollstaendig (node_type fehlt) — der geloeschte "
                "Knoten kann nicht neu angelegt werden.",
            )
        node = ChecklistTemplateNode(id=entry.node_id, template_id=template_id)
        for field in _NODE_TRACKED_FIELDS:
            if field in snapshot:
                setattr(node, field, snapshot[field])
        db.add(node)
        result_status = "recreated"

    # Neuen Verlaufseintrag 'restored' schreiben, node_version hochzaehlen.
    new_version = _latest_node_version(template_id, entry.node_id, db) + 1
    restore_snapshot = {field: getattr(node, field) for field in _NODE_TRACKED_FIELDS}
    reason_default = (
        f"Wiederhergestellt auf Version {entry.node_version} "
        f"(Eintrag {entry.id})"
    )
    new_id = str(uuid.uuid4())
    restored = ChecklistNodeHistory(
        id=new_id,
        template_id=template_id,
        node_id=entry.node_id,
        node_version=new_version,
        change_type=NodeChangeType.RESTORED.value,
        node_snapshot=restore_snapshot,
        changed_fields=None,
        changed_by_id=user_id,
        change_reason=(body.change_reason if body and body.change_reason else reason_default),
    )
    db.add(restored)
    db.commit()

    log.info(
        "checklist restore: template=%s node=%s -> v%s (%s) durch %s",
        template_id, entry.node_id, new_version, result_status, user_id,
    )
    return RestoreResult(
        status=result_status,
        node_id=entry.node_id,
        new_version=new_version,
        history_id=new_id,
    )
