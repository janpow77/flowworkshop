"""
flowworkshop · routers/state_aid.py

REST-API fuer das EU-Beihilfe-Transparenzregister (Plan §10).

Oeffentlich lesbar (Plan §13: alle Daten stammen aus Art. 9 Abs. 1 VO 651/2014
publizierten Quellen). Schreib-/Admin-Endpoints liegen unter `require_admin`.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import re
import time
from collections import deque
from datetime import date, datetime
from decimal import Decimal
from threading import Lock
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func as sql_func
from sqlalchemy.orm import Session

from database import get_db
from models.state_aid import StateAidAward, StateAidHarvestRun, StateAidSource
from routers.auth import require_admin
from services.state_aid_harvester import HarvestParams, run_harvest, _default_source_key
from services.state_aid_llm import (
    HitStats,
    compute_stats,
    parse_question,
    relax_filters,
    stream_summary,
)
from services.state_aid_service import (
    ISO3_TO_ISO2,
    _escape_like,
    aggregate_for_map,
    fuzzy_match_company,
    normalize_company_name,
)
from services.state_aid_validator import (
    get_last_report,
    persist_report,
    run_validation,
)

router = APIRouter(prefix="/api/state-aid", tags=["state-aid"])
log = logging.getLogger(__name__)


# ── Rate-Limiter ─────────────────────────────────────────────────────────────
# In-Memory Sliding-Window-Rate-Limiter fuer LLM- und Such-Endpoints.
# Workshop-Demo: ein Worker, in-process reicht. Bei Skalierung auf mehrere
# Worker waere ein redis-basierter Limiter (z.B. slowapi) angemessen.

# Limits pro (Endpoint, Bucket-Key):
#   /ask    -> 6 Requests / 60s   (zwei LLM-Calls pro Request, GPU-Last)
#   /search -> 60 Requests / 60s  (kein LLM, aber DB-Last)
_RATE_LIMIT_BUCKETS: dict[str, deque[float]] = {}
_RATE_LIMIT_LOCK = Lock()
_RATE_LIMIT_WINDOWS: dict[str, tuple[int, float]] = {
    # endpoint -> (max_calls, window_seconds)
    "ask": (6, 60.0),
    "search": (60, 60.0),
}


def _rate_limit_key(endpoint: str, request: Request) -> str:
    """Bucket-Key: bevorzugt user_id, fallback ip_hash, fallback raw-ip.

    Wird fuer beide oeffentliche Endpoints verwendet. Anonyme Nutzer landen
    im IP-basierten Bucket — eine echte Demo-Session laeuft sowieso unter
    einem registrierten Account.
    """
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return f"{endpoint}:user:{user_id}"
    # IP aus X-Forwarded-For (Reverse-Proxy) bevorzugen.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        ip = fwd.split(",")[0].strip()
    elif request.client:
        ip = request.client.host
    else:
        ip = "unknown"
    return f"{endpoint}:ip:{ip}"


def _check_rate_limit(endpoint: str, request: Request) -> None:
    """Wirft HTTP 429, wenn der Bucket des Aufrufers das Limit ueberschreitet.

    Sliding-Window: alte Eintraege (> Window) werden vor jedem Check verworfen.
    Antwort enthaelt `Retry-After`-Header (Sekunden bis der aelteste Eintrag
    aus dem Fenster faellt).
    """
    cfg = _RATE_LIMIT_WINDOWS.get(endpoint)
    if cfg is None:
        return
    max_calls, window = cfg
    key = _rate_limit_key(endpoint, request)
    now = time.monotonic()
    with _RATE_LIMIT_LOCK:
        bucket = _RATE_LIMIT_BUCKETS.setdefault(key, deque())
        # Alte Eintraege rauswerfen
        while bucket and (now - bucket[0]) > window:
            bucket.popleft()
        if len(bucket) >= max_calls:
            oldest = bucket[0]
            retry_after = max(1, int(window - (now - oldest)) + 1)
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Rate limit exceeded ({max_calls} requests / {int(window)}s). "
                    f"Bitte in {retry_after}s erneut versuchen."
                ),
                headers={"Retry-After": str(retry_after)},
            )
        bucket.append(now)


# ── Helper ────────────────────────────────────────────────────────────────────


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


_IDENTIFIER_ONLY_LABELS = {
    "ust-idnr": "USt-ID / Steuernummer",
    "ustidnr": "USt-ID / Steuernummer",
    "ust-id": "USt-ID / Steuernummer",
    "vat": "USt-ID / Steuernummer",
    "uid-nummer": "USt-ID / Steuernummer",
    "national-vat-number": "USt-ID / Steuernummer",
    "other-ms-vat-number": "USt-ID / Steuernummer",
    "dk-vat-number": "USt-ID / Steuernummer",
    "st-nr": "Steuernummer",
    "steuer-nr": "Steuernummer",
    "steuernummer": "Steuernummer",
    "handelsregisternummer": "Handelsregister",
    "firmenbuchnummer": "Firmenbuchnummer",
    "vereinsregisternummer": "Vereinsregister",
    "lfbis-betriebsnummer": "LFBIS-Betriebsnummer",
    "abgabenkontonummer": "Abgabenkontonummer",
    "business-identity-code": "Business Identity Code",
    "organisationsnummer": "Organisationsnummer",
    "registrikood": "Registrikood",
    "legal-person's-code": "Legal Person's Code",
    "aber": "ABER",
    "kur": "KUR",
    "fiber": "FIBER",
    "sonstige": "Sonstige",
}


def _split_beneficiary_identifier(raw: str | None) -> tuple[str | None, str | None]:
    """Trennt das TAM-Identifikatorfeld in Art und konkrete Nummer, falls vorhanden.

    Deutsche TAM-Datensätze enthalten häufig nur die Identifikationsart
    (z.B. "USt-IdNr") und veröffentlichen die eigentliche Nummer nicht.
    """
    value = (raw or "").strip()
    if not value:
        return None, None

    compact = re.sub(r"[\s_.]+", "-", value.casefold()).strip("-")
    if compact in _IDENTIFIER_ONLY_LABELS:
        return _IDENTIFIER_ONLY_LABELS[compact], None

    labeled = re.match(
        r"^(?P<label>USt(?:-?IdNr|-?ID)?|VAT|St-?Nr|Steuer(?:nummer|-Nr)?|Handelsregisternummer)\s*[:=\-]\s*(?P<number>.+)$",
        value,
        flags=re.IGNORECASE,
    )
    if labeled:
        label = labeled.group("label").strip()
        number = labeled.group("number").strip()
        label_compact = re.sub(r"[\s_.]+", "-", label.casefold()).strip("-")
        return _IDENTIFIER_ONLY_LABELS.get(label_compact, label), number or None

    if re.fullmatch(r"DE[0-9]{9}", value, flags=re.IGNORECASE):
        return "USt-ID / Steuernummer", value
    if re.search(r"\b(HRB|HRA|VR|GnR)\s*[0-9]", value, flags=re.IGNORECASE):
        return "Handelsregister", value

    return "Identifikationsmerkmal", value


def _serialize_award(award: StateAidAward) -> dict:
    """Serialisiert einen Award fuer JSON-Response."""
    raw_payload = award.raw_payload if isinstance(award.raw_payload, dict) else {}
    raw_national_id = (raw_payload.get("national_id") or "").strip()
    raw_national_id_type = (raw_payload.get("national_id_type") or "").strip()
    if raw_national_id and raw_national_id_type:
        identifier_type, _unused = _split_beneficiary_identifier(raw_national_id_type)
        identifier_type = identifier_type or raw_national_id_type
        identifier_value = raw_national_id
    else:
        identifier_type, identifier_value = _split_beneficiary_identifier(
            award.beneficiary_identifier,
        )
        if raw_national_id_type and not identifier_type:
            identifier_type = raw_national_id_type
    return {
        "id": award.id,
        "source_key": award.source_key,
        "source_record_id": award.source_record_id,
        "source_url": award.source_url,
        "harvest_run_id": award.harvest_run_id,
        "beneficiary_name": award.beneficiary_name,
        "beneficiary_name_normalized": award.beneficiary_name_normalized,
        "beneficiary_identifier": award.beneficiary_identifier,
        "beneficiary_identifier_type": identifier_type,
        "beneficiary_identifier_value": identifier_value,
        "beneficiary_type": award.beneficiary_type,
        "country_code": award.country_code,
        "country_name": award.country_name,
        "nuts_code": award.nuts_code,
        "nuts_label": award.nuts_label,
        "nuts_level": award.nuts_level,
        "nace_code": award.nace_code,
        "nace_label": award.nace_label,
        "aid_amount": _to_float(award.aid_amount),
        "aid_currency": award.aid_currency,
        "aid_amount_eur": _to_float(award.aid_amount_eur),
        "aid_nominal_amount": _to_float(award.aid_nominal_amount),
        "aid_instrument": award.aid_instrument,
        "aid_objective": award.aid_objective,
        "aid_measure_title": award.aid_measure_title,
        "granting_authority": award.granting_authority,
        "entrusted_entity": award.entrusted_entity,
        "financial_intermediaries": award.financial_intermediaries,
        "granting_date": award.granting_date.isoformat() if award.granting_date else None,
        "publication_date": award.publication_date.isoformat() if award.publication_date else None,
        "measure_reference": award.measure_reference,
        "sa_reference": award.sa_reference,
        "case_url": award.case_url,
        "decision_url": award.decision_url,
        "created_at": award.created_at.isoformat() if award.created_at else None,
        "updated_at": award.updated_at.isoformat() if award.updated_at else None,
    }


def _apply_award_filters(
    q,
    *,
    country_code: str | None = None,
    nuts_code: str | None = None,
    since: date | None = None,
    until: date | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
    aid_instrument: str | None = None,
    objective: str | None = None,
    granting_authority: str | None = None,
    sa_reference: str | None = None,
    source_key: str | None = None,
):
    if country_code:
        q = q.filter(StateAidAward.country_code == country_code.upper())
    if nuts_code:
        # Prefix-Match: Suche per NUTS-1 ('DE2') matcht auch NUTS-2 ('DE21')
        # und NUTS-3 ('DE212' Muenchen) — Plan §6.3 / Wunsch des Workshops.
        nc = nuts_code.upper()
        q = q.filter(StateAidAward.nuts_code.like(f"{nc}%"))
    if since:
        q = q.filter(StateAidAward.granting_date >= since)
    if until:
        q = q.filter(StateAidAward.granting_date <= until)
    if min_amount is not None:
        q = q.filter(StateAidAward.aid_amount_eur >= Decimal(str(min_amount)))
    if max_amount is not None:
        q = q.filter(StateAidAward.aid_amount_eur <= Decimal(str(max_amount)))
    # User-Eingabe-Filter (Free-Text): Wildcards '%' und '_' werden escapt,
    # damit Eingaben wie '50%' oder 'a_b' nicht als SQL-Wildcards wirken.
    if aid_instrument:
        q = q.filter(StateAidAward.aid_instrument.ilike(
            f"%{_escape_like(aid_instrument)}%", escape="\\",
        ))
    if objective:
        q = q.filter(StateAidAward.aid_objective.ilike(
            f"%{_escape_like(objective)}%", escape="\\",
        ))
    if granting_authority:
        q = q.filter(StateAidAward.granting_authority.ilike(
            f"%{_escape_like(granting_authority)}%", escape="\\",
        ))
    if sa_reference:
        q = q.filter(StateAidAward.sa_reference.ilike(
            f"%{_escape_like(sa_reference)}%", escape="\\",
        ))
    if source_key:
        q = q.filter(StateAidAward.source_key == source_key)
    return q


def _pflichthinweis() -> str:
    """Plan §13 — Pflichthinweis zur Datenherkunft."""
    return (
        "Quelle: EU Transparency Aid Module (TAM) und nationale Beihilfe-Register, "
        "veröffentlicht nach Art. 9 Abs. 1 lit. c) VO (EU) Nr. 651/2014 (AGVO). "
        "Erfasste Beihilfen sind nur solche, für die eine Veröffentlichungspflicht "
        "besteht (i.d.R. > 100.000 EUR bzw. >= 10.000 EUR im Agrarbereich). "
        "Der Datenbestand kann unvollständig sein."
    )


# ── Pydantic-Schemas (Admin) ─────────────────────────────────────────────────


class HarvestRequest(BaseModel):
    country: str = Field("DE", description="ISO-2 oder ISO-3.")
    regions: list[str] = Field(default_factory=list,
                                description="NUTS-Region-Filter (TAM-Format).")
    since: date | None = None
    until: date | None = None
    limit: int = Field(500, ge=1, le=10000)
    source_key: str | None = None
    # Drei Modi (Plan §11). 'force' hat Vorrang vor dem Legacy-Flag unten.
    mode: Literal["smart", "full-refresh", "force"] = Field(
        "smart",
        description=(
            "smart: nur neue Datensaetze, alte unveraendert (Default). "
            "full-refresh: voller Re-Scan mit UPDATE bei Konflikt. "
            "force: alle Awards der Quelle vorab loeschen."
        ),
    )
    # Rueckwaerts-Kompatibilitaet: alter Boolean-Schalter.
    force: bool = False


# ── Oeffentliche Endpunkte ────────────────────────────────────────────────────


@router.get("/status")
def get_status(db: Session = Depends(get_db)) -> dict:
    """Index-Statistik (Plan §10). Oeffentlich."""
    total_awards = db.query(sql_func.count(StateAidAward.id)).scalar() or 0
    total_runs = db.query(sql_func.count(StateAidHarvestRun.id)).scalar() or 0
    sources_enabled = (
        db.query(sql_func.count(StateAidSource.source_key))
        .filter(StateAidSource.enabled.is_(True))
        .scalar() or 0
    )
    last_run = (
        db.query(StateAidHarvestRun)
        .order_by(StateAidHarvestRun.finished_at.desc().nullslast())
        .first()
    )
    by_country_rows = (
        db.query(
            StateAidAward.country_code,
            sql_func.count(StateAidAward.id).label("count"),
            sql_func.sum(StateAidAward.aid_amount_eur).label("total_eur"),
        )
        .group_by(StateAidAward.country_code)
        .order_by(sql_func.count(StateAidAward.id).desc())
        .all()
    )

    # Validator-Status (best-effort — wenn die Tabelle noch fehlt, kein Crash).
    last_validation_at: str | None = None
    last_validation_status: str | None = None
    last_validation_findings_count: int | None = None
    try:
        last_validation = get_last_report(db, module="state_aid")
        if last_validation:
            last_validation_at = last_validation.get("started_at")
            last_validation_status = last_validation.get("status")
            last_validation_findings_count = len(last_validation.get("findings") or [])
    except Exception:  # noqa: BLE001
        log.exception("Validator-Status-Abfrage fehlgeschlagen")

    return {
        "total_awards": int(total_awards),
        "total_runs": int(total_runs),
        "sources_enabled": int(sources_enabled),
        "last_harvest_at": last_run.finished_at.isoformat()
            if last_run and last_run.finished_at else None,
        "last_harvest_status": last_run.status if last_run else None,
        "by_country": [
            {
                "country_code": r.country_code,
                "count": int(r.count or 0),
                "total_eur": _to_float(r.total_eur),
            }
            for r in by_country_rows
        ],
        "coverage_note": _pflichthinweis(),
        "last_validation_at": last_validation_at,
        "last_validation_status": last_validation_status,
        "last_validation_findings_count": last_validation_findings_count,
    }


# ── Validator-Endpunkte (Self-Check) ─────────────────────────────────────────


@router.get("/validation/last")
def get_validation_last(db: Session = Depends(get_db)) -> dict:
    """Liefert den juengsten Validator-Report fuer das State-Aid-Modul.

    Oeffentlich, weil das UI-Banner ihn ohne Auth pollt. Wenn noch kein Lauf
    existiert, kommt 200 mit `report=None`.
    """
    report = get_last_report(db, module="state_aid")
    return {"module": "state_aid", "report": report}


@router.post("/validation/run")
def post_validation_run(
    _session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Admin-Trigger fuer einen sofortigen Validator-Lauf.

    Synchron — die Checks dauern auf 170k Records < 5 Sek.
    """
    log.info("Validator: manueller Trigger via Admin-Endpoint")
    report = run_validation(db)
    try:
        run_id = persist_report(db, report, module="state_aid")
    except Exception:  # noqa: BLE001
        log.exception("Validator-Persistierung fehlgeschlagen")
        run_id = None
    return {"run_id": run_id, "report": report.to_dict()}


