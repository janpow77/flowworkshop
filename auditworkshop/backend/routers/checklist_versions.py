"""
flowworkshop · routers/checklist_versions.py

Ganz-Checklisten-Versionsverwaltung fuer das KOM-Checklisten-Template-Subsystem
(Designer). Ergaenzt die node-level Aenderungshistorie (ChecklistNodeHistory,
siehe routers/checklist_history.py) um vollstaendige, benannte Gesamtversionen.

Grundidee — Arbeitskopie vs. eingefrorener Snapshot:
  - Der relationale Knoten-Baum (ChecklistTemplateNode-Zeilen) ist die
    ARBEITSKOPIE einer Checkliste. Sie veraendert sich laufend.
  - Eine Version (ChecklistTemplateVersion) ist ein eingefrorener JSONB-SNAPSHOT
    dieses Baums zum Zeitpunkt der Erstellung. Sie dient Freigaben/Releases und
    der Wiederherstellung frueherer Staende.

Bewusst entkoppelt: dieser Router importiert KEINE Helfer aus
checklist_templates.py oder checklist_history.py. Rechtepruefung, Snapshot-Format
und Diff sind hier lokal definiert, damit die Router unabhaengig wartbar bleiben.
Gemeinsame Quelle der Wahrheit ist allein das Datenmodell
(models/checklist_template.py).

SNAPSHOT-FORMAT (tree_snapshot) — flache Knoten-Map:
  {
    "root_ids": [<id>, ...],          # Knoten ohne (bekannten) parent_id
    "nodes": {
      "<node_id>": {
        "id", "parent_id", "node_type", "branch", "ja_label", "nein_label",
        "sort_order", "title", "status", "public_remark", "eingabetyp",
        "answer_type", "answer_set_id", "category_id", "legal_reference",
        "relevant_documents_json", "is_header_field"
      },
      ...
    }
  }
Die flache Map (statt verschachteltem children[]) wurde gewaehlt, weil der Diff
zweier Versionen ueber die node-id matcht und die Wiederherstellung die Knoten
ohnehin als flache Zeilen neu anlegt — beides ist auf der Map direkt und ohne
Baum-Traversierung moeglich.

Umfang:
  - GET    /{id}/versions                         — Liste (neueste zuerst)
  - POST   /{id}/versions                         — Snapshot anlegen (editor+)
  - GET    /{id}/versions/{version_id}            — Version inkl. tree_snapshot
  - POST   /{id}/versions/{version_id}/freeze     — einfrieren/freigeben (owner/editor)
  - GET    /{id}/versions/compare                 — field-level Diff zweier Versionen
  - POST   /{id}/versions/{version_id}/restore    — Arbeitskopie wiederherstellen (owner/editor)

Rechte: Lese-Endpunkte fuer Mitglieder (oder veroeffentlichte Templates),
Schreiben (Snapshot/Freeze/Restore) nur fuer editor/owner.
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
    ChecklistTemplateVersion,
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
    tags=["checklist-versions"],
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

# Knoten-Felder, die in den Snapshot eingehen und beim Restore wieder als
# relationale Zeilen angelegt werden. Bewusst lokal gehalten (keine Import-
# Kopplung an checklist_templates.py). Quelle der Wahrheit bleibt das Modell
# ChecklistTemplateNode.
_NODE_SNAPSHOT_FIELDS = (
    "id", "parent_id", "node_type", "branch", "ja_label", "nein_label",
    "sort_order", "title", "status", "public_remark", "eingabetyp",
    "answer_type", "answer_set_id", "category_id", "legal_reference",
    "relevant_documents_json", "is_header_field",
)

# Felder, die der Versions-Diff (compare) gegenueberstellt.
_DIFF_FIELDS = (
    "title", "status", "node_type", "branch", "sort_order",
    "answer_type", "legal_reference", "public_remark", "relevant_documents_json",
)


def _utcnow() -> datetime:
    """Naive UTC-Zeit (konsistent mit den DateTime-Spalten ohne tz)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── Pydantic-Schemas (lokal, da nur fuer diesen Router relevant) ──────────────

class VersionCreate(BaseModel):
    """Eingabe zum Anlegen einer neuen Gesamtversion."""
    version_number: str
    notes: str | None = None


