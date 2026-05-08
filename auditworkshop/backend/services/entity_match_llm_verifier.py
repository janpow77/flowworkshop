"""Nightly LLM-Batch fuer EntityMatches mit niedriger Confidence (75-89).

Layer C — komplementaer zu Layer B (services/audit_match_verifier.py):

  - Layer B (on-demand, Audit-Report-Bau): pruefer-getriggerte Live-Verifikation
    Top-N ambivalente Cross-References pro Bericht. Latenz akzeptabel, weil
    pro Pruefer ~20 Refs ueblich sind.

  - Layer C (cron, hier): naechtlicher Batch ueber bis zu 500 EntityMatches
    der letzten 48 h. Schreibt das Verdict in EntityMatch.match_evidence
    und setzt rejected/confirmed_by_user_id, sodass der Audit-Report
    am naechsten Tag deutlich weniger Live-LLM-Latenz hat.

Persistenz:
  - Pro EntityMatch wird ``match.match_evidence['llm_verdict']`` gesetzt
    (idempotent — zweiter Run ueberspringt schon-verifizierte Matches).
  - match='no'                  -> match.rejected = True
  - match='yes' und confidence>=85 -> match.confirmed_by_user_id =
    'system:llm_batch'
  - match='unknown'             -> nichts setzen (bleibt offen fuer Pruefer)

Auto-Confirm-Schwelle 85 (statt 80 in Layer B): strenger im Batch, weil
der Pruefer im Audit-Report nicht mehr live drauf schauen wird.

Wiederverwendung Layer B: ``verify_match_pair`` aus audit_match_verifier
(ein LLM-Call pro Match). KEINE Code-Duplikation.

Per-Call-Timeout 30 s (statt 15 s in Layer B): Qwen3-14B kann in Spitzen
20-30 s pro Verdict brauchen, weil das Re-Ranker-Modell warm gefahren werden
muss. 60 s waere noch sicherer, aber 500 Matches * 60 s = 8.3 h — hart am
Tagesfenster. 30 s sind ein guter Kompromiss.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import desc, text
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from models.beneficiary_records import BeneficiaryRecord
from models.entities import CompanyEntity, EntityMatch
from models.entity_match_llm_run import EntityMatchLlmRun
from models.sanctions_entries import SanctionsEntry
from models.state_aid import StateAidAward
from services.audit_match_verifier import (
    LlmMatchVerdict,
    log_verdict_to_db,
    verify_match_pair,
)

log = logging.getLogger(__name__)


# ── Konstanten ───────────────────────────────────────────────────────────────


# Schwelle fuer Auto-Confirm: ueber dieser Konfidenz wird ein 'yes'-Verdict
# als confirmed_by_user_id='system:llm_batch' eingetragen. Strenger als
# Layer B (Default 80), weil der Pruefer den Audit-Report sonst gar nicht
# mehr live sehen wuerde.
AUTO_CONFIRM_CONFIDENCE = 85

# Sentinel fuer auto-confirmierte Matches. Layer 6d-Reject-Endpoint kann das
# ueberschreiben — der Pruefer kann jederzeit manuell ablehnen.
AUTO_CONFIRM_USER_ID = "system:llm_batch"

# Pseudo-Marker im match_evidence['llm_verdict'], damit ein zweiter Run
# einen schon verifizierten Match nicht erneut ans LLM gibt.
EVIDENCE_LLM_KEY = "llm_verdict"


# ── Datenklassen ─────────────────────────────────────────────────────────────


@dataclass
class BatchVerifyParams:
    """Parameter fuer ``run_batch_verification``.

    Defaults entsprechen dem nightly Cron-Modus (500 Matches/Nacht aus den
    letzten 2 Tagen). Der CLI/Admin-Trigger kann bewusst abweichen.
    """
    max_matches: int = 500
    score_min: float = 75.0
    score_max: float = 89.0
    only_recent_hours: int = 48
    only_unverified: bool = True
    per_call_timeout_s: float = 30.0
    overall_timeout_s: float = 7200.0   # 2 h Hard-Cap
    dry: bool = False                   # Trockenlauf, kein DB-Write

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BatchVerifyResult:
    """Ergebnis eines Batch-Laufs."""
    started_at: datetime
    finished_at: datetime | None
    total_eligible: int
    total_verified: int
    matches_confirmed: int
    matches_rejected: int
    matches_unknown: int
    skipped_due_to_timeout: int
    elapsed_s: float
    error: str | None = None
    run_id: int | None = None
    status: str = "running"   # 'running' | 'ok' | 'partial' | 'failed'
    verdicts: list[LlmMatchVerdict] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "total_eligible": self.total_eligible,
            "total_verified": self.total_verified,
            "matches_confirmed": self.matches_confirmed,
            "matches_rejected": self.matches_rejected,
            "matches_unknown": self.matches_unknown,
            "skipped_due_to_timeout": self.skipped_due_to_timeout,
            "elapsed_s": round(self.elapsed_s, 2),
            "error": self.error,
            "verdicts": [v.to_dict() for v in self.verdicts],
        }


# ── Eligible-Selection ───────────────────────────────────────────────────────


def select_eligible_matches(
    db: Session, params: BatchVerifyParams,
) -> list[EntityMatch]:
    """Liefert die Liste der EntityMatches, die fuer eine LLM-Verifikation
    in Frage kommen.

    Filter:
      - ``match_confidence`` zwischen ``params.score_min`` und ``params.score_max``
      - ``created_at > now() - interval 'X hours'`` (Default 48 h)
      - ``confirmed_by_user_id IS NULL`` und ``rejected = false`` (sofern
        ``only_unverified=True``)
      - NOCH NICHT vom LLM verifiziert (kein ``evidence['llm_verdict']``)

    Sortierung: ``created_at DESC, id DESC`` — neueste zuerst, damit
    grosse Backlogs ueber mehrere Naechte abgearbeitet werden.

    Limit: ``params.max_matches``.
    """
    cutoff = datetime.utcnow() - timedelta(
        hours=int(params.only_recent_hours or 48),
    )

    q = (
        db.query(EntityMatch)
        .filter(EntityMatch.match_confidence >= float(params.score_min))
        .filter(EntityMatch.match_confidence <= float(params.score_max))
        .filter(EntityMatch.created_at > cutoff)
    )

    if params.only_unverified:
        q = q.filter(
            EntityMatch.confirmed_by_user_id.is_(None),
            EntityMatch.rejected.is_(False),
        )

    # NOT EXISTS auf evidence['llm_verdict'] — wird ueber jsonb-Operator '?'
    # gemacht. Funktioniert nur, wenn match_evidence ein JSONB-Objekt ist;
    # NULL-Eintraege werden vom Filter erfasst (NOT TRUE -> kommt durch).
    q = q.filter(
        text(
            "(match_evidence IS NULL OR NOT (match_evidence ? :llm_key))"
        ).bindparams(llm_key=EVIDENCE_LLM_KEY)
    )

    q = q.order_by(desc(EntityMatch.created_at), desc(EntityMatch.id))
    q = q.limit(int(params.max_matches))
    return q.all()


# ── Source-Record Mapping ────────────────────────────────────────────────────


def _load_state_aid_record(
    db: Session, source_record_id: str,
) -> dict[str, Any] | None:
    """Holt einen StateAidAward und mappt die Felder fuer ``verify_match_pair``."""
    award = db.query(StateAidAward).filter(
        StateAidAward.id == str(source_record_id),
    ).first()
    if award is None:
        return None
    return {
        "name": award.beneficiary_name,
        "identifier": award.beneficiary_identifier,
        "country_code": award.country_code,
        "nuts_code": award.nuts_code,
        "nuts_label": award.nuts_label,
        "project_name": award.aid_measure_title,
        "aid_objective": award.aid_objective,
        "aid_amount_eur": (
            float(award.aid_amount_eur)
            if award.aid_amount_eur is not None else None
        ),
        "granting_authority": award.granting_authority,
        "source": "state_aid",
        "source_key": award.source_key,
    }


def _load_beneficiary_record(
    db: Session, source_record_id: str,
) -> dict[str, Any] | None:
    """Holt einen BeneficiaryRecord und mappt die Felder."""
    try:
        rec_id = int(source_record_id)
    except (TypeError, ValueError):
        return None
    rec = db.query(BeneficiaryRecord).filter(
        BeneficiaryRecord.id == rec_id,
    ).first()
    if rec is None:
        return None
    return {
        "name": rec.beneficiary_name,
        "identifier": rec.project_aktenzeichen,
        "country_code": rec.country_code,
        "nuts_code": rec.nuts_code,
        "bundesland": rec.bundesland,
        "location": rec.location,
        "project_name": rec.project_name,
        "kosten": (
            float(rec.cost_total)
            if rec.cost_total is not None else None
        ),
        "source": "beneficiary",
        "source_key": rec.source_key,
    }


def _load_sanctions_record(
    db: Session, source_record_id: str,
) -> dict[str, Any] | None:
    """Holt einen SanctionsEntry und mappt die Felder."""
    try:
        rec_id = int(source_record_id)
    except (TypeError, ValueError):
        return None
    rec = db.query(SanctionsEntry).filter(
        SanctionsEntry.id == rec_id,
    ).first()
    if rec is None:
        return None
    cc = None
    if rec.countries:
        cc = str(rec.countries).split(";")[0].strip().upper() or None
    return {
        "name": rec.name,
        "identifier": (
            str(rec.identifiers).split(";")[0].strip()
            if rec.identifiers else None
        ),
        "country_code": cc,
        "address": (
            str(rec.addresses).split(";")[0].strip()
            if rec.addresses else None
        ),
        "source": "sanctions",
        "source_key": rec.source_key,
    }


def _load_source_record(
    db: Session, source_module: str, source_record_id: str,
) -> dict[str, Any] | None:
    """Dispatcher fuer die drei Quell-Module."""
    if source_module == "state_aid":
        return _load_state_aid_record(db, source_record_id)
    if source_module == "beneficiary":
        return _load_beneficiary_record(db, source_record_id)
    if source_module == "sanctions":
        return _load_sanctions_record(db, source_record_id)
    return None


def _entity_to_record(ent: CompanyEntity) -> dict[str, Any]:
    """Mappt die kanonische CompanyEntity in das Klartext-Schema fuer
    ``verify_match_pair``.

    Wir nehmen die erste bekannte Adresse, wenn vorhanden.
    """
    address_str = None
    if isinstance(ent.addresses, list) and ent.addresses:
        first = ent.addresses[0]
        if isinstance(first, dict):
            parts = [
                first.get("street") or "",
                first.get("postal_code") or "",
                first.get("city") or "",
            ]
            address_str = " ".join(p for p in parts if p).strip() or None

    identifier = None
    if isinstance(ent.identifiers, dict):
        # Erstes Bucket, erstes Element
        for _bucket, vals in ent.identifiers.items():
            if isinstance(vals, list) and vals:
                identifier = vals[0]
                break
            if isinstance(vals, str) and vals:
                identifier = vals
                break

    return {
        "name": ent.canonical_name,
        "identifier": identifier,
        "country_code": ent.country_code,
        "address": address_str,
        "lei": ent.lei,
        "source": "entity_master",
    }


# ── Per-Match-Verifikation ───────────────────────────────────────────────────


async def verify_match_via_llm(
    db: Session,
    match: EntityMatch,
    *,
    timeout_s: float = 30.0,
    dry: bool = False,
) -> LlmMatchVerdict | None:
    """Fuehrt EINE LLM-Verifikation fuer einen EntityMatch aus.

    Schritte:
      1. Hole CompanyEntity (kanonische Daten).
      2. Hole Source-Record (state_aid Award / beneficiary / sanctions).
      3. Baue dict-Pair fuer ``verify_match_pair`` (Layer B).
      4. Persistiere Verdict in ``match.match_evidence['llm_verdict']``.
      5. Bei match='no'                 -> rejected = True
      6. Bei match='yes' & conf>=85     -> confirmed_by_user_id = 'system:llm_batch'
      7. Bei match='unknown'            -> nichts setzen
      8. Pro Verifikation in LlmQuestionLog persistieren (best-effort).

    Liefert ``None``, wenn:
      - die Source-Records nicht aufloesbar sind
      - der LLM-Stream leer/Timeout war (ohne Fallback-Verdict)

    ``dry=True`` umgeht jegliche DB-Writes — nur LLM-Call und Verdict.
    """
    entity = db.query(CompanyEntity).filter(
        CompanyEntity.id == match.entity_id,
    ).first()
    if entity is None:
        log.warning(
            "verify_match_via_llm: Entity %s nicht gefunden (match_id=%s)",
            match.entity_id, match.id,
        )
        return None

    source_record = _load_source_record(
        db, match.source_module, match.source_record_id,
    )
    if source_record is None:
        log.warning(
            "verify_match_via_llm: Source-Record %s/%s nicht gefunden (match_id=%s)",
            match.source_module, match.source_record_id, match.id,
        )
        return None

    record_a = _entity_to_record(entity)
    record_b = source_record

    try:
        verdict = await verify_match_pair(
            record_a, record_b,
            cross_ref_index=int(match.id),
            timeout_s=timeout_s,
        )
    except Exception as exc:  # noqa: BLE001
        log.exception(
            "verify_match_via_llm: LLM-Aufruf fuer match_id=%s fehlgeschlagen: %s",
            match.id, exc,
        )
        return None

    if verdict is None:
        return None

    # ── Persistierung ────────────────────────────────────────────────────────
    if dry:
        return verdict

    # 4. Verdict in match_evidence['llm_verdict']
    evidence = match.match_evidence
    if not isinstance(evidence, dict):
        evidence = {}
    evidence[EVIDENCE_LLM_KEY] = {
        "match": verdict.match,
        "confidence": int(verdict.confidence),
        "reason": verdict.reason,
        "model_name": verdict.model_name or "",
        "verified_at": datetime.utcnow().isoformat(),
        "elapsed_ms": int(verdict.elapsed_ms),
        "source": "entity_match_batch",
    }
    match.match_evidence = evidence
    flag_modified(match, "match_evidence")

    # 5./6./7. Match-Status anhand Verdict setzen
    if verdict.match == "no":
        match.rejected = True
    elif (
        verdict.match == "yes"
        and int(verdict.confidence) >= AUTO_CONFIRM_CONFIDENCE
    ):
        match.confirmed_by_user_id = AUTO_CONFIRM_USER_ID
        match.confirmed_at = datetime.utcnow()
        match.rejected = False

    db.add(match)

    # 8. Per-Verdict in LlmQuestionLog (best-effort, nutzt Layer-B-Helper).
    # Wir konstruieren ein „pseudo-cross-ref" mit den Records, damit die
    # bestehende ``log_verdict_to_db``-Funktion funktioniert. Alternative:
    # eigener Logger — hier bewusst Wiederverwendung.
    try:
        # Pseudo-Cross-Ref-Objekt — duck-typed via SimpleNamespace.
        from types import SimpleNamespace
        pseudo_cr = SimpleNamespace(
            type="entity_match_batch",
            evidence={
                "register_a": {
                    "register": "entity_master",
                    "value": record_a.get("name"),
                    "country_code": record_a.get("country_code"),
                },
                "register_b": {
                    "register": match.source_module,
                    "value": record_b.get("name"),
                    "country_code": record_b.get("country_code"),
                    "field": "source_record_id",
                },
            },
        )
        log_verdict_to_db(
            cross_ref=pseudo_cr,
            verdict=verdict,
            user_id=None,
        )
    except Exception:  # noqa: BLE001
        log.exception("LLM-Logging fuer match_id=%s fehlgeschlagen (non-blocking)", match.id)

    return verdict


# ── Batch-Runner ─────────────────────────────────────────────────────────────


async def _run_batch_verification_async(
    db: Session, params: BatchVerifyParams,
) -> BatchVerifyResult:
    """Async-Hauptfunktion. Iteriert eligible Matches und ruft
    ``verify_match_via_llm`` sequentiell auf (LLM-GPU ist single-tenant).

    Schreibt Zwischenstand alle 50 Records via ``db.commit()``, damit ein
    Crash nicht 500 Verdicts verliert.
    """
    started = datetime.utcnow()
    started_monotonic = time.monotonic()

    # 1. Eligible-Set bestimmen
    try:
        eligible = select_eligible_matches(db, params)
    except Exception as exc:  # noqa: BLE001
        log.exception("select_eligible_matches fehlgeschlagen")
        return BatchVerifyResult(
            started_at=started,
            finished_at=datetime.utcnow(),
            total_eligible=0,
            total_verified=0,
            matches_confirmed=0,
            matches_rejected=0,
            matches_unknown=0,
            skipped_due_to_timeout=0,
            elapsed_s=time.monotonic() - started_monotonic,
            error=f"select_eligible_matches: {exc}",
            status="failed",
        )

    total_eligible = len(eligible)
    log.info(
        "Entity-Match-LLM-Batch: %d eligible Matches (range %.0f..%.0f, "
        "recent_hours=%d, max=%d)",
        total_eligible, params.score_min, params.score_max,
        params.only_recent_hours, params.max_matches,
    )

    result = BatchVerifyResult(
        started_at=started,
        finished_at=None,
        total_eligible=total_eligible,
        total_verified=0,
        matches_confirmed=0,
        matches_rejected=0,
        matches_unknown=0,
        skipped_due_to_timeout=0,
        elapsed_s=0.0,
        status="running",
    )

    if not eligible:
        result.status = "ok"
        result.finished_at = datetime.utcnow()
        result.elapsed_s = time.monotonic() - started_monotonic
        return result

    # 2. Sequentielle Verifikation, mit Hard-Cap auf overall_timeout_s
    deadline = started_monotonic + float(params.overall_timeout_s)

    for idx, match in enumerate(eligible):
        # Globaler Timeout-Schutz
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            skipped = total_eligible - result.total_verified
            result.skipped_due_to_timeout = skipped
            log.warning(
                "Entity-Match-LLM-Batch: Overall-Timeout erreicht. "
                "%d/%d Matches uebersprungen.",
                skipped, total_eligible,
            )
            break

        call_timeout = min(
            float(params.per_call_timeout_s),
            max(2.0, remaining),
        )

        try:
            verdict = await verify_match_via_llm(
                db, match,
                timeout_s=call_timeout,
                dry=params.dry,
            )
        except Exception as exc:  # noqa: BLE001
            log.exception(
                "verify_match_via_llm: match_id=%s — Worker-Exception: %s",
                match.id, exc,
            )
            verdict = None

        if verdict is not None:
            result.total_verified += 1
            result.verdicts.append(verdict)
            if verdict.match == "yes" and int(verdict.confidence) >= AUTO_CONFIRM_CONFIDENCE:
                result.matches_confirmed += 1
            elif verdict.match == "no":
                result.matches_rejected += 1
            else:
                # 'unknown' oder 'yes' mit zu niedriger Confidence
                result.matches_unknown += 1

        # Zwischen-Commit alle 50 Records (sofern nicht dry).
        if not params.dry and (idx + 1) % 50 == 0:
            try:
                db.commit()
                log.info(
                    "Entity-Match-LLM-Batch: %d/%d verifiziert "
                    "(confirmed=%d, rejected=%d, unknown=%d)",
                    result.total_verified, total_eligible,
                    result.matches_confirmed, result.matches_rejected,
                    result.matches_unknown,
                )
            except Exception:  # noqa: BLE001
                log.exception("Zwischen-Commit fehlgeschlagen")
                db.rollback()

    # Final-Commit
    if not params.dry:
        try:
            db.commit()
        except Exception:  # noqa: BLE001
            log.exception("Final-Commit fehlgeschlagen")
            db.rollback()
    else:
        db.rollback()

    result.finished_at = datetime.utcnow()
    result.elapsed_s = time.monotonic() - started_monotonic

    # Status-Aggregation
    if result.skipped_due_to_timeout > 0 and result.total_verified > 0:
        result.status = "partial"
    elif result.skipped_due_to_timeout > 0 and result.total_verified == 0:
        result.status = "failed"
    else:
        result.status = "ok"

    log.info(
        "Entity-Match-LLM-Batch %s: eligible=%d verified=%d "
        "confirmed=%d rejected=%d unknown=%d skipped=%d in %.1fs",
        result.status,
        result.total_eligible, result.total_verified,
        result.matches_confirmed, result.matches_rejected,
        result.matches_unknown, result.skipped_due_to_timeout,
        result.elapsed_s,
    )
    return result


def run_batch_verification(
    db: Session, params: BatchVerifyParams, *,
    triggered_by: str = "cron",
) -> BatchVerifyResult:
    """Synchrone Hauptfunktion mit Run-Persistierung.

    Legt einen ``EntityMatchLlmRun``-Eintrag an (status='running'), startet
    die Async-Verifikation und aktualisiert den Run-Eintrag mit dem Ergebnis
    (status='ok'/'partial'/'failed').

    Diese Funktion ist die kanonische Einstiegsstelle fuer Cron, Admin-API
    und CLI. Sie ist synchron, weil der Scheduler ``asyncio.to_thread``
    nutzt und CLI/Admin-API eh blockend sein koennen.
    """
    # Run-Eintrag vorab anlegen (status='running')
    run = EntityMatchLlmRun(
        triggered_by=triggered_by,
        status="running",
        parameters=params.to_dict(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    run_id = run.id

    # Async-Loop ausfuehren — wir rufen das aus einem Sync-Kontext, daher
    # asyncio.run. Wenn der Aufrufer schon in einer Event-Loop laeuft
    # (z.B. innerhalb von FastAPI-Endpoint), muss er ``_run_batch_verification_async``
    # direkt awaiten.
    try:
        result = asyncio.run(_run_batch_verification_async(db, params))
        result.run_id = run_id
    except Exception as exc:  # noqa: BLE001
        log.exception("Entity-Match-LLM-Batch-Loop fehlgeschlagen")
        run.status = "failed"
        run.finished_at = datetime.utcnow()
        run.error_message = str(exc)[:2000]
        db.commit()
        return BatchVerifyResult(
            started_at=run.started_at or datetime.utcnow(),
            finished_at=datetime.utcnow(),
            total_eligible=0,
            total_verified=0,
            matches_confirmed=0,
            matches_rejected=0,
            matches_unknown=0,
            skipped_due_to_timeout=0,
            elapsed_s=0.0,
            error=str(exc),
            run_id=run_id,
            status="failed",
        )

    # Run-Eintrag aktualisieren
    try:
        run.finished_at = result.finished_at or datetime.utcnow()
        run.status = result.status
        run.total_eligible = result.total_eligible
        run.total_verified = result.total_verified
        run.matches_confirmed = result.matches_confirmed
        run.matches_rejected = result.matches_rejected
        run.matches_unknown = result.matches_unknown
        run.skipped_due_to_timeout = result.skipped_due_to_timeout
        if result.error:
            run.error_message = result.error[:2000]
        db.commit()
    except Exception:  # noqa: BLE001
        log.exception("Run-Update fehlgeschlagen (non-blocking)")
        db.rollback()

    return result


__all__ = [
    "AUTO_CONFIRM_CONFIDENCE",
    "AUTO_CONFIRM_USER_ID",
    "EVIDENCE_LLM_KEY",
    "BatchVerifyParams",
    "BatchVerifyResult",
    "_load_source_record",
    "run_batch_verification",
    "select_eligible_matches",
    "verify_match_via_llm",
]
