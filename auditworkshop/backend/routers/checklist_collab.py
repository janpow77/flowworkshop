"""
flowworkshop · routers/checklist_collab.py

Hybrid-Kollaboration fuer den KOM-Checklisten-Designer: Presence (wer ist
gerade an einer Checkliste), Node-Locking (kurzlebige Bearbeitungssperren je
Knoten) und Live-Updates ueber Server-Sent-Events (SSE).

Zielgruppe ist post-Workshop ein breiter Nutzerkreis, der GLEICHZEITIG an einer
Checkliste arbeitet — daher: jeder verbundene Client haelt einen offenen
SSE-Stream, sieht die anderen Bearbeiter (Presence) und erhaelt Knoten-
Aenderungen sowie Lock-Wechsel in Echtzeit.

Auth-Besonderheit (SSE)
-----------------------
Dieser Router hat — anders als der ``checklist_templates``-Router — KEINE
globale ``require_session``-Dependency. Grund: der SSE-Endpoint ``/events`` kann
nicht ueber den ``Authorization``-Header authentifiziert werden, weil der
Browser-``EventSource`` keine Header setzen kann. Stattdessen wird der Token als
Query-Parameter ``?token=...`` uebergeben und direkt ueber ``_load_session``
validiert. Alle uebrigen Endpunkte (Lock/Unlock/Locks/Presence) erzwingen die
Session weiterhin per Header ueber ``require_session(request)``.

Single-Worker-Limitierung: siehe services/checklist_events.py.
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import get_db
from models.checklist_template import (
    ChecklistTemplate,
    ChecklistTemplateNode,
    ChecklistNodeLock,
    MemberRole,
    TemplateStatus,
)
from models.registration import Registration
from routers.auth import require_session, _load_session
from routers.checklist_templates import (
    _get_member,
    _require_role,
    _session_user_id,
    _full_name,
)
from services.checklist_events import broker

router = APIRouter(prefix="/api/checklist-templates", tags=["checklist-collab"])
log = logging.getLogger(__name__)

# Lock-Lebensdauer: ein Lock laeuft 60s nach Erwerb/Erneuerung ab. Der Client
# erneuert ihn periodisch (z.B. alle ~30s); bleibt die Erneuerung aus (Tab
# geschlossen, Netz weg), gilt der Lock automatisch als frei.
_LOCK_TTL_SECONDS = 60

# Heartbeat-Intervall fuer den SSE-Stream — haelt Proxies/Browser-Timeouts
# auf Distanz, auch wenn gerade keine Fachevents anfallen.
_HEARTBEAT_SECONDS = 15.0


def _utcnow() -> datetime:
    """Naive UTC-Zeit (konsistent mit den tz-losen DateTime-Spalten)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── Helfer: Lock-Aufraeumung + Serialisierung ─────────────────────────────────

def _purge_expired_locks(template_id: str, db: Session) -> None:
    """Loescht abgelaufene Locks eines Templates (opportunistisch).

    Wird beim Lock-Erwerb und beim Locks-Abruf aufgerufen — abgelaufene Locks
    gelten als frei und sollen Folge-Erwerbe nicht blockieren."""
    db.query(ChecklistNodeLock).filter(
        ChecklistNodeLock.template_id == template_id,
        ChecklistNodeLock.expires_at <= _utcnow(),
    ).delete(synchronize_session=False)


def _active_locks(template_id: str, db: Session) -> list[ChecklistNodeLock]:
    """Liefert die nicht abgelaufenen Locks eines Templates."""
    return (
        db.query(ChecklistNodeLock)
        .filter(
            ChecklistNodeLock.template_id == template_id,
            ChecklistNodeLock.expires_at > _utcnow(),
        )
        .all()
    )


def _lock_out(lock: ChecklistNodeLock, regs: dict[str, Registration]) -> dict:
    """Serialisiert einen Lock inkl. Halter-Stammdaten (Name/Org/Bundesland)."""
    reg = regs.get(lock.locked_by_id)
    return {
        "node_id": lock.node_id,
        "template_id": lock.template_id,
        "locked_by_id": lock.locked_by_id,
        "locked_by_name": _full_name(reg),
        "organization": reg.organization if reg else None,
        "bundesland": reg.bundesland if reg else None,
        "locked_at": lock.locked_at.isoformat() if lock.locked_at else None,
        "expires_at": lock.expires_at.isoformat() if lock.expires_at else None,
    }


def _load_lock_regs(locks: list[ChecklistNodeLock], db: Session) -> dict[str, Registration]:
    """Laedt die Registration-Stammdaten der Lock-Halter als Map."""
    ids = {lk.locked_by_id for lk in locks if lk.locked_by_id}
    if not ids:
        return {}
    rows = db.query(Registration).filter(Registration.id.in_(ids)).all()
    return {r.id: r for r in rows}