class VersionListItem(BaseModel):
    """Ein Eintrag in der Versionsliste (ohne tree_snapshot)."""
    id: str
    template_id: str
    version_number: str
    is_frozen: bool
    status: str
    notes: str | None = None
    node_count: int
    created_by_id: str | None = None
    created_by_name: str | None = None
    created_at: datetime | None = None


class VersionDetail(VersionListItem):
    """Vollstaendige Version inkl. eingefrorenem Baum-Snapshot."""
    tree_snapshot: dict | None = None


class CompareNodeBrief(BaseModel):
    """Kurz-Beschreibung eines hinzugefuegten/entfernten Knotens im Diff."""
    node_id: str
    node_type: str | None = None
    title: str | None = None


class CompareChangedNode(BaseModel):
    """Ein geaenderter Knoten mit field-level {old, new}-Diff."""
    node_id: str
    node_type: str | None = None
    title: str | None = None
    fields: dict[str, dict[str, object | None]]


class CompareVersionInfo(BaseModel):
    """Metadaten einer verglichenen Version (Kopf der Compare-Antwort)."""
    id: str
    version_number: str
    status: str
    is_frozen: bool
    node_count: int
    created_at: datetime | None = None


class CompareSummary(BaseModel):
    """Zaehler-Zusammenfassung des Diffs."""
    added: int
    removed: int
    changed: int
    unchanged: int


class CompareResult(BaseModel):
    """Ergebnis des field-level Diffs zweier Versions-Snapshots."""
    version_a: CompareVersionInfo
    version_b: CompareVersionInfo
    summary: CompareSummary
    added: list[CompareNodeBrief]
    removed: list[CompareNodeBrief]
    changed: list[CompareChangedNode]


# ── Helfer: Rechtepruefung ────────────────────────────────────────────────────

def _get_template(template_id: str, db: Session) -> ChecklistTemplate:
    """Laedt das Template oder wirft 404."""
    tpl = db.query(ChecklistTemplate).filter(ChecklistTemplate.id == template_id).first()
    if not tpl:
        raise HTTPException(404, "Checkliste nicht gefunden.")
    return tpl


def _require_role(
    db: Session, template_id: str, user_id: str | None, min_role: MemberRole,
) -> ChecklistMember | None:
    """Stellt sicher, dass der Nutzer am Template mindestens ``min_role`` hat.

    Fuer Lese-Zugriff (min_role=VIEWER) gilt zusaetzlich: ist das Template
    ``published``, darf jeder angemeldete Nutzer lesen — auch ohne explizite
    Mitgliedschaft. Schreibende Aktionen (Snapshot/Freeze/Restore, min_role=
    EDITOR) erfordern immer eine Mitgliedschaft mit ausreichendem Rang.

    Liefert die Mitgliedschaft zurueck (oder ``None`` beim published-Lesezugriff
    ohne Mitgliedschaft). Wirft 401 ohne Nutzerkennung, 404/403 sonst.
    """
    if not user_id:
        raise HTTPException(401, "Sitzung ohne Nutzerkennung.")

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


# ── Helfer: Nutzer-Stammdaten ─────────────────────────────────────────────────

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


# ── Helfer: Snapshot erzeugen & lesen ─────────────────────────────────────────

def _node_to_snapshot(node: ChecklistTemplateNode) -> dict:
    """Serialisiert einen Knoten in das Snapshot-Dict (nur Snapshot-Felder)."""
    return {field: getattr(node, field) for field in _NODE_SNAPSHOT_FIELDS}


def _build_tree_snapshot(template_id: str, db: Session) -> dict:
    """Erzeugt den flachen Baum-Snapshot aus den aktuellen Knoten-Zeilen.

    Liefert {"root_ids": [...], "nodes": {id: {...}}}. ``root_ids`` enthaelt alle
    Knoten ohne bekannten parent_id (verwaiste Kanten werden robust als Wurzeln
    behandelt)."""
    nodes = (
        db.query(ChecklistTemplateNode)
        .filter(ChecklistTemplateNode.template_id == template_id)
        .all()
    )
    node_map: dict[str, dict] = {n.id: _node_to_snapshot(n) for n in nodes}
    known_ids = set(node_map.keys())
    root_ids = [
        n.id for n in nodes
        if not n.parent_id or n.parent_id not in known_ids
    ]
    return {"root_ids": root_ids, "nodes": node_map}