@router.get("/sources")
def list_sources(db: Session = Depends(get_db)) -> dict:
    """Alle StateAidSource-Eintraege — Konfiguration und Abdeckungsstand."""
    rows = (
        db.query(StateAidSource)
        .order_by(StateAidSource.source_type, StateAidSource.country_code)
        .all()
    )
    return {
        "count": len(rows),
        "sources": [
            {
                "source_key": s.source_key,
                "display_name": s.display_name,
                "source_type": s.source_type,
                "country_code": s.country_code,
                "base_url": s.base_url,
                "last_successful_harvest_at": s.last_successful_harvest_at.isoformat()
                    if s.last_successful_harvest_at else None,
                "last_record_date": s.last_record_date.isoformat()
                    if s.last_record_date else None,
                "record_count": int(s.record_count or 0),
                "coverage_note": s.coverage_note,
                "quality": s.quality,
                "enabled": bool(s.enabled),
            }
            for s in rows
        ],
    }


def _adaptive_min_score(query: str, requested: float | None) -> float:
    """Bestimmt den effektiven `min_score` aus der Query-Laenge, falls kein
    Wert vom Aufrufer mitgegeben wurde.

    Regel:
      - >=3 Tokens   -> 60.0  (langer Query, toleranter Match)
      - == 2 Tokens  -> 70.0
      - 1 Token      -> 80.0  (einzelner Token braucht strengen Match,
                                sonst gibt es zu viele False Positives bei 170k Records)

    Wenn der Caller einen Wert mitgegeben hat (z.B. Frontend-Slider 40-100),
    hat dieser Vorrang.
    """
    if requested is not None:
        return float(requested)
    n_tokens = len((query or "").split())
    if n_tokens >= 3:
        return 60.0
    if n_tokens == 2:
        return 70.0
    return 80.0