def _require_view_access(template_id: str, user_id: str, db: Session) -> None:
    """Stellt sicher, dass der Nutzer das Template lesen darf.

    Mitglieder duerfen immer; bei veroeffentlichten Templates auch
    Nicht-Mitglieder. Andernfalls 404/403."""
    tpl = (
        db.query(ChecklistTemplate)
        .filter(ChecklistTemplate.id == template_id)
        .first()
    )
    if not tpl:
        raise HTTPException(404, "Checklisten-Template nicht gefunden.")
    member = _get_member(template_id, user_id, db)
    if not member and tpl.status != TemplateStatus.PUBLISHED.value:
        raise HTTPException(403, "Kein Zugriff auf dieses Checklisten-Template.")


# ── SSE-Stream: Presence + Live-Updates ───────────────────────────────────────

@router.get("/{template_id}/events")
async def stream_events(
    template_id: str, request: Request, token: str = "",
    db: Session = Depends(get_db),
):
    """SSE-Stream mit Presence-Join, aktivem Lock-Stand und Live-Events.

    Authentifizierung ueber ``?token=...`` (EventSource kann keine
    Authorization-Header senden). Beim Connect tritt der Nutzer der
    Presence-Registry bei und erhaelt ein initiales Event mit dem aktuellen
    Presence-Stand und den aktiven Locks. Danach werden Fachevents
    (node_created/updated/deleted/moved, lock_acquired/released, presence)
    gestreamt; ein Heartbeat-Kommentar haelt die Verbindung offen. Beim
    Disconnect verlaesst der Nutzer die Presence und seine eigenen Locks werden
    freigegeben (mit lock_released-Events)."""
    session = _load_session(token)
    if not session:
        raise HTTPException(401, "Nicht angemeldet (ungueltiger Token).")
    user_id = _session_user_id(session)

    # Zugriff pruefen (Mitglied oder veroeffentlichtes Template).
    _require_view_access(template_id, user_id, db)

    # Presence-Join mit Stammdaten aus der Session.
    broker.presence_join(
        template_id, user_id,
        name=session.get("name"),
        organization=session.get("organization"),
        bundesland=None,
    )
    # Bundesland nachreichen (steht nicht in der Session, nur in Registration).
    reg = db.query(Registration).filter(Registration.id == user_id).first()
    if reg is not None:
        broker.presence_join(
            template_id, user_id,
            name=session.get("name") or _full_name(reg),
            organization=session.get("organization") or reg.organization,
            bundesland=reg.bundesland,
        )

    # Aktive Locks fuer das Initial-Event laden.
    locks = _active_locks(template_id, db)
    lock_regs = _load_lock_regs(locks, db)
    initial_locks = [_lock_out(lk, lock_regs) for lk in locks]

    queue = broker.subscribe(template_id)

    # Anderen Subscribern mitteilen, dass ein Nutzer beigetreten ist.
    broker.publish(template_id, {
        "type": "presence",
        "event": "join",
        "user_id": user_id,
        "users": broker.presence_list(template_id),
    })

    async def event_generator():
        try:
            # Initiales Event: Presence-Stand + aktive Locks.
            init_payload = {
                "type": "init",
                "users": broker.presence_list(template_id),
                "locks": initial_locks,
            }
            yield f"data: {json.dumps(init_payload, default=str)}\n\n"

            while True:
                # Client-Disconnect erkennen (Browser-Tab geschlossen).
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(
                        queue.get(), timeout=_HEARTBEAT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    # Heartbeat-Kommentar gegen Proxy-/Browser-Timeouts.
                    yield ": ping\n\n"
                    broker.presence_touch(template_id, user_id)
                    continue
                yield f"data: {json.dumps(event, default=str)}\n\n"
        finally:
            # Aufraeumen: Subscriber abmelden, Presence verlassen, eigene Locks
            # freigeben. Eigener DB-Lauf, da die Request-Session evtl. schon zu
            # ist, wenn der Generator beim Disconnect endet.
            broker.unsubscribe(template_id, queue)
            broker.presence_leave(template_id, user_id)
            broker.publish(template_id, {
                "type": "presence",
                "event": "leave",
                "user_id": user_id,
                "users": broker.presence_list(template_id),
            })
            _release_own_locks_on_disconnect(template_id, user_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # nginx: SSE nicht puffern
        },
    )


def _release_own_locks_on_disconnect(template_id: str, user_id: str) -> None:
    """Gibt beim SSE-Disconnect alle Locks des Nutzers frei + publiziert.

    Oeffnet eine eigene DB-Session, da diese Funktion aus dem
    Generator-``finally`` heraus laeuft, wo die Request-Session bereits
    geschlossen sein kann."""
    from database import SessionLocal
    db = SessionLocal()
    try:
        own = (
            db.query(ChecklistNodeLock)
            .filter(
                ChecklistNodeLock.template_id == template_id,
                ChecklistNodeLock.locked_by_id == user_id,
            )
            .all()
        )
        node_ids = [lk.node_id for lk in own]
        if node_ids:
            db.query(ChecklistNodeLock).filter(
                ChecklistNodeLock.template_id == template_id,
                ChecklistNodeLock.locked_by_id == user_id,
            ).delete(synchronize_session=False)
            db.commit()
            for node_id in node_ids:
                broker.publish(template_id, {
                    "type": "lock_released",
                    "node_id": node_id,
                    "template_id": template_id,
                    "user_id": user_id,
                    "reason": "disconnect",
                })
    except Exception:  # noqa: BLE001 — Aufraeumen darf den Stream nicht stoeren
        log.exception("Lock-Freigabe beim Disconnect fehlgeschlagen (%s)", template_id)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
    finally:
        db.close()