def _snapshot_nodes(snapshot: dict | None) -> dict[str, dict]:
    """Extrahiert die {id: knoten}-Map aus einem tree_snapshot (robust)."""
    if not isinstance(snapshot, dict):
        return {}
    nodes = snapshot.get("nodes")
    if isinstance(nodes, dict):
        return {nid: n for nid, n in nodes.items() if isinstance(n, dict)}
    return {}


def _snapshot_node_count(version: ChecklistTemplateVersion) -> int:
    """Anzahl der Knoten im Snapshot einer Version."""
    return len(_snapshot_nodes(version.tree_snapshot))


def _topological_order(snapshot_nodes: dict[str, dict]) -> list[str]:
    """Sortiert die Snapshot-Knoten so, dass jeder Elternknoten VOR seinen
    Kindern erscheint (Eltern-vor-Kind).

    Notwendig, weil der ``parent_id``-Self-FK der Knoten-Tabelle nicht
    DEFERRABLE ist und PostgreSQL ihn bereits beim INSERT prueft. Knoten ohne
    (bekannten) ``parent_id`` gelten als Wurzeln und kommen zuerst. Zyklen oder
    verwaiste Kanten werden robust behandelt: alle Knoten, die nicht regulaer
    aufgeloest werden konnten, werden am Ende angehaengt (ihr parent_id wird
    dann ggf. von der DB als Verletzung gemeldet — fail-fast statt stiller
    Inkonsistenz).
    """
    known = set(snapshot_nodes.keys())
    # Kinder-Liste je Elternknoten aufbauen; Wurzeln gesondert sammeln.
    children: dict[str, list[str]] = {}
    roots: list[str] = []
    for nid, node in snapshot_nodes.items():
        parent = node.get("parent_id")
        if parent and parent in known and parent != nid:
            children.setdefault(parent, []).append(nid)
        else:
            roots.append(nid)

    ordered: list[str] = []
    visited: set[str] = set()
    # Iterative Tiefensuche ab den Wurzeln (Eltern vor Kindern).
    stack = list(reversed(roots))
    while stack:
        nid = stack.pop()
        if nid in visited:
            continue
        visited.add(nid)
        ordered.append(nid)
        for child in reversed(children.get(nid, [])):
            if child not in visited:
                stack.append(child)

    # Nicht erreichte Knoten (Zyklus/verwaiste Kante) ans Ende — fail-fast.
    if len(ordered) != len(known):
        for nid in snapshot_nodes:
            if nid not in visited:
                ordered.append(nid)
    return ordered


# ── Helfer: Serialisierung ────────────────────────────────────────────────────

def _version_list_item(
    version: ChecklistTemplateVersion, names: dict[str, str],
) -> VersionListItem:
    return VersionListItem(
        id=version.id,
        template_id=version.template_id,
        version_number=version.version_number,
        is_frozen=bool(version.is_frozen),
        status=version.status,
        notes=version.notes,
        node_count=_snapshot_node_count(version),
        created_by_id=version.created_by_id,
        created_by_name=(
            names.get(version.created_by_id) if version.created_by_id else None
        ),
        created_at=version.created_at,
    )


def _get_version(
    template_id: str, version_id: str, db: Session,
) -> ChecklistTemplateVersion:
    """Laedt eine Version und stellt die Template-Zugehoerigkeit sicher."""
    version = (
        db.query(ChecklistTemplateVersion)
        .filter(
            ChecklistTemplateVersion.id == version_id,
            ChecklistTemplateVersion.template_id == template_id,
        )
        .first()
    )
    if not version:
        raise HTTPException(404, "Version nicht gefunden.")
    return version


# ── Endpunkte: Liste & Detail ─────────────────────────────────────────────────

