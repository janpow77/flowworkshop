"""
flowworkshop · routers/entities.py

Phase 6d — REST-API fuer das Entity-Resolution-Modul.

Public lesbar:
- ``GET /api/entities/search?q=...``: Master-Suche, Frontend-Autocomplete
- ``GET /api/entities/{id}``: Detail einer Entity mit allen Matches und
  Hierarchie

Admin-only:
- ``POST /api/entities/{id}/match/{match_id}/confirm``
- ``POST /api/entities/{id}/match/{match_id}/reject``
- ``POST /api/admin/entity-resolution/rebuild?module=...``: Trigger
  Rebuild ueber alle Module (synchron, nur fuer Demo-Setup)
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from models.entities import CompanyEntity, EntityMatch
from models.entity_match_llm_run import EntityMatchLlmRun
from routers.auth import require_admin, require_session
from services.entity_match_llm_verifier import (
    BatchVerifyParams,
    run_batch_verification,
)
from services.entity_resolution import (
    rebuild_entities_from_beneficiaries,
    rebuild_entities_from_sanctions,
    rebuild_entities_from_state_aid,
)
from services.state_aid_service import normalize_company_name

log = logging.getLogger(__name__)


router = APIRouter(prefix="/api/entities", tags=["entities"])


# ── Schemas ───────────────────────────────────────────────────────────────────


class EntitySearchHit(BaseModel):
    id: int
    canonical_name: str
    canonical_name_normalized: str
    entity_type: str
    country_code: str | None
    lei: str | None
    match_count: int
    has_state_aid: bool
    has_beneficiary: bool
    has_sanctions: bool

    model_config = {"from_attributes": True}


class EntityMatchInfo(BaseModel):
    id: int
    source_module: str
    source_record_id: str
    source_table: str
    match_method: str
    match_confidence: float
    match_evidence: dict | None
    confirmed_by_user_id: str | None
    confirmed_at: datetime | None
    rejected: bool
    created_at: datetime | None


class EntityDetail(BaseModel):
    id: int
    canonical_name: str
    canonical_name_normalized: str
    entity_type: str
    country_code: str | None
    lei: str | None
    identifiers: dict | None
    addresses: list[dict] | None
    parent_entity_id: int | None
    ultimate_parent_entity_id: int | None
    parent: dict | None
    ultimate_parent: dict | None
    children: list[dict]
    matches: list[EntityMatchInfo]
    discovered_at: datetime | None
    last_seen_at: datetime | None


# ── Helpers ───────────────────────────────────────────────────────────────────


def _entity_minimal(ent: CompanyEntity | None) -> dict | None:
    if ent is None:
        return None
    return {
        "id": ent.id,
        "canonical_name": ent.canonical_name,
        "lei": ent.lei,
        "country_code": ent.country_code,
    }


def _serialize_match(m: EntityMatch) -> EntityMatchInfo:
    return EntityMatchInfo(
        id=m.id,
        source_module=m.source_module,
        source_record_id=m.source_record_id,
        source_table=m.source_table,
        match_method=m.match_method,
        match_confidence=float(m.match_confidence),
        match_evidence=m.match_evidence if isinstance(m.match_evidence, dict) else None,
        confirmed_by_user_id=m.confirmed_by_user_id,
        confirmed_at=m.confirmed_at,
        rejected=bool(m.rejected),
        created_at=m.created_at,
    )


# ── Search ────────────────────────────────────────────────────────────────────


@router.get("/search")
def search_entities(
    q: str = Query("", min_length=0, max_length=200),
    country_code: str | None = Query(None, max_length=3),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _session: dict = Depends(require_session),
) -> dict:
    """Master-Suche fuer Entity-Autocomplete.

    Strategie: ILIKE-Vorfilter auf normalisierte Form (oder Name) — bei
    leerem Query liefert die Top-N nach last_seen_at. Pro Treffer wird die
    Anzahl Matches und das Vorhandensein von Module-Treffern angegeben.
    """
    qn = normalize_company_name(q) if q else ""
    base = db.query(CompanyEntity)
    if qn:
        # Wir suchen nach jedem nicht-trivialen Token im normalisierten Namen
        tokens = [t for t in qn.split() if len(t) >= 2]
        if tokens:
            ors = [
                CompanyEntity.canonical_name_normalized.ilike(f"%{t}%")
                for t in tokens[:5]
            ]
            base = base.filter(or_(*ors))
    if country_code:
        cc = country_code.upper()
        base = base.filter(
            or_(
                CompanyEntity.country_code == cc,
                CompanyEntity.country_code.is_(None),
            ),
        )

    rows = (
        base.order_by(CompanyEntity.last_seen_at.desc().nullslast())
        .limit(int(limit))
        .all()
    )
    if not rows:
        return {"count": 0, "results": []}

    # Match-Aggregat in einem Sweep statt N+1
    ids = [r.id for r in rows]
    counts: dict[int, int] = {i: 0 for i in ids}
    has_sa: dict[int, bool] = {i: False for i in ids}
    has_ben: dict[int, bool] = {i: False for i in ids}
    has_sanc: dict[int, bool] = {i: False for i in ids}
    if ids:
        match_rows = (
            db.query(
                EntityMatch.entity_id,
                EntityMatch.source_module,
            )
            .filter(
                EntityMatch.entity_id.in_(ids),
                EntityMatch.rejected.is_(False),
            )
            .all()
        )
        for r in match_rows:
            counts[r.entity_id] = counts.get(r.entity_id, 0) + 1
            if r.source_module == "state_aid":
                has_sa[r.entity_id] = True
            elif r.source_module == "beneficiary":
                has_ben[r.entity_id] = True
            elif r.source_module == "sanctions":
                has_sanc[r.entity_id] = True

    results = []
    for r in rows:
        results.append(EntitySearchHit(
            id=r.id,
            canonical_name=r.canonical_name,
            canonical_name_normalized=r.canonical_name_normalized,
            entity_type=r.entity_type,
            country_code=r.country_code,
            lei=r.lei,
            match_count=counts.get(r.id, 0),
            has_state_aid=has_sa.get(r.id, False),
            has_beneficiary=has_ben.get(r.id, False),
            has_sanctions=has_sanc.get(r.id, False),
        ).model_dump())

    return {"count": len(results), "results": results}


# ── Detail ────────────────────────────────────────────────────────────────────


@router.get("/{entity_id}")
def get_entity(
    entity_id: int,
    db: Session = Depends(get_db),
    _session: dict = Depends(require_session),
) -> dict:
    """Detail einer Entity mit allen aktiven Matches und Konzern-Hierarchie."""
    ent = db.get(CompanyEntity, int(entity_id))
    if ent is None:
        raise HTTPException(404, f"Entity {entity_id} nicht gefunden.")

    parent = None
    ultimate_parent = None
    if ent.parent_entity_id:
        parent = db.get(CompanyEntity, int(ent.parent_entity_id))
    if ent.ultimate_parent_entity_id:
        ultimate_parent = db.get(
            CompanyEntity, int(ent.ultimate_parent_entity_id),
        )

    children = (
        db.query(CompanyEntity)
        .filter(CompanyEntity.parent_entity_id == ent.id)
        .order_by(CompanyEntity.canonical_name)
        .limit(50)
        .all()
    )

    matches = (
        db.query(EntityMatch)
        .filter(EntityMatch.entity_id == ent.id)
        .order_by(EntityMatch.match_confidence.desc(), EntityMatch.id.desc())
        .all()
    )

    detail = EntityDetail(
        id=ent.id,
        canonical_name=ent.canonical_name,
        canonical_name_normalized=ent.canonical_name_normalized,
        entity_type=ent.entity_type,
        country_code=ent.country_code,
        lei=ent.lei,
        identifiers=ent.identifiers if isinstance(ent.identifiers, dict) else None,
        addresses=ent.addresses if isinstance(ent.addresses, list) else None,
        parent_entity_id=ent.parent_entity_id,
        ultimate_parent_entity_id=ent.ultimate_parent_entity_id,
        parent=_entity_minimal(parent),
        ultimate_parent=_entity_minimal(ultimate_parent),
        children=[
            _entity_minimal(c) for c in children if c is not None
        ],
        matches=[_serialize_match(m) for m in matches],
        discovered_at=ent.discovered_at,
        last_seen_at=ent.last_seen_at,
    )
    return detail.model_dump()


# ── Confirm / Reject ──────────────────────────────────────────────────────────


@router.post("/{entity_id}/match/{match_id}/confirm")
def confirm_match(
    entity_id: int,
    match_id: int,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Pruefer bestaetigt ein Match — sichert die Zuordnung."""
    m = (
        db.query(EntityMatch)
        .filter(
            EntityMatch.id == int(match_id),
            EntityMatch.entity_id == int(entity_id),
        )
        .first()
    )
    if m is None:
        raise HTTPException(404, "Match nicht gefunden.")
    m.confirmed_by_user_id = str(session.get("user_id") or "")[:36]
    m.confirmed_at = datetime.utcnow()
    m.rejected = False
    db.commit()
    return {
        "id": m.id,
        "entity_id": m.entity_id,
        "confirmed_by_user_id": m.confirmed_by_user_id,
        "confirmed_at": m.confirmed_at.isoformat() if m.confirmed_at else None,
        "rejected": m.rejected,
    }