@router.get("/search")
def search(
    request: Request,
    q: str | None = Query(None, max_length=200, description="Suchbegriff (Beguenstigtenname). Optional, wenn andere Filter gesetzt sind."),
    country_code: str | None = Query(None, max_length=3),
    nuts_code: str | None = Query(None, max_length=10),
    since: date | None = Query(None),
    until: date | None = Query(None),
    min_amount: float | None = Query(None, ge=0),
    max_amount: float | None = Query(None, ge=0),
    aid_instrument: str | None = Query(None, max_length=200),
    objective: str | None = Query(None, max_length=200),
    granting_authority: str | None = Query(None, max_length=200),
    sa_reference: str | None = Query(None, max_length=64),
    source_key: str | None = Query(None, max_length=64),
    limit: int = Query(50, ge=1, le=200),
    min_score: float | None = Query(
        None, ge=40.0, le=100.0,
        description=(
            "Fuzzy-Schwellwert. Wenn nicht gesetzt, wird er adaptiv aus der "
            "Query-Laenge bestimmt (1 Token=80, 2=70, >=3=60)."
        ),
    ),
    location_hint: str | None = Query(
        None, max_length=120,
        description=(
            "Optionaler Standort-Hinweis (Stadt, Bundesland, Region). "
            "Records mit passendem nuts_label bekommen einen kleinen "
            "Score-Boost (+5), Records mit explizit anderem NUTS-Prefix "
            "eine Penalty (-5). Hilft bei Mehrdeutigkeit ohne den "
            "Match-Charakter zu kippen."
        ),
    ),
    db: Session = Depends(get_db),
) -> dict:
    """Plan §10 — Fuzzy-Suche mit zusaetzlichen Filtern.

    Strategie: zuerst RapidFuzz-Treffer ueber `beneficiary_name_normalized`
    holen, dann optionale SQL-Filter zusaetzlich anwenden.

    Optimierungen:
    - Adaptiver `min_score` (siehe `_adaptive_min_score`).
    - Empty-Result-Fallback: Bei 0 Treffern wird einmal weicher gesucht
      (min_score -= 15) und falls noetig der `country_code`-Filter entfernt.
    - Alias-Expansion (z.B. "KfW" -> "Kreditanstalt fuer Wiederaufbau") wird
      in `meta.alias_used` ausgewiesen.
    """
    # Rate-Limit: 60 Requests / 60s pro user_id bzw. IP. Schutz gegen DB-DoS
    # ueber den 170k+ Records grossen RapidFuzz-Index.
    _check_rate_limit("search", request)
    cc = country_code.upper() if country_code else None
    q_clean = (q or "").strip()
    auto_min_score = min_score is None
    effective_min_score = _adaptive_min_score(q_clean, min_score) if q_clean else 0.0

    relaxed: list[str] = []
    location_hint_clean = (location_hint or "").strip() or None

    # Filter-only-Modus: wenn keine Query gesetzt ist, aber andere Filter,
    # zeigen wir die Awards anhand der Filter. Kein Fuzzy-Score noetig.
    if not q_clean:
        # Mindestens ein anderer Filter sollte gesetzt sein, sonst wird die
        # Antwort sehr gross. Wir lassen es zu, beschneiden aber hart.
        # (StateAidAward wird oben am Modul importiert.)
        rows_q = db.query(StateAidAward)
        rows_q = _apply_award_filters(
            rows_q, country_code=cc, nuts_code=nuts_code,
            since=since, until=until,
            min_amount=min_amount, max_amount=max_amount,
            aid_instrument=aid_instrument, objective=objective,
            granting_authority=granting_authority, sa_reference=sa_reference,
            source_key=source_key,
        )
        # Sort: highest amount first when filter-only, easier to spot big grants
        rows_q = rows_q.order_by(StateAidAward.aid_amount_eur.desc().nullslast())
        rows = rows_q.limit(limit).all()
        return {
            "query": "",
            "normalized": "",
            "total_hits": len(rows),
            "threshold": 0.0,
            "hits": [
                {**_serialize_award(r), "score": 100.0, "confidence": "exact",
                 "matched_field": "filter", "via_alias": None,
                 "match_stage": "filter"}
                for r in rows
            ],
            "filters_applied": {
                k: v for k, v in {
                    "country_code": cc, "nuts_code": nuts_code,
                    "since": since.isoformat() if since else None,
                    "until": until.isoformat() if until else None,
                    "min_amount": min_amount, "max_amount": max_amount,
                    "aid_instrument": aid_instrument, "objective": objective,
                    "granting_authority": granting_authority,
                    "sa_reference": sa_reference, "source_key": source_key,
                }.items() if v is not None
            },
            "meta": {
                "mode": "filter_only",
                "auto_min_score": False,
                "alias_used": None,
                "relaxed": [],
                "location_hint_used": False,
            },
        }

    hits = fuzzy_match_company(
        db, q_clean, limit=limit * 3, min_score=effective_min_score, country_code=cc,
        location_hint=location_hint_clean,
    )

    # Empty-Result-Fallback: schrittweise lockern, bis Treffer da sind.
    relaxed_min_score = effective_min_score
    relaxed_cc = cc
    if not hits and effective_min_score > 50.0:
        new_min = max(50.0, effective_min_score - 15.0)
        relaxed.append(f"min_score:{effective_min_score:g}->{new_min:g}")
        relaxed_min_score = new_min
        hits = fuzzy_match_company(
            db, q, limit=limit * 3, min_score=relaxed_min_score, country_code=relaxed_cc,
            location_hint=location_hint_clean,
        )
    if not hits and relaxed_cc:
        relaxed.append(f"country_code:{relaxed_cc}->none")
        relaxed_cc = None
        hits = fuzzy_match_company(
            db, q, limit=limit * 3, min_score=relaxed_min_score, country_code=relaxed_cc,
            location_hint=location_hint_clean,
        )

    # Alias-Label aus erstem Treffer ablesen (alle Hits desselben Aufrufs
    # tragen denselben Alias, da expand_alias() zentral wirkt).
    alias_used = hits[0].via_alias if hits else None

    base_meta: dict[str, Any] = {}
    if alias_used:
        base_meta["alias_used"] = alias_used
    if relaxed:
        base_meta["relaxed"] = relaxed
    if auto_min_score:
        base_meta["auto_min_score"] = True
    if location_hint_clean:
        base_meta["location_hint_used"] = True

    if not hits:
        return {
            "query": q,
            "normalized": normalize_company_name(q),
            "total_hits": 0,
            "threshold": relaxed_min_score,
            "hits": [],
            "filters_applied": _filters_applied_dict(
                country_code=cc, nuts_code=nuts_code, since=since, until=until,
                min_amount=min_amount, max_amount=max_amount,
                aid_instrument=aid_instrument, objective=objective,
                granting_authority=granting_authority, sa_reference=sa_reference,
                source_key=source_key,
            ),
            "meta": base_meta,
        }

    # Zusatz-Filter via SQL — beachte: fuer SQL-Filter wird der ggf. relaxte
    # country_code verwendet, damit wir ueberhaupt Treffer durch den
    # SQL-Filter bekommen, wenn das Land der Grund fuer 0 Hits war.
    award_query = db.query(StateAidAward).filter(
        StateAidAward.id.in_([h.award_id for h in hits])
    )
    award_query = _apply_award_filters(
        award_query,
        country_code=relaxed_cc, nuts_code=nuts_code, since=since, until=until,
        min_amount=min_amount, max_amount=max_amount,
        aid_instrument=aid_instrument, objective=objective,
        granting_authority=granting_authority, sa_reference=sa_reference,
        source_key=source_key,
    )
    awards_by_id = {a.id: a for a in award_query.all()}

    enriched = []
    for h in hits:
        award = awards_by_id.get(h.award_id)
        if not award:
            continue
        payload = _serialize_award(award)
        payload.update({
            "score": h.score,
            "confidence": h.confidence,
            "matched_field": h.matched_field,
            "matched_value": h.matched_value,
        })
        enriched.append(payload)
        if len(enriched) >= limit:
            break

    return {
        "query": q,
        "normalized": normalize_company_name(q),
        "total_hits": len(enriched),
        "threshold": relaxed_min_score,
        "hits": enriched,
        "filters_applied": _filters_applied_dict(
            country_code=cc, nuts_code=nuts_code, since=since, until=until,
            min_amount=min_amount, max_amount=max_amount,
            aid_instrument=aid_instrument, objective=objective,
            granting_authority=granting_authority, sa_reference=sa_reference,
            source_key=source_key,
        ),
        "meta": base_meta,
    }


def _filters_applied_dict(**kwargs) -> dict:
    """Liefert nur Filter, die wirklich gesetzt wurden — gut fuer UI-Anzeige."""
    out: dict[str, Any] = {}
    for k, v in kwargs.items():
        if v is None:
            continue
        if isinstance(v, date):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


@router.get("/award/{award_id}")
def get_award(award_id: str, db: Session = Depends(get_db)) -> dict:
    """Einzelner Award als JSON. 404 wenn nicht da."""
    award = db.query(StateAidAward).filter(StateAidAward.id == award_id).first()
    if not award:
        raise HTTPException(404, f"Award {award_id} nicht gefunden.")
    return _serialize_award(award)


@router.get("/map")
def get_map(
    country_code: str | None = Query(None, max_length=3),
    since: date | None = Query(None),
    until: date | None = Query(None),
    level: int = Query(1, ge=0, le=3, description="0=Land, 1=Bundesland (Default), 2=Regierungsbezirk, 3=Kreis"),
    db: Session = Depends(get_db),
) -> dict:
    """Plan §8 — NUTS-Aggregat fuer Karte (keine Adressen)."""
    cc = country_code.upper() if country_code else None
    return aggregate_for_map(db, country_code=cc, since=since, until=until, level=level)