@router.get("/{template_id}/versions", response_model=list[VersionListItem])
def list_versions(template_id: str, request: Request, db: Session = Depends(get_db)):
    """Listet alle Gesamtversionen einer Checkliste (neueste zuerst).

    Lesbar fuer Mitglieder; bei veroeffentlichten Templates fuer jeden
    angemeldeten Nutzer. ``node_count`` zaehlt die Knoten im jeweiligen Snapshot.
    """
    session = require_session(request)
    _require_role(db, template_id, session.get("user_id"), MemberRole.VIEWER)

    versions = (
        db.query(ChecklistTemplateVersion)
        .filter(ChecklistTemplateVersion.template_id == template_id)
        .order_by(ChecklistTemplateVersion.created_at.desc().nullslast())
        .all()
    )
    names = _load_user_names({v.created_by_id for v in versions}, db)
    return [_version_list_item(v, names) for v in versions]


# ── Endpunkt: Versionen vergleichen (field-level Diff) ────────────────────────
# WICHTIG: vor der parametrisierten Route /{version_id} registrieren, damit der
# literale Pfad "compare" nicht als version_id gematcht wird (FastAPI matcht in
# Definitionsreihenfolge).

def _compare_info(version: ChecklistTemplateVersion) -> CompareVersionInfo:
    return CompareVersionInfo(
        id=version.id,
        version_number=version.version_number,
        status=version.status,
        is_frozen=bool(version.is_frozen),
        node_count=_snapshot_node_count(version),
        created_at=version.created_at,
    )


@router.get("/{template_id}/versions/compare", response_model=CompareResult)
def compare_versions(
    template_id: str,
    request: Request,
    version_a_id: str = Query(..., description="Basis-Version (links)"),
    version_b_id: str = Query(..., description="Vergleichs-Version (rechts)"),
    db: Session = Depends(get_db),
):
    """Vergleicht zwei Versions-Snapshots auf Knoten-Ebene (field-level Diff).

    Matching erfolgt ueber die node-id. Knoten nur in B = hinzugefuegt, nur in A
    = entfernt, in beiden mit Feld-Unterschieden = geaendert, sonst unveraendert.
    Verglichene Felder: title, status, node_type, branch, sort_order, answer_type,
    legal_reference, public_remark, relevant_documents_json.
    """
    session = require_session(request)
    _require_role(db, template_id, session.get("user_id"), MemberRole.VIEWER)

    if version_a_id == version_b_id:
        raise HTTPException(422, "Bitte zwei unterschiedliche Versionen waehlen.")

    version_a = _get_version(template_id, version_a_id, db)
    version_b = _get_version(template_id, version_b_id, db)

    nodes_a = _snapshot_nodes(version_a.tree_snapshot)
    nodes_b = _snapshot_nodes(version_b.tree_snapshot)

    ids_a = set(nodes_a.keys())
    ids_b = set(nodes_b.keys())

    added: list[CompareNodeBrief] = []
    removed: list[CompareNodeBrief] = []
    changed: list[CompareChangedNode] = []
    unchanged = 0

    # Hinzugefuegt: nur in B vorhanden.
    for nid in ids_b - ids_a:
        node = nodes_b[nid]
        added.append(CompareNodeBrief(
            node_id=nid, node_type=node.get("node_type"), title=node.get("title"),
        ))

    # Entfernt: nur in A vorhanden.
    for nid in ids_a - ids_b:
        node = nodes_a[nid]
        removed.append(CompareNodeBrief(
            node_id=nid, node_type=node.get("node_type"), title=node.get("title"),
        ))

    # In beiden vorhanden: Feld-Diff bilden.
    for nid in ids_a & ids_b:
        node_a = nodes_a[nid]
        node_b = nodes_b[nid]
        field_diff: dict[str, dict[str, object | None]] = {}
        for field in _DIFF_FIELDS:
            old_val = node_a.get(field)
            new_val = node_b.get(field)
            if old_val != new_val:
                field_diff[field] = {"old": old_val, "new": new_val}
        if field_diff:
            changed.append(CompareChangedNode(
                node_id=nid,
                node_type=node_b.get("node_type") or node_a.get("node_type"),
                title=node_b.get("title") or node_a.get("title"),
                fields=field_diff,
            ))
        else:
            unchanged += 1

    return CompareResult(
        version_a=_compare_info(version_a),
        version_b=_compare_info(version_b),
        summary=CompareSummary(
            added=len(added), removed=len(removed),
            changed=len(changed), unchanged=unchanged,
        ),
        added=added,
        removed=removed,
        changed=changed,
    )