# ── Node-Locking ──────────────────────────────────────────────────────────────

@router.post("/{template_id}/nodes/{node_id}/lock")
def acquire_lock(
    template_id: str, node_id: str, request: Request, db: Session = Depends(get_db),
):
    """Erwirbt oder erneuert einen Bearbeitungs-Lock auf einen Knoten (editor+).

    Ein aktiver Lock eines ANDEREN Nutzers fuehrt zu 409 (mit Halter-Infos). Ein
    eigener Lock wird verlaengert. ``expires_at`` = jetzt + 60s. Abgelaufene
    Locks werden vorab opportunistisch entfernt. Publiziert ``lock_acquired``."""
    session = require_session(request)
    user_id = _session_user_id(session)
    _require_role(template_id, user_id, MemberRole.EDITOR, db)

    # Knoten muss zum Template gehoeren.
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

    _purge_expired_locks(template_id, db)

    now = _utcnow()
    expires_at = now + timedelta(seconds=_LOCK_TTL_SECONDS)

    existing = (
        db.query(ChecklistNodeLock)
        .filter(ChecklistNodeLock.node_id == node_id)
        .first()
    )

    if existing:
        active = existing.expires_at > now
        if active and existing.locked_by_id != user_id:
            holder = (
                db.query(Registration)
                .filter(Registration.id == existing.locked_by_id)
                .first()
            )
            raise HTTPException(
                409,
                detail={
                    "message": "Knoten wird gerade von einer anderen Person bearbeitet.",
                    "locked_by_id": existing.locked_by_id,
                    "locked_by_name": _full_name(holder),
                    "organization": holder.organization if holder else None,
                    "bundesland": holder.bundesland if holder else None,
                    "expires_at": existing.expires_at.isoformat(),
                },
            )
        # Eigener (oder abgelaufener) Lock → uebernehmen/verlaengern.
        existing.locked_by_id = user_id
        existing.locked_at = now
        existing.expires_at = expires_at
        lock = existing
    else:
        lock = ChecklistNodeLock(
            id=str(uuid.uuid4()),
            node_id=node_id,
            template_id=template_id,
            locked_by_id=user_id,
            locked_at=now,
            expires_at=expires_at,
        )
        db.add(lock)

    db.commit()
    db.refresh(lock)

    regs = _load_lock_regs([lock], db)
    payload = _lock_out(lock, regs)
    broker.publish(template_id, {"type": "lock_acquired", "user_id": user_id, **payload})
    return payload


@router.delete("/{template_id}/nodes/{node_id}/lock", status_code=204)
def release_lock(
    template_id: str, node_id: str, request: Request, db: Session = Depends(get_db),
):
    """Gibt den eigenen Lock auf einen Knoten frei. Publiziert ``lock_released``.

    Nur der Halter (oder ein owner) darf freigeben — fremde aktive Locks bleiben
    geschuetzt."""
    session = require_session(request)
    user_id = _session_user_id(session)
    _require_role(template_id, user_id, MemberRole.EDITOR, db)

    lock = (
        db.query(ChecklistNodeLock)
        .filter(
            ChecklistNodeLock.node_id == node_id,
            ChecklistNodeLock.template_id == template_id,
        )
        .first()
    )
    if not lock:
        # Bereits frei — idempotent als Erfolg behandeln.
        return

    # Fremden, noch aktiven Lock nur ein owner aufbrechen lassen.
    if lock.locked_by_id != user_id and lock.expires_at > _utcnow():
        member = _get_member(template_id, user_id, db)
        if not member or member.role != MemberRole.OWNER.value:
            raise HTTPException(403, "Dieser Lock gehoert einer anderen Person.")

    db.delete(lock)
    db.commit()
    broker.publish(template_id, {
        "type": "lock_released",
        "node_id": node_id,
        "template_id": template_id,
        "user_id": user_id,
    })


@router.get("/{template_id}/locks")
def list_locks(template_id: str, request: Request, db: Session = Depends(get_db)):
    """Listet die aktiven (nicht abgelaufenen) Locks mit Halter-Infos.

    Raeumt vorab abgelaufene Locks opportunistisch auf."""
    session = require_session(request)
    user_id = _session_user_id(session)
    _require_view_access(template_id, user_id, db)

    _purge_expired_locks(template_id, db)
    db.commit()

    locks = _active_locks(template_id, db)
    regs = _load_lock_regs(locks, db)
    return [_lock_out(lk, regs) for lk in locks]


@router.get("/{template_id}/presence")
def list_presence(template_id: str, request: Request, db: Session = Depends(get_db)):
    """Liefert die aktuell ueber SSE verbundenen Nutzer (Presence-Registry).

    Optional — die Presence wird auch ueber den SSE-Stream selbst gepusht."""
    session = require_session(request)
    user_id = _session_user_id(session)
    _require_view_access(template_id, user_id, db)
    return broker.presence_list(template_id)
