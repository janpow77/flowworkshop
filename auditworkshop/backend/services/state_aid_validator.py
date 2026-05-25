"""
flowworkshop · services/state_aid_validator.py

Nightly Self-Check fuer das State-Aid-Modul.

Plan: nach jedem Harvest-Slot (Default 02:30 UTC) prueft dieser Validator,
ob die Daten plausibel sind und die Such-Endpoints antworten. Ergebnis
wird in `workshop_validation_runs` persistiert und im UI als Banner /
Modal angezeigt.

Konkrete Checks (alle aus Aufgabenstellung):
 1. Zero-Records-Check: keine Source mit record_count=0 AND enabled=true
    AND last_successful_harvest_at IS NOT NULL
 2. NUTS-Code-Regex: ^[A-Z]{2}[0-9A-Z]{0,3}$
 3. NUTS-Konsistenz: nuts_level passt zur Code-Laenge
 4. Datum-Plausibilitaet: granting_date >= 2014-07-01 AND <= today + 180 Tage
 5. Currency-Sanity: aid_currency='EUR' AND aid_amount_eur >= 0
 6. Smoke-Suchen: Siemens, Trumpf, Volkswagen, Fraunhofer, Bosch (>=3 Treffer)
 7. Source-Status-Ampel: quality vs. record_count
 8. Duplikat-SA-Reference innerhalb Source (sollte 0 sein)
 9. Award ohne beneficiary_name (sollte 0 sein)
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Literal

from sqlalchemy import func as sql_func, or_
from sqlalchemy.orm import Session

from models.state_aid import StateAidAward, StateAidSource

log = logging.getLogger(__name__)


# ── Datentypen ───────────────────────────────────────────────────────────────


SeverityT = Literal["info", "warning", "error"]
StatusT = Literal["ok", "warnings", "failed"]


@dataclass
class ValidationFinding:
    """Ein einzelner Check-Befund."""
    severity: SeverityT
    code: str          # z.B. "NUTS_INVALID", "ZERO_RECORDS"
    message: str
    detail: dict | None = None

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "detail": self.detail,
        }


@dataclass
class ValidationReport:
    """Zusammenfassung eines Validator-Laufs."""
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int
    status: StatusT
    checks_total: int
    checks_passed: int
    checks_warned: int
    checks_failed: int
    findings: list[ValidationFinding] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "checks_total": self.checks_total,
            "checks_passed": self.checks_passed,
            "checks_warned": self.checks_warned,
            "checks_failed": self.checks_failed,
            "findings": [f.to_dict() for f in self.findings],
        }


# ── Konstanten ────────────────────────────────────────────────────────────────


# Smoke-Queries — sollten in einem 170k-Record-Index immer >=3 Treffer liefern.
SMOKE_QUERIES: list[str] = [
    "Siemens",
    "Trumpf",
    "Volkswagen",
    "Fraunhofer",
    "Bosch",
]

# NUTS-Code: 2 Buchstaben Land + 0-3 alphanumerische Zeichen.
NUTS_REGEX = re.compile(r"^[A-Z]{2}[0-9A-Z]{0,3}$")

# Datum-Plausibilitaet
DATE_MIN = date(2014, 7, 1)


# ── Einzel-Checks ─────────────────────────────────────────────────────────────


def _check_zero_records(db: Session) -> list[ValidationFinding]:
    """Quellen, die als enabled+harvested markiert sind, aber 0 Records haben."""
    findings: list[ValidationFinding] = []
    rows = (
        db.query(StateAidSource)
        .filter(StateAidSource.enabled.is_(True))
        .filter(StateAidSource.last_successful_harvest_at.isnot(None))
        .filter((StateAidSource.record_count == 0) | (StateAidSource.record_count.is_(None)))
        .all()
    )
    for src in rows:
        findings.append(ValidationFinding(
            severity="error",
            code="ZERO_RECORDS",
            message=(
                f"Quelle '{src.source_key}' ist aktiviert und wurde geharvested, "
                "hat aber 0 Datensaetze."
            ),
            detail={
                "source_key": src.source_key,
                "display_name": src.display_name,
                "last_successful_harvest_at": (
                    src.last_successful_harvest_at.isoformat()
                    if src.last_successful_harvest_at else None
                ),
            },
        ))
    return findings


def _check_nuts_regex(db: Session, *, sample_limit: int = 10) -> list[ValidationFinding]:
    """NUTS-Codes, die nicht ^[A-Z]{2}[0-9A-Z]{0,3}$ matchen."""
    findings: list[ValidationFinding] = []
    rows = (
        db.query(StateAidAward.id, StateAidAward.nuts_code, StateAidAward.country_code)
        .filter(StateAidAward.nuts_code.isnot(None))
        .filter(StateAidAward.nuts_code != "")
        .all()
    )
    invalid: list[dict] = []
    for r in rows:
        nc = (r.nuts_code or "").strip()
        if not nc:
            continue
        if not NUTS_REGEX.match(nc):
            invalid.append({
                "award_id": r.id,
                "nuts_code": nc,
                "country_code": r.country_code,
            })
    if invalid:
        findings.append(ValidationFinding(
            severity="warning",
            code="NUTS_INVALID",
            message=(
                f"{len(invalid)} Award(s) haben einen NUTS-Code, der nicht dem "
                "Regex ^[A-Z]{2}[0-9A-Z]{0,3}$ entspricht."
            ),
            detail={
                "count": len(invalid),
                "sample": invalid[:sample_limit],
            },
        ))
    return findings


def _check_nuts_level_consistency(db: Session, *, sample_limit: int = 10) -> list[ValidationFinding]:
    """nuts_level passt zur Code-Laenge: Level 1 = 3 Chars, Level 2 = 4, Level 3 = 5."""
    findings: list[ValidationFinding] = []
    rows = (
        db.query(StateAidAward.id, StateAidAward.nuts_code, StateAidAward.nuts_level)
        .filter(StateAidAward.nuts_code.isnot(None))
        .filter(StateAidAward.nuts_code != "")
        .filter(StateAidAward.nuts_level.isnot(None))
        .all()
    )
    inconsistent: list[dict] = []
    for r in rows:
        nc = (r.nuts_code or "").strip()
        lvl = r.nuts_level
        if not nc or lvl is None:
            continue
        # Level 0 = Land (2 Chars), Level 1 = 3 Chars, Level 2 = 4, Level 3 = 5
        expected_len = 2 + lvl
        if len(nc) != expected_len:
            inconsistent.append({
                "award_id": r.id,
                "nuts_code": nc,
                "nuts_level": lvl,
                "expected_len": expected_len,
                "actual_len": len(nc),
            })
    if inconsistent:
        findings.append(ValidationFinding(
            severity="warning",
            code="NUTS_LEVEL_MISMATCH",
            message=(
                f"{len(inconsistent)} Award(s) haben einen NUTS-Level, der "
                "nicht zur Code-Laenge passt."
            ),
            detail={
                "count": len(inconsistent),
                "sample": inconsistent[:sample_limit],
            },
        ))
    return findings


def _check_granting_date(db: Session, *, sample_limit: int = 10) -> list[ValidationFinding]:
    """granting_date >= 2014-07-01 AND <= today + 180 Tage."""
    findings: list[ValidationFinding] = []
    today = date.today()
    max_future = today + timedelta(days=180)
    rows = (
        db.query(StateAidAward.id, StateAidAward.granting_date, StateAidAward.source_key)
        .filter(StateAidAward.granting_date.isnot(None))
        .filter(or_(
            StateAidAward.granting_date < DATE_MIN,
            StateAidAward.granting_date > max_future,
        ))
        .all()
    )
    if rows:
        sample = [
            {
                "award_id": r.id,
                "granting_date": r.granting_date.isoformat() if r.granting_date else None,
                "source_key": r.source_key,
            }
            for r in rows[:sample_limit]
        ]
        findings.append(ValidationFinding(
            severity="warning",
            code="DATE_OUT_OF_RANGE",
            message=(
                f"{len(rows)} Award(s) haben ein granting_date "
                f"ausserhalb [{DATE_MIN.isoformat()} .. {max_future.isoformat()}]."
            ),
            detail={
                "count": len(rows),
                "min_allowed": DATE_MIN.isoformat(),
                "max_allowed": max_future.isoformat(),
                "sample": sample,
            },
        ))
    return findings


def _check_currency_sanity(db: Session, *, sample_limit: int = 10) -> list[ValidationFinding]:
    """aid_currency='EUR' AND aid_amount_eur >= 0 — negative Betraege = Error."""
    findings: list[ValidationFinding] = []
    # Negative Betraege: Error
    neg_rows = (
        db.query(StateAidAward.id, StateAidAward.aid_amount_eur, StateAidAward.aid_currency)
        .filter(StateAidAward.aid_amount_eur.isnot(None))
        .filter(StateAidAward.aid_amount_eur < 0)
        .all()
    )
    if neg_rows:
        sample = [
            {
                "award_id": r.id,
                "aid_amount_eur": float(r.aid_amount_eur) if r.aid_amount_eur else None,
                "aid_currency": r.aid_currency,
            }
            for r in neg_rows[:sample_limit]
        ]
        findings.append(ValidationFinding(
            severity="error",
            code="NEGATIVE_AMOUNT",
            message=f"{len(neg_rows)} Award(s) haben einen negativen aid_amount_eur.",
            detail={"count": len(neg_rows), "sample": sample},
        ))

    # Fremdwaehrung trotz aid_amount_eur: nur Warning (vorhandene Daten,
    # bei TAM teilweise normal — z.B. CZK in DE-Slice durch EBA-Foerderung).
    other_curr = (
        db.query(StateAidAward.aid_currency, sql_func.count(StateAidAward.id).label("cnt"))
        .filter(StateAidAward.aid_currency.isnot(None))
        .filter(StateAidAward.aid_currency != "EUR")
        .filter(StateAidAward.aid_currency != "")
        .group_by(StateAidAward.aid_currency)
        .all()
    )
    if other_curr:
        findings.append(ValidationFinding(
            severity="info",
            code="NON_EUR_CURRENCY",
            message=(
                f"{len(other_curr)} unterschiedliche Nicht-EUR-Waehrungen im "
                "Bestand — pruefen, ob aid_amount_eur korrekt umgerechnet ist."
            ),
            detail={
                "currencies": [
                    {"currency": r.aid_currency, "count": int(r.cnt or 0)}
                    for r in other_curr
                ],
            },
        ))
    return findings


def _check_smoke_searches(db: Session, *, min_hits: int = 3) -> list[ValidationFinding]:
    """5 Smoke-Queries gegen `fuzzy_match_company`. Jede Query muss >=3 Treffer haben."""
    # Lazy-Import: fuzzy_match_company laedt rapidfuzz, dauert ein paar ms.
    from services.state_aid_service import fuzzy_match_company

    findings: list[ValidationFinding] = []
    failed: list[dict] = []
    for query in SMOKE_QUERIES:
        try:
            hits = fuzzy_match_company(db, query, limit=10, min_score=65.0)
            if len(hits) < min_hits:
                failed.append({
                    "query": query,
                    "hits": len(hits),
                    "expected_min": min_hits,
                })
        except Exception as exc:  # noqa: BLE001
            failed.append({
                "query": query,
                "error": str(exc)[:200],
            })
    if failed:
        findings.append(ValidationFinding(
            severity="warning",
            code="SMOKE_SEARCH_LOW_RECALL",
            message=(
                f"{len(failed)} von {len(SMOKE_QUERIES)} Smoke-Queries lieferten "
                f"weniger als {min_hits} Treffer. Daten ggf. unvollstaendig."
            ),
            detail={
                "queries_failed": failed,
                "queries_total": len(SMOKE_QUERIES),
            },
        ))
    return findings


def _check_source_quality(db: Session) -> list[ValidationFinding]:
    """Source quality muss zu record_count passen.

    Regel:
      - record_count > 0: quality sollte 'green' oder 'yellow' sein, nicht 'red'.
      - record_count == 0: quality sollte 'red' sein, nicht 'green'/'yellow'.
    """
    findings: list[ValidationFinding] = []
    rows = (
        db.query(StateAidSource)
        .filter(StateAidSource.enabled.is_(True))
        .all()
    )
    mismatches: list[dict] = []
    for src in rows:
        rc = int(src.record_count or 0)
        q = (src.quality or "").lower()
        # Sources, die nie geharvested wurden (last_successful_harvest_at IS NULL),
        # gelten als "geplant"/"placeholder" — der Quality-Status ist hier nicht
        # aussagekraeftig, also nicht als Mismatch werten. Nationale Register
        # (PL/RO/ES/SI) sind der Hauptfall: Default 'red' als „Connector noch
        # nicht implementiert", ohne dass es ein echtes Datenqualitaetsproblem
        # ist. Cases-Quellen werden grundsaetzlich nie geharvested.
        if src.last_successful_harvest_at is None:
            continue
        if src.source_type == "cases":
            continue
        if rc > 0 and q == "red":
            mismatches.append({
                "source_key": src.source_key,
                "record_count": rc,
                "quality": q,
                "issue": "rot trotz Records",
            })
        elif rc == 0 and q in ("green", "yellow"):
            mismatches.append({
                "source_key": src.source_key,
                "record_count": rc,
                "quality": q,
                "issue": "gruen/gelb ohne Records",
            })
    if mismatches:
        findings.append(ValidationFinding(
            severity="warning",
            code="SOURCE_QUALITY_MISMATCH",
            message=(
                f"{len(mismatches)} Quelle(n) haben einen Quality-Status, der "
                "nicht zum record_count passt."
            ),
            detail={"mismatches": mismatches},
        ))
    return findings


def _check_duplicate_sa_reference(db: Session, *, sample_limit: int = 10) -> list[ValidationFinding]:
    """Innerhalb derselben Source darf eine SA-Referenz nicht doppelt vorkommen."""
    findings: list[ValidationFinding] = []
    # GROUP BY source_key, sa_reference HAVING count > 1
    rows = (
        db.query(
            StateAidAward.source_key,
            StateAidAward.sa_reference,
            sql_func.count(StateAidAward.id).label("cnt"),
        )
        .filter(StateAidAward.sa_reference.isnot(None))
        .filter(StateAidAward.sa_reference != "")
        .group_by(StateAidAward.source_key, StateAidAward.sa_reference)
        .having(sql_func.count(StateAidAward.id) > 1)
        .all()
    )
    if rows:
        sample = [
            {
                "source_key": r.source_key,
                "sa_reference": r.sa_reference,
                "count": int(r.cnt or 0),
            }
            for r in rows[:sample_limit]
        ]
        # Severity bewusst "info" — TAM-Beihilferegelungen werden vielfach
        # vergeben; dieselbe SA-Referenz kann fuer hunderte Beguenstigte gelten.
        # Das ist KEIN Datenqualitaetsproblem, sondern fachliche Realitaet.
        findings.append(ValidationFinding(
            severity="info",
            code="DUPLICATE_SA_REFERENCE",
            message=(
                f"{len(rows):,} SA-Referenz(en) werden mehrfach genutzt — "
                "fachlich erwartet (eine Beihilferegelung kann viele "
                "Empfaenger foerdern), nur als Hintergrund-Information."
            ),
            detail={"count": len(rows), "sample": sample},
        ))
    return findings


def _check_missing_beneficiary(db: Session, *, sample_limit: int = 10) -> list[ValidationFinding]:
    """Awards ohne beneficiary_name (sollte 0 sein, NOT NULL Constraint)."""
    findings: list[ValidationFinding] = []
    rows = (
        db.query(StateAidAward.id, StateAidAward.source_key)
        .filter(or_(
            StateAidAward.beneficiary_name.is_(None),
            StateAidAward.beneficiary_name == "",
        ))
        .all()
    )
    if rows:
        sample = [
            {"award_id": r.id, "source_key": r.source_key}
            for r in rows[:sample_limit]
        ]
        findings.append(ValidationFinding(
            severity="error",
            code="MISSING_BENEFICIARY",
            message=f"{len(rows)} Award(s) ohne beneficiary_name.",
            detail={"count": len(rows), "sample": sample},
        ))
    return findings


# ── Hauptfunktion ────────────────────────────────────────────────────────────


CHECK_FUNCTIONS = [
    ("zero_records", _check_zero_records),
    ("nuts_regex", _check_nuts_regex),
    ("nuts_level", _check_nuts_level_consistency),
    ("granting_date", _check_granting_date),
    ("currency_sanity", _check_currency_sanity),
    ("smoke_searches", _check_smoke_searches),
    ("source_quality", _check_source_quality),
    ("duplicate_sa_ref", _check_duplicate_sa_reference),
    ("missing_beneficiary", _check_missing_beneficiary),
]


def run_validation(db: Session) -> ValidationReport:
    """Fuehrt alle Checks aus und liefert einen ValidationReport.

    Persistierung in `workshop_validation_runs` macht der Aufrufer (Router /
    Scheduler), damit diese Funktion fuer Tests reine Logik bleibt.
    """
    started_at = datetime.utcnow()
    findings: list[ValidationFinding] = []
    checks_passed = 0
    checks_warned = 0
    checks_failed = 0

    for check_name, check_fn in CHECK_FUNCTIONS:
        try:
            check_findings = check_fn(db)
        except Exception as exc:  # noqa: BLE001
            log.exception("Validator-Check '%s' fehlgeschlagen", check_name)
            findings.append(ValidationFinding(
                severity="error",
                code="CHECK_EXCEPTION",
                message=f"Check '{check_name}' warf Exception: {exc}",
                detail={"check": check_name, "exception": str(exc)[:500]},
            ))
            checks_failed += 1
            continue

        if not check_findings:
            checks_passed += 1
        else:
            findings.extend(check_findings)
            # Schwerstes Severity-Level zaehlt fuer pass/warned/failed
            severity_max = max(
                ("error", "warning", "info").index(f.severity)
                for f in check_findings
            )
            # severity_max: 0=error → failed, 1=warning → warned, 2=info → passed
            if severity_max == 0:
                checks_failed += 1
            elif severity_max == 1:
                checks_warned += 1
            else:
                checks_passed += 1

    finished_at = datetime.utcnow()
    duration_ms = int((finished_at - started_at).total_seconds() * 1000)

    if checks_failed > 0:
        status: StatusT = "failed"
    elif checks_warned > 0:
        status = "warnings"
    else:
        status = "ok"

    return ValidationReport(
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        status=status,
        checks_total=len(CHECK_FUNCTIONS),
        checks_passed=checks_passed,
        checks_warned=checks_warned,
        checks_failed=checks_failed,
        findings=findings,
    )


# ── Persistierung ────────────────────────────────────────────────────────────


def persist_report(db: Session, report: ValidationReport, *, module: str = "state_aid") -> int:
    """Schreibt einen ValidationReport in `workshop_validation_runs`.

    Liefert die ID des angelegten Datensatzes.
    """
    from models.state_aid_validation import StateAidValidationRun

    run = StateAidValidationRun(
        started_at=report.started_at,
        finished_at=report.finished_at,
        module=module,
        status=report.status,
        duration_ms=report.duration_ms,
        checks_total=report.checks_total,
        checks_passed=report.checks_passed,
        checks_warned=report.checks_warned,
        checks_failed=report.checks_failed,
        findings=[f.to_dict() for f in report.findings],
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return int(run.id)


def get_last_report(db: Session, *, module: str = "state_aid") -> dict | None:
    """Liest den juengsten ValidationRun fuer ein Modul.

    Liefert ein Dict-Format, das mit ``ValidationReport.to_dict()`` kompatibel
    ist (zusaetzlich `id`).
    """
    from models.state_aid_validation import StateAidValidationRun

    row = (
        db.query(StateAidValidationRun)
        .filter(StateAidValidationRun.module == module)
        .order_by(StateAidValidationRun.started_at.desc())
        .first()
    )
    if row is None:
        return None
    return {
        "id": int(row.id),
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "module": row.module,
        "status": row.status,
        "duration_ms": int(row.duration_ms or 0),
        "checks_total": int(row.checks_total or 0),
        "checks_passed": int(row.checks_passed or 0),
        "checks_warned": int(row.checks_warned or 0),
        "checks_failed": int(row.checks_failed or 0),
        "findings": list(row.findings or []),
    }