@router.get("/{template_id}/versions/{version_id}", response_model=VersionDetail)
def get_version(
    template_id: str, version_id: str, request: Request, db: Session = Depends(get_db),
):
    """Liefert eine einzelne Version inkl. eingefrorenem ``tree_snapshot``."""
    session = require_session(request)
    _require_role(db, template_id, session.get("user_id"), MemberRole.VIEWER)

    version = _get_version(template_id, version_id, db)
    names = _load_user_names({version.created_by_id}, db)
    base = _version_list_item(version, names)
    return VersionDetail(**base.model_dump(), tree_snapshot=version.tree_snapshot)


# ── Endpunkt: Snapshot anlegen ────────────────────────────────────────────────

@router.post("/{template_id}/versions", response_model=VersionDetail, status_code=201)
def create_version(
    template_id: str, data: VersionCreate, request: Request, db: Session = Depends(get_db),
):
    """Friert die aktuelle Arbeitskopie als neue Gesamtversion ein (editor+).

    Erzeugt einen flachen Baum-Snapshot der aktuellen ChecklistTemplateNode-Zeilen
    in ``tree_snapshot``, legt eine ChecklistTemplateVersion (status=draft,
    is_frozen=false) an und setzt ``template.current_version`` auf die neue
    Versionsnummer. Die Versionsnummer muss je Template eindeutig sein.
    """
    session = require_session(request)
    user_id = session.get("user_id")
    _require_role(db, template_id, user_id, MemberRole.EDITOR)

    version_number = (data.version_number or "").strip()
    if not version_number:
        raise HTTPException(422, "Eine Versionsnummer ist erforderlich.")
    if len(version_number) > 40:
        raise HTTPException(422, "Die Versionsnummer darf hoechstens 40 Zeichen lang sein.")

    # Eindeutigkeit der Versionsnummer je Template.
    existing = (
        db.query(ChecklistTemplateVersion)
        .filter(
            ChecklistTemplateVersion.template_id == template_id,
            ChecklistTemplateVersion.version_number == version_number,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            409, f"Die Versionsnummer «{version_number}» existiert fuer diese Checkliste bereits."
        )

    snapshot = _build_tree_snapshot(template_id, db)

    tpl = _get_template(template_id, db)
    version = ChecklistTemplateVersion(
        id=str(uuid.uuid4()),
        template_id=template_id,
        version_number=version_number,
        is_frozen=False,
        status="draft",
        tree_snapshot=snapshot,
        created_by_id=user_id,
        notes=data.notes,
    )
    db.add(version)
    tpl.current_version = version_number
    db.commit()
    db.refresh(version)
    log.info(
        "Checklisten-Version %s (%s) angelegt fuer Template %s durch %s — %d Knoten",
        version.id, version_number, template_id, user_id,
        _snapshot_node_count(version),
    )
    names = _load_user_names({version.created_by_id}, db)
    base = _version_list_item(version, names)
    return VersionDetail(**base.model_dump(), tree_snapshot=version.tree_snapshot)


# ── Endpunkt: Einfrieren / Freigeben ──────────────────────────────────────────

@router.post(
    "/{template_id}/versions/{version_id}/freeze", response_model=VersionDetail,
)
def freeze_version(
    template_id: str, version_id: str, request: Request, db: Session = Depends(get_db),
):
    """Friert eine Version ein und gibt sie frei (editor/owner).

    Setzt ``is_frozen=True`` und ``status='released'``. Eine eingefrorene Version
    bleibt als unveraenderlicher Freigabestand erhalten. Erneutes Einfrieren ist
    idempotent.
    """
    session = require_session(request)
    user_id = session.get("user_id")
    _require_role(db, template_id, user_id, MemberRole.EDITOR)

    version = _get_version(template_id, version_id, db)
    version.is_frozen = True
    version.status = "released"
    db.commit()
    db.refresh(version)
    log.info(
        "Checklisten-Version %s (%s) eingefroren/freigegeben durch %s",
        version.id, version.version_number, user_id,
    )
    names = _load_user_names({version.created_by_id}, db)
    base = _version_list_item(version, names)
    return VersionDetail(**base.model_dump(), tree_snapshot=version.tree_snapshot)


# ── Endpunkt: Arbeitskopie aus Snapshot wiederherstellen ──────────────────────

# Vollstaendige Spaltenmenge, die beim Restore in neue ChecklistTemplateNode-
# Zeilen geschrieben wird. Felder ausserhalb dieser Menge (z.B. Uebersetzung)
# werden auf die Server-Defaults gesetzt — der Snapshot haelt nur den fachlichen
# Kern (siehe _NODE_SNAPSHOT_FIELDS).
_RESTORE_FIELDS = _NODE_SNAPSHOT_FIELDS


# Felder, die in den node-level Restore-Snapshot (ChecklistNodeHistory) eingehen.
# Spiegelt die Tracked-Field-Liste der node-level CRUD-Pfade in
# checklist_templates.py — bewusst lokal gehalten (keine Import-Kopplung). Quelle
# der Wahrheit bleibt das Modell ChecklistTemplateNode.
_HISTORY_SNAPSHOT_FIELDS = (
    "parent_id", "node_type", "branch", "ja_label", "nein_label",
    "decision_parent_id", "sort_order", "title", "public_remark",
    "remark_snippets_json", "eingabetyp", "answer_type", "answer_set_id",
    "category_id", "legal_reference", "relevant_documents_json", "is_header_field",
)


def _latest_node_versions(template_id: str, db: Session) -> dict[str, int]:
    """Liefert je node_id die hoechste bisher vergebene node_version als Map.

    Ein Aggregat-Query statt N Einzelabfragen, damit der Restore eines grossen
    Baums nicht in ein N+1-Problem laeuft. Knoten ohne Historie fehlen in der
    Map (gelten als 0)."""
    rows = (
        db.query(
            ChecklistNodeHistory.node_id,
            func.max(ChecklistNodeHistory.node_version),
        )
        .filter(ChecklistNodeHistory.template_id == template_id)
        .group_by(ChecklistNodeHistory.node_id)
        .all()
    )
    return {node_id: int(maxv or 0) for node_id, maxv in rows}


def _write_restore_history(
    *, db: Session, template_id: str, version: ChecklistTemplateVersion,
    node: ChecklistTemplateNode, changed_by_id: str, node_version: int,
) -> None:
    """Schreibt einen node-level Verlaufseintrag ``restored`` fuer einen beim
    Versions-Restore neu angelegten Knoten (F-009).

    Macht den Ganz-Checklisten-Restore auf Knotenebene auditierbar — analog zu
    den CREATED/UPDATED/DELETED-Eintraegen der node-level CRUD-Pfade. Wird in
    derselben Transaktion wie der Restore committed."""
    snapshot = {field: getattr(node, field, None) for field in _HISTORY_SNAPSHOT_FIELDS}
    db.add(ChecklistNodeHistory(
        id=str(uuid.uuid4()),
        template_id=template_id,
        node_id=node.id,
        node_version=node_version,
        change_type=NodeChangeType.RESTORED.value,
        node_snapshot=snapshot,
        changed_fields=None,
        new_parent_id=getattr(node, "parent_id", None),
        new_position=getattr(node, "sort_order", None),
        changed_by_id=changed_by_id,
        change_reason=(
            f"Arbeitskopie aus Version {version.version_number} "
            f"({version.id}) wiederhergestellt"
        ),
    ))


class RestoreResult(BaseModel):
    """Ergebnis einer Wiederherstellung."""
    template_id: str
    version_id: str
    version_number: str
    restored_node_count: int
    deleted_node_count: int


@router.post(
    "/{template_id}/versions/{version_id}/restore", response_model=RestoreResult,
)
def restore_version(
    template_id: str, version_id: str, request: Request, db: Session = Depends(get_db),
):
    """Stellt die Arbeitskopie aus einem Versions-Snapshot wieder her (editor/owner).

    Loescht in EINER Transaktion alle aktuellen Knoten des Templates und legt sie
    aus ``tree_snapshot`` neu an. Da die Knoten-IDs aus dem Snapshot uebernommen
    werden, bleiben parent_id-/decision-Bezuege konsistent. Bei einem Fehler wird
    die Transaktion zurueckgerollt — die bestehende Arbeitskopie bleibt unberuehrt.

    Setzt ``template.current_version`` auf die wiederhergestellte Versionsnummer.
    """
    session = require_session(request)
    user_id = session.get("user_id")
    _require_role(db, template_id, user_id, MemberRole.EDITOR)

    tpl = _get_template(template_id, db)
    version = _get_version(template_id, version_id, db)

    snapshot_nodes = _snapshot_nodes(version.tree_snapshot)
    if not snapshot_nodes:
        raise HTTPException(
            422,
            "Der Snapshot dieser Version enthaelt keine Knoten — "
            "Wiederherstellung abgebrochen.",
        )

    try:
        # 1) Bestehende Arbeitskopie loeschen (Kaskade auf Kindknoten greift via
        #    FK ondelete=CASCADE; explizites delete je Zeile, damit ORM-Cascade
        #    und Identity-Map konsistent bleiben).
        deleted_count = (
            db.query(ChecklistTemplateNode)
            .filter(ChecklistTemplateNode.template_id == template_id)
            .count()
        )
        db.query(ChecklistTemplateNode).filter(
            ChecklistTemplateNode.template_id == template_id
        ).delete(synchronize_session=False)
        db.flush()

        # 2) Knoten aus dem Snapshot neu anlegen. WICHTIG: Der self-FK
        #    ``parent_id`` (workshop_checklist_nodes → workshop_checklist_nodes,
        #    ondelete=CASCADE) ist NICHT DEFERRABLE — PostgreSQL prueft ihn schon
        #    beim INSERT. Wuerde ein Kindknoten vor seinem Elternknoten angelegt,
        #    schluege der Restore mit einer FK-Verletzung fehl. Die Dict-Reihen-
        #    folge des Snapshots ist NICHT garantiert topologisch sortiert; daher
        #    werden die Knoten hier explizit in Eltern-vor-Kind-Reihenfolge
        #    einsortiert. Nur Snapshot-Felder setzen, template_id erzwingen,
        #    fremde/unbekannte Felder ignorieren.
        # Hoechste bisher vergebene node_version je Knoten EINMAL vorab laden
        # (vor dem Loeschen der Knoten — die Historie bleibt erhalten), damit der
        # Restore eines grossen Baums kein N+1-Problem erzeugt (F-009/F-011).
        latest_versions = _latest_node_versions(template_id, db)

        ordered_ids = _topological_order(snapshot_nodes)
        restored = 0
        for nid in ordered_ids:
            node = snapshot_nodes[nid]
            kwargs = {field: node.get(field) for field in _RESTORE_FIELDS}
            # id aus dem Snapshot (Schluessel hat Vorrang vor evtl. abweichendem
            # node["id"]), template_id konsistent erzwingen.
            kwargs["id"] = nid
            kwargs["template_id"] = template_id
            new_node = ChecklistTemplateNode(**kwargs)
            db.add(new_node)
            db.flush()  # FK je Knoten direkt pruefen — fail-fast bei Inkonsistenz
            # F-009: node-level Verlaufseintrag 'restored' schreiben, damit der
            # Ganz-Checklisten-Restore auf Knotenebene auditierbar ist.
            _write_restore_history(
                db=db, template_id=template_id, version=version, node=new_node,
                changed_by_id=user_id, node_version=latest_versions.get(nid, 0) + 1,
            )
            restored += 1

        tpl.current_version = version.version_number
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        log.exception(
            "Fehler beim Wiederherstellen der Checklisten-Version %s (Template %s) — "
            "Transaktion zurueckgerollt.",
            version_id, template_id,
        )
        raise HTTPException(
            500, "Wiederherstellung fehlgeschlagen — Arbeitskopie unveraendert."
        )

    log.info(
        "Checklisten-Version %s (%s) wiederhergestellt fuer Template %s durch %s — "
        "%d Knoten geloescht, %d neu angelegt.",
        version_id, version.version_number, template_id, user_id,
        deleted_count, restored,
    )
    return RestoreResult(
        template_id=template_id,
        version_id=version_id,
        version_number=version.version_number,
        restored_node_count=restored,
        deleted_node_count=deleted_count,
    )