@router.post("/{entity_id}/match/{match_id}/reject")
def reject_match(
    entity_id: int,
    match_id: int,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Pruefer markiert ein Match als falsch — Audit-Trail bleibt erhalten."""
    m = (
        db.query(EntityMatch)
        .filter(
            EntityMatch.id == int(match_id),
            EntityMatch.entity_id == int(entity_id),
        )
        .first()
    )
    if m is None:
        raise HTTPException(404, "Match nicht gefunden.")
    m.rejected = True
    m.confirmed_at = None
    m.confirmed_by_user_id = str(session.get("user_id") or "")[:36]
    db.commit()
    return {
        "id": m.id,
        "entity_id": m.entity_id,
        "rejected": True,
        "confirmed_by_user_id": m.confirmed_by_user_id,
    }


# ── Admin: Rebuild ────────────────────────────────────────────────────────────


# Wir brauchen einen separaten Router fuer /api/admin/entity-resolution/...
admin_router = APIRouter(
    prefix="/api/admin/entity-resolution",
    tags=["entities-admin"],
)


def _do_rebuild(db: Session, module: str, dry: bool, limit: int | None) -> dict:
    out: dict = {"module": module, "dry": dry}
    if module in ("state_aid", "all"):
        out["state_aid"] = rebuild_entities_from_state_aid(db, dry=dry, limit=limit)
    if module in ("beneficiary", "all"):
        out["beneficiary"] = rebuild_entities_from_beneficiaries(db, dry=dry, limit=limit)
    if module in ("sanctions", "all"):
        out["sanctions"] = rebuild_entities_from_sanctions(db, dry=dry, limit=limit)
    return out


def _rebuild_in_background(module: str, dry: bool, limit: int | None) -> None:
    """Rebuild mit EIGENER DB-Session (die Request-Session ist nach dem
    Response bereits geschlossen)."""
    db = SessionLocal()
    try:
        out = _do_rebuild(db, module, dry, limit)
        log.info("Entity-Rebuild (Hintergrund) abgeschlossen: %s", out)
    except Exception:
        log.exception("Entity-Rebuild (Hintergrund) fehlgeschlagen (module=%s)", module)
    finally:
        db.close()


@admin_router.post("/rebuild")
def admin_rebuild(
    background_tasks: BackgroundTasks,
    module: Literal["state_aid", "beneficiary", "sanctions", "all"] = Query("all"),
    dry: bool = Query(False, description="Trockenlauf — keine Schreibvorgaenge."),
    limit: int | None = Query(
        None, ge=1,
        description="Maximale Anzahl Records pro Modul — fuer schnelle Tests.",
    ),
    background: bool = Query(
        False,
        description="Im Hintergrund ausfuehren (HTTP-Worker nicht blockieren); "
                    "Fortschritt in den Backend-Logs.",
    ),
    _session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Triggert einen Rebuild der Entity-Resolution.

    Standard ist synchron (kleine ``limit``/``module``-Filter nutzen). Bei
    grossen Bestaenden ``background=true`` setzen, damit der HTTP-Worker nicht
    blockiert — oder ``scripts/rebuild_entity_resolution.py`` per CLI nutzen.
    """
    log.info(
        "Entity-Rebuild ausgeloest: module=%s dry=%s limit=%s background=%s",
        module, dry, limit, background,
    )
    if background:
        background_tasks.add_task(_rebuild_in_background, module, dry, limit)
        return {
            "status": "gestartet",
            "background": True,
            "module": module,
            "dry": dry,
            "hinweis": "Rebuild laeuft im Hintergrund. Fortschritt in den Backend-Logs; "
                       "fuer grosse Bestaende ist scripts/rebuild_entity_resolution.py empfohlen.",
        }
    out = _do_rebuild(db, module, dry, limit)
    log.info("Entity-Rebuild abgeschlossen: %s", out)
    return out


# ── Layer C: Nightly LLM-Verifikations-Batch ─────────────────────────────────


class LlmVerifyBatchRequest(BaseModel):
    """Body fuer ``/llm-verify-batch`` — alle Felder optional."""
    max_matches: int = 500
    score_min: float = 75.0
    score_max: float = 89.0
    only_recent_hours: int = 48
    only_unverified: bool = True
    per_call_timeout_s: float = 30.0
    overall_timeout_s: float = 7200.0
    dry: bool = False
    background: bool = False  # True = im Hintergrund, Status via GET /llm-runs


def _llm_batch_in_background(params: BatchVerifyParams, triggered_by: str) -> None:
    """Batch-Lauf mit EIGENER DB-Session (Request-Session ist nach dem
    Response geschlossen). Der Lauf protokolliert sich selbst in
    workshop_entity_match_llm_runs → Status via GET /llm-runs."""
    db = SessionLocal()
    try:
        result = run_batch_verification(db, params, triggered_by=triggered_by)
        log.info("Entity-Match-LLM-Batch (Hintergrund) fertig: %s", result.to_dict())
    except Exception:
        log.exception("Entity-Match-LLM-Batch (Hintergrund) fehlgeschlagen")
    finally:
        db.close()


@admin_router.post("/llm-verify-batch")
def admin_llm_verify_batch(
    body: LlmVerifyBatchRequest,
    background_tasks: BackgroundTasks,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Triggert den LLM-Verifikations-Batch (Admin-only).

    Standard ist synchron — bei 500 Matches kann der Lauf mehrere Minuten bis
    Stunden dauern, daher in Tests mit ``max_matches`` klein anfangen oder
    ``dry=True``. Mit ``background=true`` laeuft der Batch im Hintergrund (der
    HTTP-Worker wird nicht blockiert); der Fortschritt ist ueber
    ``GET /llm-runs`` abrufbar. Fuer grosse Laeufe alternativ
    ``scripts/entity_match_llm_batch.py`` per CLI.
    """
    user_id = str(session.get("user_id") or "unknown")[:36]
    triggered_by = f"admin:{user_id}"

    params = BatchVerifyParams(
        max_matches=int(body.max_matches),
        score_min=float(body.score_min),
        score_max=float(body.score_max),
        only_recent_hours=int(body.only_recent_hours),
        only_unverified=bool(body.only_unverified),
        per_call_timeout_s=float(body.per_call_timeout_s),
        overall_timeout_s=float(body.overall_timeout_s),
        dry=bool(body.dry),
    )

    log.info(
        "Entity-Match-LLM-Batch ausgeloest (%s): max=%d recent=%dh dry=%s background=%s",
        triggered_by, params.max_matches, params.only_recent_hours, params.dry, body.background,
    )
    if body.background:
        background_tasks.add_task(_llm_batch_in_background, params, triggered_by)
        return {
            "status": "gestartet",
            "background": True,
            "hinweis": "Batch laeuft im Hintergrund — Status ueber GET /llm-runs abrufbar.",
        }
    result = run_batch_verification(db, params, triggered_by=triggered_by)
    return result.to_dict()


@admin_router.get("/llm-runs")
def admin_llm_runs(
    limit: int = Query(20, ge=1, le=200),
    _session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Liste der letzten LLM-Verifikations-Batch-Laeufe (Audit-Trail)."""
    rows = (
        db.query(EntityMatchLlmRun)
        .order_by(EntityMatchLlmRun.started_at.desc())
        .limit(int(limit))
        .all()
    )
    runs = []
    for r in rows:
        runs.append({
            "id": r.id,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "triggered_by": r.triggered_by,
            "status": r.status,
            "total_eligible": r.total_eligible,
            "total_verified": r.total_verified,
            "matches_confirmed": r.matches_confirmed,
            "matches_rejected": r.matches_rejected,
            "matches_unknown": r.matches_unknown,
            "skipped_due_to_timeout": r.skipped_due_to_timeout,
            "parameters": r.parameters,
            "error_message": r.error_message,
        })
    return {"count": len(runs), "runs": runs}