@router.get("/stats")
def get_stats(
    q: str | None = Query(None, max_length=200),
    country_code: str | None = Query(None, max_length=3),
    nuts_code: str | None = Query(None, max_length=10),
    since: date | None = Query(None),
    until: date | None = Query(None),
    min_amount: float | None = Query(None, ge=0),
    max_amount: float | None = Query(None, ge=0),
    aid_instrument: str | None = Query(None, max_length=200),
    objective: str | None = Query(None, max_length=200),
    granting_authority: str | None = Query(None, max_length=200),
    sa_reference: str | None = Query(None, max_length=64),
    source_key: str | None = Query(None, max_length=64),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> dict:
    """Aggregat-Statistiken: Top-N-Listen + Verteilungen pro Jahr/Land."""
    cc = country_code.upper() if country_code else None

    base = db.query(StateAidAward)
    base = _apply_award_filters(
        base,
        country_code=cc, nuts_code=nuts_code, since=since, until=until,
        min_amount=min_amount, max_amount=max_amount,
        aid_instrument=aid_instrument, objective=objective,
        granting_authority=granting_authority, sa_reference=sa_reference,
        source_key=source_key,
    )

    # Optionale Volltext-Vorfilterung via Fuzzy auf den Namen
    if q:
        hits = fuzzy_match_company(db, q, limit=2000, min_score=70.0, country_code=cc)
        if not hits:
            base = base.filter(StateAidAward.id.in_([]))
        else:
            base = base.filter(StateAidAward.id.in_([h.award_id for h in hits]))

    base_subq = base.subquery()

    def _top(grouping, label_attr=None, n: int = limit) -> list[dict]:
        rows = (
            db.query(
                grouping.label("key"),
                sql_func.count().label("count"),
                sql_func.sum(base_subq.c.aid_amount_eur).label("total_eur"),
            )
            .select_from(base_subq)
            .group_by(grouping)
            .order_by(sql_func.sum(base_subq.c.aid_amount_eur).desc().nullslast())
            .limit(n)
            .all()
        )
        return [
            {
                "key": r.key,
                "count": int(r.count or 0),
                "total_eur": _to_float(r.total_eur),
            }
            for r in rows
            if r.key is not None
        ]

    top_beneficiaries = _top(base_subq.c.beneficiary_name)
    top_authorities = _top(base_subq.c.granting_authority)
    top_objectives = _top(base_subq.c.aid_objective)
    top_instruments = _top(base_subq.c.aid_instrument)

    by_year_rows = (
        db.query(
            sql_func.extract("year", base_subq.c.granting_date).label("year"),
            sql_func.count().label("count"),
            sql_func.sum(base_subq.c.aid_amount_eur).label("total_eur"),
        )
        .select_from(base_subq)
        .group_by("year")
        .order_by("year")
        .all()
    )
    by_year = [
        {
            "year": int(r.year) if r.year is not None else None,
            "count": int(r.count or 0),
            "total_eur": _to_float(r.total_eur),
        }
        for r in by_year_rows
        if r.year is not None
    ]

    by_country_rows = (
        db.query(
            base_subq.c.country_code.label("country_code"),
            sql_func.count().label("count"),
            sql_func.sum(base_subq.c.aid_amount_eur).label("total_eur"),
        )
        .select_from(base_subq)
        .group_by(base_subq.c.country_code)
        .order_by(sql_func.sum(base_subq.c.aid_amount_eur).desc().nullslast())
        .all()
    )
    by_country = [
        {
            "country_code": r.country_code,
            "count": int(r.count or 0),
            "total_eur": _to_float(r.total_eur),
        }
        for r in by_country_rows
    ]

    total = db.query(sql_func.count()).select_from(base_subq).scalar() or 0
    total_eur = db.query(sql_func.sum(base_subq.c.aid_amount_eur)).select_from(base_subq).scalar()

    return {
        "filters_applied": _filters_applied_dict(
            q=q, country_code=cc, nuts_code=nuts_code, since=since, until=until,
            min_amount=min_amount, max_amount=max_amount,
            aid_instrument=aid_instrument, objective=objective,
            granting_authority=granting_authority, sa_reference=sa_reference,
            source_key=source_key,
        ),
        "total_awards": int(total),
        "total_eur": _to_float(total_eur),
        "top_beneficiaries": top_beneficiaries,
        "top_authorities": top_authorities,
        "top_objectives": top_objectives,
        "top_instruments": top_instruments,
        "by_year": by_year,
        "by_country": by_country,
    }


@router.get("/stats/export")
def export_stats(
    format: str = Query("xlsx", pattern="^(xlsx)$"),
    q: str | None = Query(None, max_length=200),
    country_code: str | None = Query(None, max_length=3),
    nuts_code: str | None = Query(None, max_length=10),
    since: date | None = Query(None),
    until: date | None = Query(None),
    min_amount: float | None = Query(None, ge=0),
    max_amount: float | None = Query(None, ge=0),
    aid_instrument: str | None = Query(None, max_length=200),
    objective: str | None = Query(None, max_length=200),
    granting_authority: str | None = Query(None, max_length=200),
    sa_reference: str | None = Query(None, max_length=64),
    source_key: str | None = Query(None, max_length=64),
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Auswertungs-Export — Top-Listen + Jahresverteilung als Multi-Sheet-XLSX.

    Sheets:
      - Top Behoerden
      - Top Beguenstigte
      - Top NUTS-Regionen (auf Basis von Awards je NUTS-Code)
      - Top Instrumente
      - Jahresverteilung

    Kein PDF/CSV — Statistiken sind ohnehin tabellarisch und Excel das natuerliche
    Format. Filter-Param-Set ist identisch zu /api/state-aid/stats.
    """
    from services.excel_export import (
        XLSX_MEDIA_TYPE,
        make_xlsx_multi_sheet,
        xlsx_response_headers,
    )

    cc = country_code.upper() if country_code else None

    # Re-Use von /stats Logik via direktem Aufruf — vermeidet Code-Duplikation
    stats = get_stats(
        q=q, country_code=cc, nuts_code=nuts_code, since=since, until=until,
        min_amount=min_amount, max_amount=max_amount,
        aid_instrument=aid_instrument, objective=objective,
        granting_authority=granting_authority, sa_reference=sa_reference,
        source_key=source_key, limit=limit, db=db,
    )

    # NUTS-Auswertung separat — /stats liefert keinen by_nuts-Block, wir
    # bauen ihn hier on-the-fly.
    base = db.query(StateAidAward)
    base = _apply_award_filters(
        base,
        country_code=cc, nuts_code=nuts_code, since=since, until=until,
        min_amount=min_amount, max_amount=max_amount,
        aid_instrument=aid_instrument, objective=objective,
        granting_authority=granting_authority, sa_reference=sa_reference,
        source_key=source_key,
    )
    if q:
        hits = fuzzy_match_company(db, q, limit=2000, min_score=70.0, country_code=cc)
        if not hits:
            base = base.filter(StateAidAward.id.in_([]))
        else:
            base = base.filter(StateAidAward.id.in_([h.award_id for h in hits]))

    base_subq = base.subquery()
    nuts_rows = (
        db.query(
            base_subq.c.nuts_code.label("nuts_code"),
            base_subq.c.nuts_label.label("nuts_label"),
            sql_func.count().label("count"),
            sql_func.sum(base_subq.c.aid_amount_eur).label("total_eur"),
        )
        .select_from(base_subq)
        .group_by(base_subq.c.nuts_code, base_subq.c.nuts_label)
        .order_by(sql_func.sum(base_subq.c.aid_amount_eur).desc().nullslast())
        .limit(limit)
        .all()
    )
    by_nuts = [
        {
            "nuts_code": r.nuts_code or "",
            "nuts_label": r.nuts_label or "",
            "count": int(r.count or 0),
            "total_eur": _to_float(r.total_eur),
        }
        for r in nuts_rows if r.nuts_code or r.nuts_label
    ]

    sheets = [
        {
            "name": "Top Behoerden",
            "headers": ["key", "count", "total_eur"],
            "rows": stats.get("top_authorities") or [],
            "table_name": "TopBehoerden",
        },
        {
            "name": "Top Beguenstigte",
            "headers": ["key", "count", "total_eur"],
            "rows": stats.get("top_beneficiaries") or [],
            "table_name": "TopBeguenstigte",
        },
        {
            "name": "Top NUTS-Regionen",
            "headers": ["nuts_code", "nuts_label", "count", "total_eur"],
            "rows": by_nuts,
            "table_name": "TopNUTS",
        },
        {
            "name": "Top Instrumente",
            "headers": ["key", "count", "total_eur"],
            "rows": stats.get("top_instruments") or [],
            "table_name": "TopInstrumente",
        },
        {
            "name": "Jahresverteilung",
            "headers": ["year", "count", "total_eur"],
            "rows": stats.get("by_year") or [],
            "table_name": "Jahresverteilung",
        },
    ]

    metadata: dict[str, str] = {
        "Trefferzahl gesamt": str(stats.get("total_awards") or 0),
        "Foerdervolumen gesamt (EUR)": f"{stats.get('total_eur') or 0:.2f}",
        "Limit pro Top-Liste": str(limit),
    }
    filters_applied = stats.get("filters_applied") or {}
    if filters_applied:
        metadata["Filter"] = ", ".join(f"{k}={v}" for k, v in filters_applied.items())
    sources = db.query(StateAidSource).order_by(StateAidSource.source_key).all()
    metadata.update(_build_source_metadata(sources))

    xlsx_bytes = make_xlsx_multi_sheet(
        sheets,
        pflichthinweis=_pflichthinweis(),
        metadata=metadata,
        notes_title="State-Aid-Auswertung · Hinweise",
    )

    filename = f"state_aid_stats_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        iter([xlsx_bytes]),
        media_type=XLSX_MEDIA_TYPE,
        headers=xlsx_response_headers(filename),
    )


@router.get("/company-dossier")
def company_dossier(
    q: str = Query(..., min_length=2, max_length=200, description="Firmenname / Beguenstigter."),
    country_code: str | None = Query(None, max_length=3),
    db: Session = Depends(get_db),
) -> dict:
    """Plan §7.3 — Cross-Register-Dossier fuer einen Firmennamen.

    Sucht parallel in:
    - State-Aid: Top 20 Awards des Beguenstigten
    - Sanctions: EU FSF Top 10 Treffer
    - Beneficiaries: lokale Begünstigtenverzeichnisse Top 20
    """
    cc = country_code.upper() if country_code else None

    # ── State-Aid ─────────────────────────────────────────────────────────
    state_aid_hits: list[dict] = []
    state_aid_total_eur: float = 0.0
    try:
        sa_hits = fuzzy_match_company(db, q, limit=20, min_score=70.0, country_code=cc)
        if sa_hits:
            awards = (
                db.query(StateAidAward)
                .filter(StateAidAward.id.in_([h.award_id for h in sa_hits]))
                .all()
            )
            by_id = {a.id: a for a in awards}
            for h in sa_hits:
                a = by_id.get(h.award_id)
                if not a:
                    continue
                payload = _serialize_award(a)
                payload.update({
                    "score": h.score,
                    "confidence": h.confidence,
                    "matched_field": h.matched_field,
                })
                state_aid_hits.append(payload)
                state_aid_total_eur += float(a.aid_amount_eur or 0)
    except Exception as exc:  # noqa: BLE001
        log.warning("Dossier State-Aid-Suche fehlgeschlagen: %s", exc)

    # ── Sanctions (EU FSF) ────────────────────────────────────────────────
    sanctions_hits: list[dict] = []
    try:
        from services.sanctions_service import get_index
        idx = get_index()
        if idx.is_loaded():
            for h in idx.search(q, limit=10, min_score=80.0):
                sanctions_hits.append({
                    "id": h.id,
                    "schema": h.schema,
                    "name": h.name,
                    "matched_on": h.matched_on,
                    "matched_field": h.matched_field,
                    "score": h.score,
                    "confidence": h.confidence,
                    "aliases": h.aliases,
                    "countries": h.countries,
                    "sanctions": h.sanctions,
                    "program_ids": h.program_ids,
                })
    except Exception as exc:  # noqa: BLE001
        log.warning("Dossier Sanctions-Suche fehlgeschlagen: %s", exc)

    # ── Beneficiaries (lokale Verzeichnisse) ──────────────────────────────
    beneficiary_hits: list[dict] = []
    beneficiary_total = 0
    try:
        from services.dataframe_service import search_beneficiary_records
        ben_result = search_beneficiary_records(
            query=q, scope="company", limit=20, country_code=cc,
        )
        if isinstance(ben_result, dict):
            beneficiary_hits = (
                ben_result.get("results")
                or ben_result.get("companies")
                or ben_result.get("entries")
                or []
            )
            beneficiary_total = ben_result.get("count") or len(beneficiary_hits)
        elif isinstance(ben_result, list):
            beneficiary_hits = ben_result
            beneficiary_total = len(ben_result)
    except Exception as exc:  # noqa: BLE001
        log.info("Dossier Beneficiaries-Suche uebersprungen: %s", exc)

    # ── Summary ──────────────────────────────────────────────────────────
    register_count = sum(1 for cnt in (
        len(state_aid_hits), len(sanctions_hits), len(beneficiary_hits),
    ) if cnt > 0)

    return {
        "query": q,
        "normalized": normalize_company_name(q),
        "country_code": cc,
        "state_aid": {
            "count": len(state_aid_hits),
            "total_eur": state_aid_total_eur,
            "hits": state_aid_hits,
        },
        "sanctions": {
            "count": len(sanctions_hits),
            "hits": sanctions_hits,
        },
        "beneficiaries": {
            "count": int(beneficiary_total or 0),
            "hits": beneficiary_hits,
        },
        "summary": {
            "register_count": register_count,
            "total_eur": state_aid_total_eur,
            "has_sanctions_hit": bool(sanctions_hits),
        },
        "coverage_note": _pflichthinweis(),
    }


# ── Export ────────────────────────────────────────────────────────────────────


CSV_COLUMNS = [
    "id", "source_key", "source_record_id", "source_url",
    "beneficiary_name", "beneficiary_identifier", "beneficiary_identifier_type",
    "beneficiary_identifier_value", "beneficiary_type",
    "country_code", "country_name", "nuts_code", "nuts_label", "nuts_level",
    "nace_code", "nace_label",
    "aid_amount", "aid_currency", "aid_amount_eur", "aid_nominal_amount",
    "aid_instrument", "aid_objective", "aid_measure_title",
    "granting_authority", "entrusted_entity", "financial_intermediaries",
    "granting_date", "publication_date",
    "measure_reference", "sa_reference", "case_url", "decision_url",
]


def _query_for_export(
    db: Session, q: str | None, *,
    country_code: str | None, nuts_code: str | None,
    since: date | None, until: date | None,
    min_amount: float | None, max_amount: float | None,
    aid_instrument: str | None, objective: str | None,
    granting_authority: str | None, sa_reference: str | None,
    source_key: str | None, limit: int, min_score: float,
) -> list[StateAidAward]:
    if q:
        hits = fuzzy_match_company(db, q, limit=limit * 2, min_score=min_score,
                                   country_code=country_code)
        if not hits:
            return []
        ids = [h.award_id for h in hits]
        base = db.query(StateAidAward).filter(StateAidAward.id.in_(ids))
    else:
        base = db.query(StateAidAward)
    base = _apply_award_filters(
        base,
        country_code=country_code, nuts_code=nuts_code, since=since, until=until,
        min_amount=min_amount, max_amount=max_amount,
        aid_instrument=aid_instrument, objective=objective,
        granting_authority=granting_authority, sa_reference=sa_reference,
        source_key=source_key,
    )
    base = base.order_by(StateAidAward.granting_date.desc().nullslast())
    return base.limit(limit).all()


def _stream_csv(awards: list[StateAidAward], filters: dict, sources: list[StateAidSource]) -> StreamingResponse:
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_MINIMAL)

    # Metadaten als Kommentar-Zeilen
    buf.write(f"# FlowWorkshop · State-Aid-Export · {datetime.utcnow().isoformat()}Z\n")
    buf.write("# Quelle: EU TAM (Transparency Aid Module) und nationale Register\n")
    buf.write(f"# {_pflichthinweis()}\n")
    if filters:
        buf.write(f"# Filter: {filters}\n")
    for s in sources:
        last = s.last_successful_harvest_at.isoformat() if s.last_successful_harvest_at else "—"
        buf.write(
            f"# Datenstand {s.source_key}: {s.record_count or 0} Awards · "
            f"letzter Harvest {last} · Qualitaet {s.quality or '?'}\n"
        )

    writer.writerow(CSV_COLUMNS)
    for a in awards:
        d = _serialize_award(a)
        writer.writerow([d.get(k) if d.get(k) is not None else "" for k in CSV_COLUMNS])

    buf.seek(0)
    headers = {
        "Content-Disposition": (
            f"attachment; filename=\"state_aid_export_"
            f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv\""
        ),
    }
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers=headers,
    )


def _build_source_metadata(sources: list[StateAidSource]) -> dict:
    """Datenstand pro Quelle (Source-Key → Beschreibung) — fuer XLSX-Hinweise."""
    out: dict[str, str] = {}
    for s in sources:
        last = s.last_successful_harvest_at.isoformat() if s.last_successful_harvest_at else "—"
        out[s.source_key] = (
            f"{s.record_count or 0} Awards · letzter Harvest {last} · "
            f"Qualitaet {s.quality or '?'}"
        )
    return out


def _stream_xlsx(awards: list[StateAidAward], filters: dict, sources: list[StateAidSource]) -> StreamingResponse:
    """XLSX-Export via openpyxl (services/excel_export.py).

    Sheet 1: Awards-Daten mit AutoFilter und Header-Style
    Sheet "Hinweise": Pflichthinweis + Datenstand pro Quelle (Plan §13)
    """
    from services.excel_export import (
        XLSX_MEDIA_TYPE,
        make_xlsx,
        xlsx_response_headers,
    )

    rows = [_serialize_award(a) for a in awards]
    metadata: dict[str, str] = {}
    if filters:
        metadata["Filter"] = ", ".join(f"{k}={v}" for k, v in filters.items())
    metadata["Trefferzahl"] = str(len(awards))
    metadata.update(_build_source_metadata(sources))

    xlsx_bytes = make_xlsx(
        rows,
        sheet_name="Beihilfen",
        headers=CSV_COLUMNS,
        table_name="Beihilfen",
        pflichthinweis=_pflichthinweis(),
        metadata=metadata,
        notes_title="EU-Beihilfe-Export · Hinweise",
    )

    filename = f"state_aid_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        iter([xlsx_bytes]),
        media_type=XLSX_MEDIA_TYPE,
        headers=xlsx_response_headers(filename),
    )


def _stream_pdf(awards: list[StateAidAward], filters: dict, sources: list[StateAidSource]) -> StreamingResponse:
    """PDF-Export via PyMuPDF (pymupdf ist installiert)."""
    try:
        import fitz  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            501,
            f"PDF-Export nicht verfuegbar: pymupdf nicht installiert ({exc}).",
        ) from exc

    doc = fitz.open()
    page = doc.new_page(width=842, height=595)  # A4 Querformat
    margin = 28
    cursor_y = margin
    line_height = 11

    def _write(text: str, *, size: int = 9, bold: bool = False) -> None:
        nonlocal cursor_y, page
        if cursor_y > page.rect.height - margin - line_height:
            page = doc.new_page(width=842, height=595)
            cursor_y = margin
        font = "helvB" if bold else "helv"
        try:
            page.insert_text(
                (margin, cursor_y), text, fontsize=size, fontname=font,
            )
        except Exception:
            page.insert_text((margin, cursor_y), text, fontsize=size)
        cursor_y += line_height + (size - 9)

    _write("FlowWorkshop · EU-Beihilfe-Export", size=14, bold=True)
    _write(datetime.utcnow().strftime("Erstellt: %Y-%m-%d %H:%M UTC"), size=9)
    if filters:
        _write(f"Filter: {filters}", size=8)
    for s in sources:
        last = s.last_successful_harvest_at.strftime("%Y-%m-%d") if s.last_successful_harvest_at else "—"
        _write(
            f"  · {s.source_key}: {s.record_count or 0} Awards · "
            f"letzter Harvest {last} · Qualitaet {s.quality or '?'}",
            size=8,
        )
    cursor_y += line_height // 2

    _write(f"Treffer: {len(awards)}", size=10, bold=True)
    cursor_y += line_height // 2

    for a in awards:
        d = _serialize_award(a)
        amount = d.get("aid_amount_eur")
        amount_str = f"{amount:,.2f} EUR" if amount is not None else "—"
        granting_date = d.get("granting_date") or "—"
        _write(
            f"{d.get('beneficiary_name', '')} · {d.get('country_code') or '—'}"
            f" · {granting_date} · {amount_str}",
            size=9, bold=True,
        )
        if d.get("aid_measure_title"):
            _write(f"   Massnahme: {(d['aid_measure_title'] or '')[:160]}", size=8)
        if d.get("granting_authority"):
            _write(f"   Bewilligungsstelle: {d['granting_authority']}", size=8)
        if d.get("sa_reference"):
            _write(f"   SA-Ref: {d['sa_reference']}", size=8)
        cursor_y += 2

    # Footer-Pflichthinweis auf jeder Seite waere sauberer; hier minimal:
    _write("", size=8)
    _write(_pflichthinweis(), size=7)

    pdf_bytes = doc.tobytes()
    doc.close()

    headers = {
        "Content-Disposition": (
            f"attachment; filename=\"state_aid_export_"
            f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf\""
        ),
    }
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers=headers,
    )


@router.get("/export")
def export_awards(
    format: str = Query("csv", pattern="^(csv|xlsx|pdf)$"),
    q: str | None = Query(None, min_length=2, max_length=200),
    country_code: str | None = Query(None, max_length=3),
    nuts_code: str | None = Query(None, max_length=10),
    since: date | None = Query(None),
    until: date | None = Query(None),
    min_amount: float | None = Query(None, ge=0),
    max_amount: float | None = Query(None, ge=0),
    aid_instrument: str | None = Query(None, max_length=200),
    objective: str | None = Query(None, max_length=200),
    granting_authority: str | None = Query(None, max_length=200),
    sa_reference: str | None = Query(None, max_length=64),
    source_key: str | None = Query(None, max_length=64),
    limit: int = Query(500, ge=1, le=5000),
    min_score: float = Query(70.0, ge=40.0, le=100.0),
    db: Session = Depends(get_db),
):
    """Export-Endpoint (CSV oder PDF, Plan §13)."""
    cc = country_code.upper() if country_code else None
    awards = _query_for_export(
        db, q,
        country_code=cc, nuts_code=nuts_code, since=since, until=until,
        min_amount=min_amount, max_amount=max_amount,
        aid_instrument=aid_instrument, objective=objective,
        granting_authority=granting_authority, sa_reference=sa_reference,
        source_key=source_key, limit=limit, min_score=min_score,
    )

    filters_applied = _filters_applied_dict(
        q=q, country_code=cc, nuts_code=nuts_code, since=since, until=until,
        min_amount=min_amount, max_amount=max_amount,
        aid_instrument=aid_instrument, objective=objective,
        granting_authority=granting_authority, sa_reference=sa_reference,
        source_key=source_key,
    )
    sources = db.query(StateAidSource).order_by(StateAidSource.source_key).all()

    if format == "csv":
        return _stream_csv(awards, filters_applied, sources)
    if format == "xlsx":
        return _stream_xlsx(awards, filters_applied, sources)
    return _stream_pdf(awards, filters_applied, sources)


# ── Admin-Endpunkte ──────────────────────────────────────────────────────────


@router.post("/harvest")
def admin_harvest(
    body: HarvestRequest,
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Admin: TAM-Harvest synchron starten (Plan §10).

    Synchron — der Workshop-Demo laeuft live, Pruefer wartet auf Ergebnis.
    Frontend muss seinen eigenen Timeout setzen.
    """
    # Land normalisieren — TAM erwartet ISO-3
    country_raw = (body.country or "DE").strip().upper()
    iso2_to_iso3 = {iso2: iso3 for iso3, iso2 in ISO3_TO_ISO2.items()}
    if len(country_raw) == 3 and country_raw in ISO3_TO_ISO2:
        country_iso3 = country_raw
    elif len(country_raw) == 2 and country_raw in iso2_to_iso3:
        country_iso3 = iso2_to_iso3[country_raw]
    else:
        raise HTTPException(422, f"Erwartet ISO-2 oder ISO-3, bekommen '{body.country}'.")

    source_key = body.source_key or _default_source_key(country_iso3)
    actor_id = session.get("user_id") or "unknown"
    triggered_by = f"admin:{actor_id}"

    # Mode-Resolution: explizites mode-Feld hat Vorrang. Legacy `force=true`
    # bei Default-Mode 'smart' wird auf 'force' gemappt (Backward-Compat).
    mode = body.mode or "smart"
    if body.force and mode == "smart":
        mode = "force"

    params = HarvestParams(
        country_iso3=country_iso3,
        region_codes=list(body.regions or []),
        since=body.since,
        until=body.until,
        limit=int(body.limit),
        page_size=100,
        triggered_by=triggered_by,
        source_key=source_key,
        mode=mode,
    )
    log.info(
        "Admin-Harvest start: mode=%s country=%s source=%s (Actor=%s)",
        mode, country_iso3, source_key, actor_id,
    )
    try:
        result = run_harvest(db, params, check_only=False)
    except Exception as exc:  # noqa: BLE001
        log.exception("Admin-Harvest fehlgeschlagen")
        raise HTTPException(502, f"Harvest fehlgeschlagen: {exc}") from exc

    return {
        "run_id": result.run_id,
        "status": result.status,
        "mode": mode,
        "records_seen": result.records_seen,
        "records_inserted": result.records_inserted,
        "records_updated": result.records_updated,
        "records_skipped": result.records_skipped,
        "records_failed": result.records_failed,
        "pages_fetched": result.pages_fetched,
        "error": result.error,
        "country_iso3": country_iso3,
        "source_key": source_key,
        "triggered_by": triggered_by,
    }


# ── LLM-Frage-Endpoint (Plan §11.5) ──────────────────────────────────────────


class AskRequest(BaseModel):
    """Klartext-Frage an das State-Aid-Register.

    Architektur (zwei LLM-Calls + ein SQL-Call dazwischen) ist in
    `services/state_aid_llm.py` dokumentiert. Garantie: Daten kommen
    ausschliesslich aus SQL, das LLM paraphrasiert nur Aggregate.
    """
    question: str = Field(..., min_length=3, max_length=2000)
    country_code: str | None = Field(
        None, max_length=3,
        description="Optionaler UI-Voreinsteller — DE oder AT.",
    )
    locale: str = Field("de", max_length=8, description="Antwortsprache (aktuell nur 'de').")
    limit: int = Field(50, ge=1, le=200,
                       description="Max. Anzahl Treffer fuer SQL und Stats.")


def _sse_event(event_type: str, payload: dict) -> str:
    """Baut einen benannten SSE-Event-Frame.

    Format:
      event: <type>
      data: {"...": ...}
      \\n
    """
    body = json.dumps(payload, ensure_ascii=False, default=str)
    return f"event: {event_type}\ndata: {body}\n\n"


def _run_search_with_filter(
    db: Session,
    *,
    filter_dict: dict[str, Any],
    limit: int,
) -> list[dict]:
    """Fuehrt die SQL-Suche mit einem normalisierten Filter-Dict aus.

    Re-Use von `_apply_award_filters` und `fuzzy_match_company` aus diesem
    Router. Liefert serialisierte Awards (Dict-Form).
    """
    cc = filter_dict.get("country_code")
    q_text = filter_dict.get("q")

    # Datums-Felder bei Bedarf in date() konvertieren
    since = filter_dict.get("since")
    until = filter_dict.get("until")
    if isinstance(since, str):
        try:
            since = date.fromisoformat(since)
        except ValueError:
            since = None
    if isinstance(until, str):
        try:
            until = date.fromisoformat(until)
        except ValueError:
            until = None

    # Strategie: wenn `q` gesetzt ist, vorab fuzzy + ID-Filter; sonst direkter Filter
    if q_text:
        hits = fuzzy_match_company(
            db, q_text, limit=limit * 3, min_score=65.0, country_code=cc,
        )
        if not hits:
            return []
        base_query = db.query(StateAidAward).filter(
            StateAidAward.id.in_([h.award_id for h in hits])
        )
    else:
        base_query = db.query(StateAidAward)

    base_query = _apply_award_filters(
        base_query,
        country_code=cc,
        nuts_code=filter_dict.get("nuts_code"),
        since=since,
        until=until,
        min_amount=filter_dict.get("min_amount"),
        max_amount=filter_dict.get("max_amount"),
        aid_instrument=filter_dict.get("aid_instrument"),
        objective=filter_dict.get("objective"),
        granting_authority=filter_dict.get("granting_authority"),
        sa_reference=filter_dict.get("sa_reference"),
        source_key=filter_dict.get("source_key"),
    )

    base_query = base_query.order_by(
        StateAidAward.aid_amount_eur.desc().nullslast(),
        StateAidAward.granting_date.desc().nullslast(),
    )
    awards = base_query.limit(limit).all()
    return [_serialize_award(a) for a in awards]


def _log_ask(
    request: Request,
    question: str,
    *,
    filter_dict: dict[str, Any],
    total_hits: int,
    elapsed_ms: int,
    response_excerpt: str | None = None,
    error: str | None = None,
) -> None:
    """Schreibt den /ask-Aufruf in `LlmQuestionLog`. Non-blocking.

    Plan v3.2 §16.4 — wir markieren den Eintrag mit scenario=99
    (ausserhalb der 6 Workshop-Szenarien) und matched_mode='state_aid_ask'.
    """
    try:
        import hashlib
        from database import SessionLocal
        from models.automation import LlmQuestionLog
        from routers.auth import _session_from_request

        sess = _session_from_request(request)
        ip = request.client.host if request.client else ""
        ip_h = (
            hashlib.sha256((ip + ":auditworkshop").encode()).hexdigest()[:32]
            if ip else None
        )
        normalized = " ".join((question or "").lower().split())[:480]
        excerpt = (response_excerpt or json.dumps(filter_dict, ensure_ascii=False))[:500]

        db_log = SessionLocal()
        try:
            db_log.add(LlmQuestionLog(
                user_id=sess.get("user_id") if sess else None,
                ip_hash=ip_h,
                # Wir verwenden 99 als Sentinel fuer "kein Workshop-Szenario".
                scenario=99,
                prompt=(question or "")[:4000],
                prompt_normalized=normalized,
                answer_path="state_aid_ask",
                matched_mode="state_aid_ask",
                items_returned=total_hits,
                model_name="state-aid-llm",
                elapsed_ms=elapsed_ms,
                response_excerpt=excerpt,
                response_total_chars=len(excerpt) if excerpt else None,
                error_message=error,
            ))
            db_log.commit()
        finally:
            db_log.close()
    except Exception:  # noqa: BLE001
        log.exception("LLM-Logging /ask fehlgeschlagen (non-blocking)")


@router.post("/ask")
async def ask(
    req: AskRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Klartext-Frage -> Filter-JSON -> SQL -> Klartext-Zusammenfassung (Plan §11.5).

    Streaming via SSE. Eventtypen:
      - status         : Pipeline-Schritt (filter | search | summary)
      - filter         : Erkannter Filter (sanitisiert) + raw_llm-Output
      - relax          : Filter wurde gelockert (filter zu eng -> 0 Treffer)
      - results        : SQL-Treffer (max. limit) + berechnete Stats
      - summary_token  : einzelner LLM-Token fuer die Zusammenfassung
      - done           : Abschluss + elapsed_ms
      - error          : Fehler (mit kurzer Beschreibung)

    Garantie: Betraege/Namen/Behoerden in `results` stammen aus SQL.
    Das LLM darf in `summary_token` nur die berechneten Aggregate paraphrasieren
    und gibt den Pflicht-Disclaimer am Ende aus.
    """
    # Rate-Limit: 6 Requests / 60s pro user_id bzw. IP. Schutz fuer die
    # GPU-Last (jeder /ask-Request triggert zwei LLM-Calls auf qwen3:14b).
    _check_rate_limit("ask", request)
    t_start = time.monotonic()
    question = req.question.strip()
    country_code = req.country_code

    async def gen():
        nonlocal country_code
        elapsed_ms = 0
        total_hits = 0
        filter_dict: dict[str, Any] = {}
        first_error: str | None = None
        log_excerpt: str | None = None

        try:
            # Schritt 1: LLM-Filter-Uebersetzung
            yield _sse_event("status", {"step": "filter"})
            try:
                filter_dict, raw_llm, source = await parse_question(
                    question, country_code=country_code, timeout_s=15.0,
                )
            except Exception as exc:  # noqa: BLE001
                log.exception("parse_question failed")
                # Wir bleiben gnaedig: weiter mit leerem Filter (Fulltext-Fallback)
                filter_dict, raw_llm, source = {}, "", "fallback"
                first_error = first_error or f"filter:{exc}"

            # Wenn LLM ueberhaupt nichts liefert und auch kein Fallback greift:
            # immerhin die Frage als q durchreichen, sonst gibt es 0 Treffer.
            if not filter_dict and question:
                filter_dict = {"q": question}
                source = "fallback"

            yield _sse_event("filter", {
                "filter": filter_dict,
                "raw_llm": raw_llm[:1500],
                "source": source,
            })

            # Schritt 2: SQL-Suche (mit Auto-Lockerung bei 0 Treffern)
            yield _sse_event("status", {"step": "search"})
            hits: list[dict] = []
            relaxations: list[str] = []
            try:
                hits = _run_search_with_filter(
                    db, filter_dict=filter_dict, limit=req.limit,
                )
                # Bei 0 Treffern bis zu 3x lockern.
                attempt = 0
                while not hits and attempt < 3:
                    new_filter, removed = relax_filters(filter_dict)
                    if not removed:
                        break
                    relaxations.append(removed)
                    yield _sse_event("relax", {
                        "removed_field": removed,
                        "new_filter": new_filter,
                    })
                    filter_dict = new_filter
                    hits = _run_search_with_filter(
                        db, filter_dict=filter_dict, limit=req.limit,
                    )
                    attempt += 1
            except Exception as exc:  # noqa: BLE001
                log.exception("SQL-Suche fehlgeschlagen")
                first_error = first_error or f"search:{exc}"
                yield _sse_event("error", {
                    "step": "search",
                    "message": f"SQL-Suche fehlgeschlagen: {exc}",
                })
                # Wir streamen trotzdem ein leeres Ergebnis, damit das UI fortfaehrt.
                hits = []

            total_hits = len(hits)
            stats: HitStats = compute_stats(hits)

            yield _sse_event("results", {
                "total_hits": total_hits,
                "hits": hits,
                "stats": stats.to_dict(),
                "filter_used": filter_dict,
                "relaxations": relaxations,
            })

            # Schritt 3: Klartext-Zusammenfassung streamen
            yield _sse_event("status", {"step": "summary"})
            summary_parts: list[str] = []
            try:
                async for token in stream_summary(
                    question, hits, stats, timeout_s=30.0,
                ):
                    summary_parts.append(token)
                    yield _sse_event("summary_token", {"text": token})
            except Exception as exc:  # noqa: BLE001
                log.exception("Summary-Stream fehlgeschlagen")
                first_error = first_error or f"summary:{exc}"
                yield _sse_event("error", {
                    "step": "summary",
                    "message": f"Summary-Stream fehlgeschlagen: {exc}",
                })

            log_excerpt = "".join(summary_parts)[:480]
            elapsed_ms = int((time.monotonic() - t_start) * 1000)
            yield _sse_event("done", {
                "elapsed_ms": elapsed_ms,
                "total_hits": total_hits,
                "filter_used": filter_dict,
            })
        except Exception as exc:  # noqa: BLE001
            log.exception("/ask gen-Loop fehlgeschlagen")
            first_error = first_error or f"gen:{exc}"
            elapsed_ms = int((time.monotonic() - t_start) * 1000)
            yield _sse_event("error", {
                "message": str(exc),
                "elapsed_ms": elapsed_ms,
            })
        finally:
            # Logging non-blocking — niemals den Stream blockieren.
            try:
                _log_ask(
                    request, question,
                    filter_dict=filter_dict,
                    total_hits=total_hits,
                    elapsed_ms=elapsed_ms or int((time.monotonic() - t_start) * 1000),
                    response_excerpt=log_excerpt,
                    error=first_error,
                )
            except Exception:  # noqa: BLE001
                log.exception("Final logging /ask fehlgeschlagen")

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Cross-Register-Pruefbericht (Plan §7.4) ──────────────────────────────────


class PersonInput(BaseModel):
    """Vom Pruefer eingegebene Person (Geschaeftsfuehrer, UBO, Gesellschafter).

    Wird gegen alle 5 Sanctions-Listen (schema='Person') gematcht — siehe
    services/state_aid_audit_report.py _build_persons_check_section.
    """
    name: str = Field(..., min_length=2, max_length=200)
    role: str | None = Field(None, max_length=80)


class AuditReportPdfRequest(BaseModel):
    """Body fuer POST /audit-report/pdf.

    Alle Felder ausser `q` sind optional und werden vom Pruefer beim
    Erzeugen frei eingegeben. Sie werden 1:1 in den PDF-Footer und ins
    Audit-Log uebernommen — keine Validierung gegen externe Listen.
    """
    q: str = Field(..., min_length=2, max_length=200)
    country_code: str | None = Field(None, max_length=3)
    auftraggeber: str | None = Field(None, max_length=120)
    pruefer_name: str | None = Field(None, max_length=120)
    # Konzernverbund-Erweiterung (Mai 2026, Item 2): Toechter aus GLEIF +
    # Wikidata mitberuecksichtigen. Default false — der Lookup dauert ~5-15s
    # (zwei externe APIs) und soll nur auf Wunsch aktiviert werden.
    include_corporate_group: bool = Field(
        False,
        description=(
            "Wenn true, wird ueber GLEIF + Wikidata der Konzernverbund "
            "aufgeloest und Tochterfirmen werden separat in State-Aid und "
            "Beneficiaries gesucht. Lookup-Dauer: 5-15 Sekunden."
        ),
    )
    # Layer A: Embedding-Layer (bge-m3) — semantisch aehnliche Records.
    include_semantic_neighbors: bool = Field(
        False,
        description=(
            "Wenn true, werden top-N semantisch aehnliche Records pro Modul "
            "(state_aid|beneficiary|sanctions) als Cross-References hinzu-"
            "gefuegt und im PDF als eigene Sektion ausgewiesen. Strikt neu-"
            "tral, kein Identitaets-Beweis. Voraussetzung: Embedding-Index "
            "gebaut (scripts/rebuild_embeddings.py)."
        ),
    )
    # Layer B: LLM-Re-Ranker fuer ambivalente Cross-References (Score 75..89).
    include_llm_verification: bool = Field(
        False,
        description=(
            "Wenn true, werden ambivalente Cross-References (Score 75..89) "
            "durch das LLM nachgeprueft. Pro Match ein Verdict (yes/no/"
            "unknown + Confidence + 1-Satz-Begruendung). Bei `match=no` wird "
            "der Querbezug aus dem PDF gefiltert (raw bleibt im Audit-Trail). "
            "Latenz: ~2-3 Min bei Top-20 Matches. On-demand."
        ),
    )
    # Polish-Runde 3, Aufgabe 1: Personen-Eingabe fuer Sanctions-Personen-Check.
    persons: list[PersonInput] = Field(
        default_factory=list,
        max_length=20,
        description=(
            "Optional: Personen (Geschaeftsfuehrer, UBO, Gesellschafter), "
            "die gegen alle 5 Sanctions-Listen mit schema='Person' gematcht "
            "werden sollen. Maximal 20 Eintraege."
        ),
    )


def _parse_persons_query(persons_param: list[str] | None) -> list[dict]:
    """Parst die `persons`-GET-Query (Format ``Name|Rolle``).

    Beispiele:
      ?persons=Max%20Mustermann%7CGesch%C3%A4ftsf%C3%BChrer
      ?persons=Jane%20Doe%7CUBO&persons=John%20Smith
    """
    out: list[dict] = []
    if not persons_param:
        return out
    for raw in persons_param:
        if not raw:
            continue
        s = str(raw)
        # Format: Name|Rolle
        if "|" in s:
            name_raw, role_raw = s.split("|", 1)
        else:
            name_raw, role_raw = s, ""
        name = name_raw.strip()
        role = role_raw.strip() or None
        if not name or len(name) < 2:
            continue
        out.append({"name": name[:200], "role": (role[:80] if role else None)})
        if len(out) >= 20:
            break
    return out


@router.get("/audit-report")
def get_audit_report_json(
    q: str = Query(..., min_length=2, max_length=200,
                    description="Beguenstigter / Firmenname."),
    country_code: str | None = Query(None, max_length=3),
    auftraggeber: str | None = Query(None, max_length=120),
    include_corporate_group: bool = Query(
        False,
        description=(
            "Konzernverbund-Erweiterung. Wenn true, GLEIF + Wikidata werden "
            "befragt und Tochterfirmen separat in State-Aid + Beneficiaries "
            "gesucht. Default: false (schneller Default-Pfad)."
        ),
    ),
    include_semantic_neighbors: bool = Query(
        False,
        description=(
            "Layer A — Embedding-Layer (bge-m3). Wenn true, werden top-N "
            "semantisch aehnliche Records pro Modul als Cross-References "
            "hinzugefuegt. Voraussetzung: Embedding-Index gebaut (siehe "
            "scripts/rebuild_embeddings.py). Strikt neutral, kein Identitaets-"
            "Beweis."
        ),
    ),
    include_llm_verification: bool = Query(
        False,
        description=(
            "Layer B — LLM-Re-Ranker. Wenn true, prueft das LLM ambivalente "
            "Cross-References (Score 75..89) und liefert pro Match ein "
            "Verdict (yes/no/unknown). Latenz: ~2-3 Min bei Top-20 Matches."
        ),
    ),
    persons: list[str] | None = Query(
        None,
        description=(
            "Optional: Personen-Liste fuer Sanctions-Check (Format "
            "`Name|Rolle`, URL-encoded). Beispiel: "
            "?persons=Max%20Mustermann%7CGeschaeftsfuehrer. Maximal 20."
        ),
    ),
    db: Session = Depends(get_db),
    request: Request = None,  # type: ignore[assignment]
) -> dict:
    """Cross-Register-Pruefbericht als JSON (UI-Live-Vorschau).

    Aggregiert State-Aid + Beneficiaries + Sanctions zu einem strukturierten
    Bericht. Faktisch, ohne Bewertung. Oeffentlich (Plan §13).
    """
    from services.state_aid_audit_report import build_audit_report

    cc = country_code.upper() if country_code else None
    persons_list = _parse_persons_query(persons)

    pruefer_user_id = None
    if request is not None:
        try:
            from routers.auth import _session_from_request
            sess = _session_from_request(request)
            pruefer_user_id = (sess or {}).get("user_id") if sess else None
        except Exception:  # noqa: BLE001
            pruefer_user_id = None

    data = build_audit_report(
        db, q,
        country_code=cc,
        auftraggeber=auftraggeber,
        pruefer_name=None,  # Pruefer-Name nur fuer PDF-Footer relevant
        include_corporate_group=bool(include_corporate_group),
        include_semantic_neighbors=bool(include_semantic_neighbors),
        include_llm_verification=bool(include_llm_verification),
        persons=persons_list or None,
        pruefer_user_id=pruefer_user_id,
    )
    return data.to_dict()


@router.get("/corporate-group")
def get_corporate_group(
    q: str = Query(..., min_length=2, max_length=200,
                    description="Firmenname (Konzern-Anker)."),
    include_children: bool = Query(True),
    max_children: int = Query(50, ge=0, le=500),
    timeout_seconds: float = Query(30.0, ge=5.0, le=60.0),
    db: Session = Depends(get_db),
) -> dict:
    """Standalone Konzernverbund-Lookup (Item 2 / Mai 2026).

    Liefert die CorporateGroup ohne den Audit-Report-Aufbau — fuer
    Frontend-Vorschau und API-Integrationen. Cache-Hint im Response
    (`cache_meta.cache`: 'hit' | 'miss' | 'stale-refreshed' | 'disabled').

    Quellen: GLEIF Public API + Wikidata SPARQL (beide kostenlos, oeffentlich).
    """
    from services.corporate_registry import lookup_corporate_group_cached

    try:
        group, meta = lookup_corporate_group_cached(
            db, q,
            include_children=bool(include_children),
            max_children=int(max_children),
            timeout_seconds=float(timeout_seconds),
            use_cache=True,
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("Corporate-Group-Lookup fehlgeschlagen")
        raise HTTPException(
            502, f"Corporate-Group-Lookup fehlgeschlagen: {exc}",
        ) from exc

    return {
        "query": q,
        "group": group.to_dict(),
        "cache_meta": meta,
        "coverage_note": group.coverage_note,
        "sources_used": group.sources_used,
    }


@router.post("/audit-report/pdf")
def post_audit_report_pdf(
    body: AuditReportPdfRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Cross-Register-Pruefbericht als PDF.

    Persistiert die Anfrage in `workshop_audit_report_log` (Audit-Trail).
    Liefert das PDF als Stream mit Content-Disposition: attachment.
    Oeffentlich (Plan §13) — alle Daten stammen aus oeffentlichen Quellen.
    """
    import hashlib
    import re as _re

    from services.state_aid_audit_report import build_audit_report
    from services.state_aid_audit_pdf import render_audit_report_pdf
    from models.state_aid_audit import AuditReportLog

    cc = body.country_code.upper() if body.country_code else None
    # Personen-Liste serialisieren (Pydantic → dicts), auch leere Liste ist ok.
    persons_payload: list[dict] = []
    for p in (body.persons or []):
        if not p or not p.name:
            continue
        persons_payload.append({
            "name": (p.name or "").strip()[:200],
            "role": (p.role.strip()[:80] if p.role else None),
        })

    pruefer_user_id_pdf = None
    try:
        from routers.auth import _session_from_request
        sess_pdf = _session_from_request(request)
        pruefer_user_id_pdf = (sess_pdf or {}).get("user_id") if sess_pdf else None
    except Exception:  # noqa: BLE001
        pruefer_user_id_pdf = None

    try:
        data = build_audit_report(
            db, body.q,
            country_code=cc,
            auftraggeber=body.auftraggeber,
            pruefer_name=body.pruefer_name,
            include_corporate_group=bool(body.include_corporate_group),
            include_semantic_neighbors=bool(body.include_semantic_neighbors),
            include_llm_verification=bool(body.include_llm_verification),
            persons=persons_payload or None,
            pruefer_user_id=pruefer_user_id_pdf,
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("Audit-Report Aggregation fehlgeschlagen")
        raise HTTPException(500, f"Bericht konnte nicht erstellt werden: {exc}") from exc

    try:
        pdf_bytes = render_audit_report_pdf(data)
    except Exception as exc:  # noqa: BLE001
        log.exception("Audit-Report PDF-Rendering fehlgeschlagen")
        raise HTTPException(500, f"PDF-Erzeugung fehlgeschlagen: {exc}") from exc

    # Persistierung des Audit-Logs (Best-Effort).
    try:
        from routers.auth import _session_from_request
        sess = _session_from_request(request)
        pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()
        log_row = AuditReportLog(
            query=body.q[:255],
            auftraggeber=body.auftraggeber,
            pruefer_name=body.pruefer_name,
            pruefer_user_id=(sess or {}).get("user_id") if sess else None,
            state_aid_hits=int(data.state_aid.total_count),
            beneficiaries_hits=int(data.beneficiaries.total_count),
            sanctions_hits=int(data.sanctions.total_hits),
            cross_references=int(len(data.cross_references)),
            pdf_size_bytes=int(len(pdf_bytes)),
            pdf_sha256=pdf_hash,
        )
        db.add(log_row)
        db.commit()
    except Exception:  # noqa: BLE001
        # Log darf das Ergebnis nicht blockieren.
        log.exception("Audit-Report Log-Persistierung fehlgeschlagen")
        db.rollback()

    safe_name = _re.sub(r"[^A-Za-z0-9._-]+", "_", body.q.strip())[:60] or "bericht"
    filename = f"pruefbericht_{safe_name}.pdf"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-Content-Type-Options": "nosniff",
    }
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers=headers,
    )


@router.get("/audit-report/log")
def get_audit_report_log(
    limit: int = Query(50, ge=1, le=500),
    _session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Admin: Liste der zuletzt erzeugten Pruefberichte (Metadaten).

    Liefert KEINE PDFs zurueck — nur Audit-Trail-Daten.
    """
    from models.state_aid_audit import AuditReportLog

    rows = (
        db.query(AuditReportLog)
        .order_by(AuditReportLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "count": len(rows),
        "items": [
            {
                "id": int(r.id),
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "query": r.query,
                "auftraggeber": r.auftraggeber,
                "pruefer_name": r.pruefer_name,
                "pruefer_user_id": r.pruefer_user_id,
                "state_aid_hits": int(r.state_aid_hits or 0),
                "beneficiaries_hits": int(r.beneficiaries_hits or 0),
                "sanctions_hits": int(r.sanctions_hits or 0),
                "cross_references": int(r.cross_references or 0),
                "pdf_size_bytes": int(r.pdf_size_bytes or 0),
                "pdf_sha256": r.pdf_sha256,
            }
            for r in rows
        ],
    }


@router.get("/audit-report/log/export")
def export_audit_report_log(
    format: str = Query("csv", pattern="^(csv|xlsx)$"),
    limit: int = Query(500, ge=1, le=5000),
    _session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin: Audit-Trail der erzeugten Pruefberichte als CSV oder XLSX.

    Liefert NUR Metadaten — keine PDFs. Format-Default ist CSV (UTF-8 mit BOM
    fuer Excel-Kompatibilitaet).
    """
    from models.state_aid_audit import AuditReportLog

    rows = (
        db.query(AuditReportLog)
        .order_by(AuditReportLog.created_at.desc())
        .limit(limit)
        .all()
    )
    log_columns = [
        "id", "created_at", "query", "auftraggeber",
        "pruefer_name", "pruefer_user_id",
        "state_aid_hits", "beneficiaries_hits", "sanctions_hits",
        "cross_references", "pdf_size_bytes", "pdf_sha256",
    ]
    serialized = [
        {
            "id": int(r.id),
            "created_at": r.created_at.isoformat() if r.created_at else "",
            "query": r.query or "",
            "auftraggeber": r.auftraggeber or "",
            "pruefer_name": r.pruefer_name or "",
            "pruefer_user_id": r.pruefer_user_id or "",
            "state_aid_hits": int(r.state_aid_hits or 0),
            "beneficiaries_hits": int(r.beneficiaries_hits or 0),
            "sanctions_hits": int(r.sanctions_hits or 0),
            "cross_references": int(r.cross_references or 0),
            "pdf_size_bytes": int(r.pdf_size_bytes or 0),
            "pdf_sha256": r.pdf_sha256 or "",
        }
        for r in rows
    ]

    pflichthinweis = (
        "Audit-Trail der Cross-Register-Pruefberichte. Enthaelt NUR Metadaten — "
        "keine PDFs, keine Bewertungen, kein Risiko-Score. SHA256 erlaubt die "
        "Reproduktion (gleiche Eingabe + gleicher Datenstand = gleicher Hash)."
    )

    if format == "xlsx":
        from services.excel_export import (
            XLSX_MEDIA_TYPE,
            make_xlsx,
            xlsx_response_headers,
        )
        xlsx_bytes = make_xlsx(
            serialized,
            sheet_name="Audit-Trail",
            headers=log_columns,
            table_name="AuditTrail",
            pflichthinweis=pflichthinweis,
            metadata={
                "Anzahl Eintraege": str(len(serialized)),
                "Limit": str(limit),
            },
            notes_title="Pruefbericht-Audit-Trail · Hinweise",
        )
        filename = f"audit_trail_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return StreamingResponse(
            iter([xlsx_bytes]),
            media_type=XLSX_MEDIA_TYPE,
            headers=xlsx_response_headers(filename),
        )

    # CSV-Export — UTF-8 mit BOM fuer Excel
    buf = io.StringIO()
    buf.write("﻿")  # BOM
    buf.write(f"# FlowWorkshop · Pruefbericht-Audit-Trail · {datetime.utcnow().isoformat()}Z\n")
    buf.write(f"# {pflichthinweis}\n")
    buf.write(f"# Anzahl Eintraege: {len(serialized)}\n")
    writer = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(log_columns)
    for d in serialized:
        writer.writerow([d.get(k, "") for k in log_columns])

    filename = f"audit_trail_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/awards/{source_key}")
def admin_delete_source_awards(
    source_key: str,
    _session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Admin: Loescht alle Awards einer Quelle (idempotent)."""
    deleted = (
        db.query(StateAidAward)
        .filter(StateAidAward.source_key == source_key)
        .delete(synchronize_session=False)
    )
    db.commit()
    # record_count im Source-Eintrag mit-aktualisieren, falls vorhanden
    src = db.query(StateAidSource).filter(StateAidSource.source_key == source_key).first()
    if src:
        src.record_count = 0
        src.quality = "red"
        db.commit()
    log.warning("Admin-Delete: %d Awards aus '%s' entfernt.", deleted, source_key)
    return {"deleted": int(deleted), "source_key": source_key}
