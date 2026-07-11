"""
flowworkshop · services/scheduler.py
Leichtgewichtiger Background-Scheduler für Auto-Tasks (Plan v3.2 §16).

Nutzt asyncio.create_task im Lifespan, ohne separaten Worker-Container.
- Begünstigten-Harvest: monatlich (erster Sonntag, 03:00 UTC)
- Sanktions-Refresh: täglich (04:00 UTC)
- State-Aid-Harvest (TAM): täglich (04:00 UTC, smart-Mode pro Source)
- Beneficiary-Auto-Harvest: täglich (Phase 6b — datengetriebene Pipeline,
  iteriert ueber ``BeneficiarySourceConfig`` und holt nur faellige Quellen).

Tasks sind idempotent: speichern Zeitstempel des letzten erfolgreichen
Laufs in der DB; bei jedem Tick (5-Min-Intervall) wird geprüft, ob fällig.
"""
from __future__ import annotations
import asyncio
import hashlib
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import desc

from database import SessionLocal
from config import WORKER_API_TOKEN
from models.automation import (
    HarvestRun, SanctionsRefreshRun,
)
from models.beneficiary_records import BeneficiaryRecord
from models.beneficiary_sources_config import BeneficiarySourceConfig
from models.state_aid import StateAidHarvestRun

log = logging.getLogger(__name__)

TICK_SECONDS = int(os.environ.get("SCHEDULER_TICK_SECONDS", "300"))  # 5 min
ENABLE_AUTO_HARVEST = os.environ.get("ENABLE_AUTO_HARVEST", "true").lower() == "true"
ENABLE_AUTO_SANCTIONS = os.environ.get("ENABLE_AUTO_SANCTIONS", "true").lower() == "true"

# Nightly-Batch-Window: ein gemeinsames Stundenfenster fuer alle Wartungs-
# Jobs (Sanctions-Refresh, State-Aid-Harvest, Access-Log-Pruning, Beneficiary-
# Harvest 1. Sonntag/Monat). Default 02:00 UTC = 04:00 CEST. Pro Job kann das
# einzeln ueberschrieben werden, sofern eine vom Default abweichende Stunde
# notwendig ist.
NIGHTLY_BATCH_HOUR = int(os.environ.get("NIGHTLY_BATCH_HOUR", "2"))

# Access-Log Pruning (DSGVO — kurze Aufbewahrung, default 30 Tage)
WORKSHOP_ACCESS_LOG_TTL_DAYS = int(os.environ.get("WORKSHOP_ACCESS_LOG_TTL_DAYS", "30"))
ACCESS_LOG_PRUNE_HOUR = int(os.environ.get("ACCESS_LOG_PRUNE_HOUR", str(NIGHTLY_BATCH_HOUR)))

# Sanctions-Refresh (taeglich)
SANCTIONS_REFRESH_HOUR = int(os.environ.get("SANCTIONS_REFRESH_HOUR", str(NIGHTLY_BATCH_HOUR)))

# Beneficiary-Auto-Harvest (1. Sonntag/Monat — alter Pfad)
BENEFICIARY_HARVEST_HOUR = int(os.environ.get("BENEFICIARY_HARVEST_HOUR", str(NIGHTLY_BATCH_HOUR)))

# Phase 6b: Datengetriebener Beneficiary-Harvest (taeglich, pro Quelle).
# Iteriert ``BeneficiarySourceConfig`` mit enabled=true UND faellig — Test
# anhand ``last_successful_harvest_at + update_frequency_days``.
ENABLE_BENEFICIARY_AUTO_HARVEST = (
    os.environ.get("ENABLE_BENEFICIARY_AUTO_HARVEST", "true").lower() == "true"
)
BENEFICIARY_AUTO_HARVEST_HOUR = int(
    os.environ.get("BENEFICIARY_AUTO_HARVEST_HOUR", str(NIGHTLY_BATCH_HOUR))
)
# Verzeichnis fuer das Audit-Backup der Original-Dateien (pro Quelle ein
# Unterordner). Standardmaessig im /app/data-Volume — bleibt persistent.
BENEFICIARY_RAW_DIR = Path(
    os.environ.get(
        "BENEFICIARY_RAW_DIR",
        str(Path(__file__).resolve().parent.parent / "data" / "beneficiaries" / "raw"),
    )
)
# HTTP-Timeout pro Quelle (Sekunden). Default 180 = 3 min — XLSX einiger
# Bundeslaender sind 5–10 MB gross.
BENEFICIARY_HTTP_TIMEOUT = int(os.environ.get("BENEFICIARY_HTTP_TIMEOUT", "180"))

# State-Aid-Auto-Harvest (Plan §11/§16)
STATE_AID_AUTO_HARVEST = os.environ.get("STATE_AID_AUTO_HARVEST", "true").lower() == "true"
# Komma-Liste: tam_de, tam_at, ...
STATE_AID_AUTO_HARVEST_SOURCES = [
    s.strip() for s in os.environ.get("STATE_AID_AUTO_HARVEST_SOURCES", "tam_de,tam_at").split(",")
    if s.strip()
]
STATE_AID_AUTO_HARVEST_HOUR = int(os.environ.get("STATE_AID_AUTO_HARVEST_HOUR", str(NIGHTLY_BATCH_HOUR)))
STATE_AID_AUTO_HARVEST_LIMIT = int(os.environ.get("STATE_AID_AUTO_HARVEST_LIMIT", "5000"))

# State-Aid-Validator: Self-Check, der ~30 Minuten nach dem Harvest-Slot laeuft.
# Default: NIGHTLY_BATCH_HOUR (gleicher Stunden-Slot, aber Tick prueft erst
# ab Minute 30 ob faellig). Damit ist der Validator-Lauf reproduzierbar
# nach dem Harvest abgeschlossen.
STATE_AID_VALIDATION_HOUR = int(
    os.environ.get("STATE_AID_VALIDATION_HOUR", str(NIGHTLY_BATCH_HOUR))
)
STATE_AID_VALIDATION_MINUTE = int(
    os.environ.get("STATE_AID_VALIDATION_MINUTE", "30")
)
ENABLE_STATE_AID_VALIDATION = (
    os.environ.get("ENABLE_STATE_AID_VALIDATION", "true").lower() == "true"
)

# Layer C: Nightly LLM-Batch ueber jueengste unsichere EntityMatches.
# Default: 1 h NACH dem State-Aid-Harvest, damit Harvest+Resolution durch sind.
ENABLE_ENTITY_MATCH_LLM_BATCH = (
    os.environ.get("ENABLE_ENTITY_MATCH_LLM_BATCH", "true").lower() == "true"
)
ENTITY_MATCH_LLM_BATCH_HOUR = int(
    os.environ.get(
        "ENTITY_MATCH_LLM_BATCH_HOUR",
        str(NIGHTLY_BATCH_HOUR + 1),
    )
)
ENTITY_MATCH_LLM_BATCH_MAX = int(
    os.environ.get("ENTITY_MATCH_LLM_BATCH_MAX", "500")
)
ENTITY_MATCH_LLM_BATCH_RECENT_HOURS = int(
    os.environ.get("ENTITY_MATCH_LLM_BATCH_RECENT_HOURS", "48")
)
ENTITY_MATCH_LLM_BATCH_TIMEOUT_S = float(
    os.environ.get("ENTITY_MATCH_LLM_BATCH_TIMEOUT_S", "30.0")
)

# Mapping source_key -> ISO-3 Country-Code (TAM erwartet ISO-3).
# Wird genutzt, wenn `StateAidSource.country_code` leer ist oder nicht der
# erwartete TAM-ISO-3 ist.
STATE_AID_SOURCE_COUNTRY_FALLBACK = {
    "tam_de": "DEU",
    "tam_at": "AUT",
}


# ─── Last-Run-Lookups ─────────────────────────────────────────────────────────

def _last_harvest_run() -> datetime | None:
    db = SessionLocal()
    try:
        row = (
            db.query(HarvestRun.started_at)
            .filter(HarvestRun.status.in_(("success", "partial")))
            .order_by(desc(HarvestRun.started_at))
            .first()
        )
        return row[0] if row else None
    finally:
        db.close()


def _last_sanctions_run() -> datetime | None:
    db = SessionLocal()
    try:
        row = (
            db.query(SanctionsRefreshRun.started_at)
            .filter(SanctionsRefreshRun.status == "success")
            .order_by(desc(SanctionsRefreshRun.started_at))
            .first()
        )
        return row[0] if row else None
    finally:
        db.close()


_LAST_ACCESS_LOG_PRUNE_AT: datetime | None = None
_LAST_VALIDATION_AT: datetime | None = None
_LAST_ENTITY_MATCH_LLM_RUN_AT: datetime | None = None


def _last_entity_match_llm_run() -> datetime | None:
    """Letzten Cron-Lauf des Entity-Match-LLM-Batchs."""
    from models.entity_match_llm_run import EntityMatchLlmRun
    db = SessionLocal()
    try:
        row = (
            db.query(EntityMatchLlmRun.started_at)
            .filter(EntityMatchLlmRun.triggered_by == "cron")
            .filter(EntityMatchLlmRun.status.in_(("ok", "partial")))
            .order_by(desc(EntityMatchLlmRun.started_at))
            .first()
        )
        return row[0] if row else None
    finally:
        db.close()


def _run_entity_match_llm_batch(triggered_by: str = "cron") -> dict:
    """Wrapper, der ``run_batch_verification`` mit den Cron-Defaults aufruft.

    Wird aus dem Scheduler-Tick ueber ``asyncio.to_thread`` aufgerufen, damit
    der Scheduler-Loop nicht blockiert.
    """
    from services.entity_match_llm_verifier import (
        BatchVerifyParams, run_batch_verification,
    )

    params = BatchVerifyParams(
        max_matches=ENTITY_MATCH_LLM_BATCH_MAX,
        score_min=75.0,
        score_max=89.0,
        only_recent_hours=ENTITY_MATCH_LLM_BATCH_RECENT_HOURS,
        only_unverified=True,
        per_call_timeout_s=ENTITY_MATCH_LLM_BATCH_TIMEOUT_S,
        overall_timeout_s=7200.0,  # 2 h Hard-Cap
        dry=False,
    )
    db = SessionLocal()
    try:
        result = run_batch_verification(
            db, params, triggered_by=triggered_by,
        )
        return result.to_dict()
    finally:
        db.close()


def prune_access_log(ttl_days: int | None = None) -> int:
    """Loescht Access-Log-Eintraege aelter als ``ttl_days`` Tage.

    Liefert die Anzahl der geloeschten Zeilen (best-effort — bei Fehler 0).
    Idempotent: kann ohne Schaden mehrfach pro Tag laufen.
    """
    from sqlalchemy import text
    days = int(ttl_days if ttl_days is not None else WORKSHOP_ACCESS_LOG_TTL_DAYS)
    if days <= 0:
        log.warning("prune_access_log: TTL=%d ungueltig — uebersprungen.", days)
        return 0

    db = SessionLocal()
    try:
        # PostgreSQL-spezifisches INTERVAL — passt zu unserer Backend-DB.
        result = db.execute(
            text(
                "DELETE FROM workshop_access_log "
                "WHERE created_at < (now() - (:d || ' days')::interval)"
            ),
            {"d": days},
        )
        deleted = int(result.rowcount or 0)
        db.commit()
        log.info("pruned %d access-log records older than %d days", deleted, days)
        return deleted
    except Exception:
        log.exception("prune_access_log fehlgeschlagen")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return 0
    finally:
        db.close()


def _last_state_aid_run() -> datetime | None:
    """Letzten cron-Lauf des State-Aid-Harvesters ueber alle Sources hinweg.

    Wir prueffen "ok" oder "partial" — ein partial-Run gilt als ausreichend,
    weil einzelne Sources fehlschlagen koennen, ohne dass der ganze Tages-Slot
    wiederholt werden muss.
    """
    db = SessionLocal()
    try:
        row = (
            db.query(StateAidHarvestRun.started_at)
            .filter(StateAidHarvestRun.triggered_by == "cron")
            .filter(StateAidHarvestRun.status.in_(("ok", "partial")))
            .order_by(desc(StateAidHarvestRun.started_at))
            .first()
        )
        return row[0] if row else None
    finally:
        db.close()


def _last_state_aid_any_run() -> datetime | None:
    """Letzter erfolgreicher State-Aid-Lauf egal welcher Trigger.

    Wird beim Auto-Resume nach Backend-Start verwendet — ob CLI, Cron oder
    Admin-Trigger ist egal, wir wollen wissen, wann zuletzt Daten reinkamen.
    """
    db = SessionLocal()
    try:
        row = (
            db.query(StateAidHarvestRun.started_at)
            .filter(StateAidHarvestRun.status.in_(("ok", "partial")))
            .order_by(desc(StateAidHarvestRun.started_at))
            .first()
        )
        return row[0] if row else None
    finally:
        db.close()


def _cleanup_zombie_state_aid_runs(max_age_minutes: int = 5) -> int:
    """Markiert alte 'running'-Eintraege als failed (z.B. nach Backend-Rebuild).

    Detached `docker exec`-Prozesse sterben beim Container-Restart, ihre
    Run-Eintraege bleiben aber auf 'running' stehen. Beim Lifespan-Start
    werden diese Zombies aufgeraeumt, damit das UI nicht ewig „läuft" zeigt.
    """
    from datetime import timedelta
    db = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(minutes=max_age_minutes)
        affected = (
            db.query(StateAidHarvestRun)
            .filter(StateAidHarvestRun.status == "running")
            .filter(StateAidHarvestRun.started_at < cutoff)
            .all()
        )
        for run in affected:
            run.status = "failed"
            run.finished_at = datetime.utcnow()
            run.error_message = (run.error_message or "") + (
                "\nzombie cleanup: backend restart vor Abschluss"
            ).strip()
        if affected:
            db.commit()
        return len(affected)
    finally:
        db.close()


def _is_first_sunday_window(now: datetime, hour: int | None = None) -> bool:
    """True, wenn now im Zeitfenster 'erster Sonntag des Monats, hour:00-hour:59 UTC'."""
    target_hour = BENEFICIARY_HARVEST_HOUR if hour is None else hour
    if now.weekday() != 6:  # Sonntag
        return False
    if now.day > 7:
        return False
    if now.hour != target_hour:
        return False
    return True


def _is_daily_window(now: datetime, hour: int = NIGHTLY_BATCH_HOUR) -> bool:
    return now.hour == hour


# ─── Sanktions-Refresh ────────────────────────────────────────────────────────

def run_sanctions_refresh(
    triggered_by: str = "cron",
    source_key: str | None = None,
) -> dict:
    """Fuehrt einen Sanktions-Refresh aus, schreibt Audit-Eintrag.

    Multi-Source: Wenn ``source_key`` None ist, werden alle aktivierten
    Sanctions-Quellen sequenziell refreshed (eu_fsf, un_sc, us_ofac_sdn,
    gb_hmt_sanctions, ch_seco). Der Subreport pro Quelle wird in
    `SanctionsRefreshRun.parameters` (JSON) abgelegt.

    Sync, weil das CSV-Lesen blockiert; aber pro Quelle schnell (<30s).
    """
    from services.sanctions_service import get_multi_service

    db = SessionLocal()
    started = datetime.utcnow()
    svc = get_multi_service()

    # Pro-Source-Stats vor dem Refresh fuer das Subreport sammeln
    pre_stats: dict[str, dict] = {}
    for source in svc.sources:
        if source_key and source.key != source_key:
            continue
        idx = svc.get_index(source.key)
        s = idx.stats() if idx else {}
        pre_stats[source.key] = {
            "rows_before": int(s.get("total_entries") or 0),
            "persons_before": int(s.get("persons") or 0),
            "organizations_before": int(s.get("organizations") or 0),
            "sha256_old": "",
        }
        try:
            if Path(source.csv_path).exists():
                pre_stats[source.key]["sha256_old"] = hashlib.sha256(
                    Path(source.csv_path).read_bytes()
                ).hexdigest()
        except Exception:  # noqa: BLE001
            pass

    # Phase 6c: Audit-Run vorab anlegen (status='running'), damit jeder
    # SanctionsEntry-Upsert die FK auf diesen Lauf bekommt. Anschliessend
    # wird der Run mit den finalen Stats aktualisiert.
    run = SanctionsRefreshRun(
        started_at=started,
        triggered_by=triggered_by,
        status="running",
        sources=source_key,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    refresh_run_id = run.id

    try:
        if source_key:
            single = svc.refresh_source(source_key, refresh_run_id=refresh_run_id)
            per_source_results = [single]
            agg_status = single.get("status", "failed")
            sources_ok = 1 if agg_status == "success" else 0
            sources_failed = 0 if agg_status == "success" else 1
        else:
            agg = svc.refresh_all(refresh_run_id=refresh_run_id)
            per_source_results = agg.get("per_source") or []
            agg_status = agg.get("status", "failed")
            sources_ok = int(agg.get("sources_ok") or 0)
            sources_failed = int(agg.get("sources_failed") or 0)

        # Subreport pro Source: rows_before, rows_after, sha256, status
        subreport: list[dict] = []
        rows_before_total = 0
        rows_after_total = 0
        persons_before_total = 0
        persons_after_total = 0
        orgs_before_total = 0
        orgs_after_total = 0
        size_total = 0

        for r in per_source_results:
            sk = r.get("source_key", "")
            pre = pre_stats.get(sk, {})
            stats_after = r.get("stats") or {}
            csv_path = ""
            sha_new = ""
            size_bytes = 0
            source_obj = next((s for s in svc.sources if s.key == sk), None)
            if source_obj:
                csv_path = source_obj.csv_path
                if Path(csv_path).exists():
                    try:
                        content = Path(csv_path).read_bytes()
                        sha_new = hashlib.sha256(content).hexdigest()
                        size_bytes = len(content)
                    except Exception:  # noqa: BLE001
                        pass

            entry = {
                "source_key": sk,
                "status": r.get("status"),
                "rows_before": int(pre.get("rows_before") or 0),
                "rows_after": int(stats_after.get("total_entries") or 0),
                "persons_before": int(pre.get("persons_before") or 0),
                "persons_after": int(stats_after.get("persons") or 0),
                "organizations_before": int(pre.get("organizations_before") or 0),
                "organizations_after": int(stats_after.get("organizations") or 0),
                "sha256_old": pre.get("sha256_old") or "",
                "sha256_new": sha_new,
                "file_size_bytes": size_bytes,
                "csv_path": csv_path,
                "error": r.get("error"),
            }
            subreport.append(entry)
            rows_before_total += entry["rows_before"]
            rows_after_total += entry["rows_after"]
            persons_before_total += entry["persons_before"]
            persons_after_total += entry["persons_after"]
            orgs_before_total += entry["organizations_before"]
            orgs_after_total += entry["organizations_after"]
            size_total += size_bytes

        # Run mit den finalen Stats aktualisieren (vorab als 'running' angelegt).
        run.finished_at = datetime.utcnow()
        run.status = "success" if agg_status == "success" else (
            "partial" if agg_status == "partial" else "failed"
        )
        run.source_url = ", ".join(
            s.download_url for s in svc.sources
            if (source_key is None or s.key == source_key)
        )
        run.file_size_bytes = size_total
        run.sha256_old = ""  # Aggregat — pro Source im Subreport
        run.sha256_new = ""
        run.rows_before = rows_before_total
        run.rows_after = rows_after_total
        run.persons_before = persons_before_total
        run.persons_after = persons_after_total
        run.organizations_before = orgs_before_total
        run.organizations_after = orgs_after_total
        run.sources = ",".join(
            e["source_key"] for e in subreport if e.get("source_key")
        )
        run.parameters = {
            "per_source": subreport,
            "sources_ok": sources_ok,
            "sources_failed": sources_failed,
            "single_source": source_key,
            "refresh_run_id": refresh_run_id,
        }
        db.commit()
        log.info(
            "Sanctions-Refresh %s (%s): %d → %d Eintraege ueber %d Quellen "
            "(ok=%d, failed=%d)",
            agg_status, triggered_by,
            rows_before_total, rows_after_total,
            len(subreport), sources_ok, sources_failed,
        )
        return {
            "status": agg_status,
            "rows_after": rows_after_total,
            "sources_ok": sources_ok,
            "sources_failed": sources_failed,
            "per_source": subreport,
        }
    except Exception as e:
        log.exception("Sanctions-Refresh fehlgeschlagen")
        # Den vorab angelegten Run auf 'failed' setzen, falls er noch
        # existiert; sonst neuen Eintrag schreiben (defensiv).
        try:
            run.finished_at = datetime.utcnow()
            run.status = "failed"
            run.error = str(e)[:2000]
            db.commit()
        except Exception:
            db.rollback()
            db.add(SanctionsRefreshRun(
                started_at=started,
                finished_at=datetime.utcnow(),
                triggered_by=triggered_by,
                status="failed",
                error=str(e)[:2000],
                sources=source_key,
            ))
            db.commit()
        return {"status": "failed", "error": str(e)}
    finally:
        db.close()


# ─── Begünstigten-Harvest ─────────────────────────────────────────────────────

def run_beneficiary_harvest(triggered_by: str = "cron") -> dict:
    """Führt das harvest_transparenzlisten.py-Skript als Subprozess aus
    und protokolliert das Resultat.
    Idempotent — bestehende Quellen werden überschrieben.
    """
    import subprocess

    db = SessionLocal()
    run = HarvestRun(triggered_by=triggered_by, status="running")
    db.add(run)
    db.commit()
    db.refresh(run)
    run_id = run.id
    started = run.started_at

    try:
        # Subprozess: das bestehende Harvest-Skript ausführen
        script = Path(__file__).resolve().parent.parent / "scripts" / "harvest_transparenzlisten.py"
        result = subprocess.run(
            ["python", str(script)],
            capture_output=True, text=True, timeout=1200,
            env={**os.environ, "BACKEND_BASE": "http://localhost:8000", "WORKER_API_TOKEN": WORKER_API_TOKEN},
        )
        log_excerpt = (result.stdout or "")[-4000:] + ("\n[STDERR]\n" + (result.stderr or ""))[-2000:]
        success = result.returncode == 0
        status = "success" if success else "partial"

        run = db.query(HarvestRun).filter(HarvestRun.id == run_id).first()
        run.finished_at = datetime.utcnow()
        run.status = status
        run.log_excerpt = log_excerpt
        # Versuche Counts aus Output zu extrahieren (best-effort)
        for line in (result.stdout or "").splitlines():
            if line.startswith("Quellen ok:"):
                try:
                    run.sources_ok = int(line.split(":")[1].strip())
                except Exception:
                    pass
            elif line.startswith("Quellen fehler:"):
                try:
                    run.sources_failed = int(line.split(":")[1].strip())
                except Exception:
                    pass
            elif line.startswith("Quellen total:"):
                try:
                    run.sources_total = int(line.split(":")[1].strip())
                except Exception:
                    pass
        db.commit()
        log.info("Harvest-Run %s ok=%s status=%s", run_id, success, status)
        return {"status": status, "run_id": run_id, "started_at": started.isoformat()}
    except subprocess.TimeoutExpired:
        run = db.query(HarvestRun).filter(HarvestRun.id == run_id).first()
        run.finished_at = datetime.utcnow()
        run.status = "failed"
        run.errors = {"timeout": "20 min Timeout überschritten"}
        db.commit()
        return {"status": "failed", "error": "timeout"}
    except Exception as e:
        log.exception("Harvest-Run fehlgeschlagen")
        run = db.query(HarvestRun).filter(HarvestRun.id == run_id).first()
        run.finished_at = datetime.utcnow()
        run.status = "failed"
        run.errors = {"exception": str(e)[:1000]}
        db.commit()
        return {"status": "failed", "error": str(e)}
    finally:
        db.close()


# ─── State-Aid-Auto-Harvest (Plan §11/§16) ───────────────────────────────────

def _resolve_state_aid_country(source_key: str) -> str | None:
    """source_key -> ISO-3 Country-Code fuer TAM-Submit.

    Versucht zuerst den DB-Eintrag (StateAidSource.country_code) zu lesen,
    sonst Fallback ueber das statische Mapping.
    """
    from models.state_aid import StateAidSource

    db = SessionLocal()
    try:
        src = (
            db.query(StateAidSource)
            .filter(StateAidSource.source_key == source_key)
            .first()
        )
        if src and src.country_code:
            cc = (src.country_code or "").upper()
            if len(cc) == 3:
                return cc
            # ISO-2 -> ISO-3 (fallback)
            from services.state_aid_service import ISO3_TO_ISO2
            iso2_to_iso3 = {iso2: iso3 for iso3, iso2 in ISO3_TO_ISO2.items()}
            if cc in iso2_to_iso3:
                return iso2_to_iso3[cc]
    except Exception:
        log.exception("State-Aid Country-Resolve fuer %s fehlgeschlagen", source_key)
    finally:
        db.close()

    return STATE_AID_SOURCE_COUNTRY_FALLBACK.get(source_key)


def run_state_aid_auto_harvest(triggered_by: str = "cron") -> dict:
    """Fuehrt den TAM-Smart-Harvest pro konfigurierter Source aus.

    Pro Source ein eigener ``run_harvest``-Aufruf mit ``mode="smart"`` und
    ``limit=STATE_AID_AUTO_HARVEST_LIMIT``. Smart-Mode nutzt automatisch das
    ``last_successful_harvest_at`` der Source als Auto-Since (mit 14 Tagen
    Lookback).

    Fehler pro Source werden geloggt + als Notification an Admins gepusht,
    aber die anderen Sources werden weiter abgearbeitet.
    """
    from services.state_aid_harvester import HarvestParams, run_harvest

    summary: dict = {
        "status": "running",
        "started_at": datetime.utcnow().isoformat(),
        "triggered_by": triggered_by,
        "sources": [],
    }
    sources_ok = 0
    sources_failed = 0

    for source_key in STATE_AID_AUTO_HARVEST_SOURCES:
        country_iso3 = _resolve_state_aid_country(source_key)
        if not country_iso3:
            log.warning(
                "State-Aid Auto-Harvest: source=%s — kein Country-Code aufloesbar, ueberspringe.",
                source_key,
            )
            sources_failed += 1
            summary["sources"].append({
                "source_key": source_key,
                "status": "skipped",
                "error": "country_code unbekannt",
            })
            continue

        params = HarvestParams(
            country_iso3=country_iso3,
            limit=STATE_AID_AUTO_HARVEST_LIMIT,
            page_size=100,
            triggered_by=triggered_by,
            source_key=source_key,
            mode="smart",
        )
        log.info(
            "State-Aid Auto-Harvest: source=%s country=%s mode=smart limit=%d",
            source_key, country_iso3, STATE_AID_AUTO_HARVEST_LIMIT,
        )

        db = SessionLocal()
        try:
            try:
                result = run_harvest(db, params)
            except Exception as exc:  # noqa: BLE001
                log.exception(
                    "State-Aid Auto-Harvest: source=%s fehlgeschlagen", source_key,
                )
                sources_failed += 1
                summary["sources"].append({
                    "source_key": source_key,
                    "country_iso3": country_iso3,
                    "status": "failed",
                    "error": str(exc)[:500],
                })
                _notify_admins_state_aid_failed(source_key, str(exc)[:500])
                continue
        finally:
            db.close()

        log.info(
            "State-Aid Auto-Harvest %s: %s seen=%d inserted=%d skipped=%d failed=%d",
            source_key, result.status, result.records_seen,
            result.records_inserted, result.records_skipped, result.records_failed,
        )
        summary["sources"].append({
            "source_key": source_key,
            "country_iso3": country_iso3,
            "status": result.status,
            "run_id": result.run_id,
            "records_seen": result.records_seen,
            "records_inserted": result.records_inserted,
            "records_skipped": result.records_skipped,
            "records_failed": result.records_failed,
            "error": result.error,
        })
        if result.status in ("ok", "partial"):
            sources_ok += 1
        else:
            sources_failed += 1
            _notify_admins_state_aid_failed(source_key, result.error or "harvest failed")

    if sources_failed == 0:
        summary["status"] = "ok"
    elif sources_ok == 0:
        summary["status"] = "failed"
    else:
        summary["status"] = "partial"
    summary["finished_at"] = datetime.utcnow().isoformat()
    summary["sources_ok"] = sources_ok
    summary["sources_failed"] = sources_failed
    return summary


def run_state_aid_validation(triggered_by: str = "cron") -> dict:
    """Fuehrt den State-Aid-Validator (services.state_aid_validator) aus
    und persistiert den Report.

    Liefert ein Dict mit Status + Findings-Count fuer Logs/Tests.
    """
    from services.state_aid_validator import (
        persist_report,
        run_validation,
    )

    db = SessionLocal()
    try:
        report = run_validation(db)
        try:
            run_id = persist_report(db, report, module="state_aid")
        except Exception:  # noqa: BLE001
            log.exception("Validator-Persistierung (cron=%s) fehlgeschlagen", triggered_by)
            run_id = None
        log.info(
            "State-Aid-Validator (%s): status=%s findings=%d "
            "passed=%d warned=%d failed=%d",
            triggered_by, report.status, len(report.findings),
            report.checks_passed, report.checks_warned, report.checks_failed,
        )
        return {
            "status": report.status,
            "run_id": run_id,
            "findings_count": len(report.findings),
            "checks_total": report.checks_total,
            "checks_passed": report.checks_passed,
            "checks_warned": report.checks_warned,
            "checks_failed": report.checks_failed,
        }
    except Exception as exc:  # noqa: BLE001
        log.exception("State-Aid-Validator-Lauf (%s) fehlgeschlagen", triggered_by)
        return {"status": "failed", "error": str(exc)[:500]}
    finally:
        db.close()


def _notify_admins_state_aid_failed(source_key: str, error: str) -> None:
    """Pushed eine Notification an alle Admins (Bell-Icon)."""
    try:
        from routers.notifications import push_notification
        from models.registration import Registration

        db = SessionLocal()
        try:
            admins = db.query(Registration).filter(Registration.role == "admin").all()
            for adm in admins:
                push_notification(
                    user_id=adm.id,
                    kind="admin_harvest_failed",
                    title=f"State-Aid Auto-Harvest fehlgeschlagen: {source_key}",
                    body=error[:500],
                    link="/admin",
                )
        finally:
            db.close()
    except Exception:
        log.exception("State-Aid Admin-Notification fehlgeschlagen")


# ─── Phase 6b: Datengetriebener Beneficiary-Auto-Harvest ─────────────────────


def _is_source_due(cfg: BeneficiarySourceConfig, now: datetime) -> bool:
    """True, wenn die Quelle wieder geharvested werden soll.

    Regel:
      - enabled=false      -> niemals
      - source_type=manual -> niemals (kein Auto-Harvest fuer manuelle Uploads)
      - kein source_url    -> niemals
      - last_successful_harvest_at None -> ja (Erst-Harvest)
      - sonst: ``(now - last) >= update_frequency_days`` (Default 30 Tage,
        falls die Config keinen Wert hat).
    """
    if not cfg.enabled:
        return False
    if cfg.source_type not in ("xlsx_url", "csv_url"):
        return False
    if not cfg.source_url:
        return False
    if cfg.last_successful_harvest_at is None:
        return True
    freq_days = int(cfg.update_frequency_days or 30)
    delta = now - cfg.last_successful_harvest_at
    return delta >= timedelta(days=freq_days)


def _archive_raw_file(source_key: str, file_name: str, content: bytes) -> str | None:
    """Schreibt die Original-Datei nach ``BENEFICIARY_RAW_DIR/<source_key>/<ts>_<file>``.

    Liefert den absoluten Pfad oder None bei Fehler — Audit-Backup ist
    nice-to-have, ein Fehler hier darf den Harvest nicht abbrechen.
    """
    try:
        target_dir = BENEFICIARY_RAW_DIR / source_key
        target_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        # Dateinamen saeubern — nur safe-Zeichen, sonst ts.
        safe_name = "".join(
            c for c in (file_name or "data.xlsx")
            if c.isalnum() or c in "._-"
        ) or "data.xlsx"
        path = target_dir / f"{ts}_{safe_name}"
        path.write_bytes(content)
        return str(path)
    except Exception:  # noqa: BLE001
        log.exception("Audit-Archivierung fuer %s fehlgeschlagen", source_key)
        return None


def _harvest_one_beneficiary_source(
    cfg: BeneficiarySourceConfig,
    triggered_by: str,
) -> dict:
    """Worker-Schritt fuer EINE Quelle: download, sha-skip, harvest, archive.

    Liefert ein Dict-Result mit Status + Counters fuer das Summary. Schreibt
    die Status-Felder (last_successful_harvest_at, last_seen_sha256,
    record_count, quality) zurueck in die Config.
    """
    from services.beneficiary_harvester import (
        BeneficiaryHarvestParams, run_beneficiary_harvest,
    )

    source_key = cfg.source_key
    log.info(
        "Beneficiary-Auto-Harvest: source=%s url=%s freq=%sd",
        source_key, cfg.source_url, cfg.update_frequency_days,
    )

    # 1. Download
    try:
        import httpx
        with httpx.Client(timeout=BENEFICIARY_HTTP_TIMEOUT, follow_redirects=True) as client:
            r = client.get(cfg.source_url)
            r.raise_for_status()
            file_content = r.content
    except Exception as exc:  # noqa: BLE001
        log.warning("Beneficiary-Auto-Harvest %s: Download fehlgeschlagen: %s", source_key, exc)
        return {
            "source_key": source_key,
            "status": "failed",
            "error": f"download_failed: {exc}",
        }

    if not file_content:
        return {
            "source_key": source_key,
            "status": "failed",
            "error": "empty_response",
        }

    # 2. SHA-Skip — wenn die Datei bit-identisch zur letzten ist, kein Harvest noetig.
    sha256_new = hashlib.sha256(file_content).hexdigest()
    if cfg.last_seen_sha256 and cfg.last_seen_sha256 == sha256_new:
        log.info(
            "Beneficiary-Auto-Harvest %s: Datei unveraendert (sha256 match) — skip.",
            source_key,
        )
        # last_successful_harvest_at trotzdem aktualisieren — sonst laeuft
        # die Quelle morgen wieder ins Auto-Window.
        db = SessionLocal()
        try:
            cfg_db = (
                db.query(BeneficiarySourceConfig)
                .filter(BeneficiarySourceConfig.source_key == source_key)
                .first()
            )
            if cfg_db:
                cfg_db.last_successful_harvest_at = datetime.utcnow()
                db.commit()
        finally:
            db.close()
        return {
            "source_key": source_key,
            "status": "unchanged",
            "sha256": sha256_new,
            "records_inserted": 0,
            "records_skipped": 0,
        }

    # 3. Audit-Archive (best-effort).
    file_name = (cfg.source_url.rsplit("/", 1)[-1] if cfg.source_url else "") or f"{source_key}.xlsx"
    archive_path = _archive_raw_file(source_key, file_name, file_content)

    # 4. Validierter Snapshot-Harvest: entfallene Vorhaben der Quelle werden
    # entfernt, statt bei jeder Veröffentlichung historischen Ballast zu sammeln.
    db = SessionLocal()
    try:
        params = BeneficiaryHarvestParams(
            source_key=source_key,
            bundesland=cfg.bundesland,
            fonds=cfg.fonds,
            periode=cfg.periode,
            country_code=cfg.country_code,
            file_content=file_content,
            file_name=file_name,
            field_mapping=cfg.field_mapping,
            sheet_name=cfg.sheet_name,
            header_row=int(cfg.header_row or 0),
            mode="snapshot",
            triggered_by=triggered_by,
        )
        try:
            result = run_beneficiary_harvest(db, params)
        except Exception as exc:  # noqa: BLE001
            log.exception("Beneficiary-Auto-Harvest %s: Harvest-Fehler", source_key)
            return {
                "source_key": source_key,
                "status": "failed",
                "error": f"harvest_failed: {exc}",
                "archive_path": archive_path,
            }

        # Die Kartenansicht verwendet noch die materialisierte DataFrame-Tabelle.
        # Sie erhält dieselben validierten Originalbytes wie die zentrale Tabelle,
        # damit Auto-Harvest, Karte und Analytics denselben Stand zeigen.
        if result.get("status") in ("ok", "partial"):
            from services.dataframe_service import ingest_dataframe
            try:
                ingest_dataframe(
                    file_content, file_name, source_key,
                    cfg.sheet_name if cfg.sheet_name is not None else 0,
                    dataset_group="beneficiary",
                )
                from routers.beneficiaries import invalidate_map_cache
                invalidate_map_cache()
            except Exception as exc:  # zentraler Snapshot bleibt intakt
                log.exception("Beneficiary-Auto-Harvest %s: Kartenmaterialisierung fehlgeschlagen", source_key)
                result["status"] = "partial"
                result["materialization_error"] = str(exc)

        # 5. Status der Config aktualisieren.
        cfg_db = (
            db.query(BeneficiarySourceConfig)
            .filter(BeneficiarySourceConfig.source_key == source_key)
            .first()
        )
        if cfg_db:
            cfg_db.last_seen_sha256 = sha256_new
            cfg_db.last_harvest_run_id = result.get("run_id")
            if result.get("status") in ("ok", "partial"):
                cfg_db.last_successful_harvest_at = datetime.utcnow()
            cfg_db.record_count = (
                db.query(BeneficiaryRecord)
                .filter(BeneficiaryRecord.source_key == source_key)
                .count()
            )
            if result.get("status") == "ok":
                cfg_db.quality = "green"
            elif result.get("status") == "partial":
                cfg_db.quality = "yellow"
            else:
                cfg_db.quality = "red"
            db.commit()
    finally:
        db.close()

    result["archive_path"] = archive_path
    result["sha256"] = sha256_new
    return result


def run_beneficiary_auto_harvest(triggered_by: str = "cron") -> dict:
    """Iteriert alle ``BeneficiarySourceConfig`` mit enabled=true UND faellig.

    Pro Quelle:
      1. download(source_url) -> bytes
      2. sha256(bytes) vergleichen mit ``last_seen_sha256``: gleich -> skip
      3. ``run_beneficiary_harvest`` im smart-Modus
      4. Original-Bytes nach ``BENEFICIARY_RAW_DIR/<source_key>/<ts>_<file>``
         archivieren (Audit-Backup)
      5. ``last_seen_sha256``, ``last_successful_harvest_at``,
         ``record_count``, ``quality`` aktualisieren

    Liefert ein Summary-Dict mit Per-Source-Status — fuer Logs und Tests.
    Idempotent: laeuft eine fehlerfreie Quelle ein zweites Mal an, greift
    der SHA-Skip und es passiert nichts.
    """
    summary: dict = {
        "status": "running",
        "started_at": datetime.utcnow().isoformat(),
        "triggered_by": triggered_by,
        "sources": [],
    }
    sources_ok = 0
    sources_failed = 0
    sources_unchanged = 0
    sources_skipped_not_due = 0

    db = SessionLocal()
    try:
        rows = (
            db.query(BeneficiarySourceConfig)
            .filter(BeneficiarySourceConfig.enabled.is_(True))
            .order_by(BeneficiarySourceConfig.source_key.asc())
            .all()
        )
        # Snapshot aufnehmen (Source-Keys), dann Session schliessen — die
        # Worker-Funktion oeffnet eigene Sessions, das vermeidet langlaufende
        # Locks auf der Config-Tabelle.
        candidates: list[BeneficiarySourceConfig] = list(rows)
    finally:
        db.close()

    now = datetime.utcnow()
    for cfg in candidates:
        if not _is_source_due(cfg, now):
            sources_skipped_not_due += 1
            continue

        try:
            result = _harvest_one_beneficiary_source(cfg, triggered_by=triggered_by)
        except Exception as exc:  # noqa: BLE001
            log.exception(
                "Beneficiary-Auto-Harvest %s: Worker-Fehler", cfg.source_key,
            )
            sources_failed += 1
            summary["sources"].append({
                "source_key": cfg.source_key,
                "status": "failed",
                "error": f"worker_exception: {exc}",
            })
            continue

        summary["sources"].append(result)
        status = result.get("status")
        if status == "unchanged":
            sources_unchanged += 1
        elif status in ("ok", "partial"):
            sources_ok += 1
        else:
            sources_failed += 1

    if sources_failed == 0:
        summary["status"] = "ok"
    elif sources_ok + sources_unchanged == 0:
        summary["status"] = "failed"
    else:
        summary["status"] = "partial"
    summary["finished_at"] = datetime.utcnow().isoformat()
    summary["sources_ok"] = sources_ok
    summary["sources_unchanged"] = sources_unchanged
    summary["sources_failed"] = sources_failed
    summary["sources_skipped_not_due"] = sources_skipped_not_due
    log.info(
        "Beneficiary-Auto-Harvest %s: ok=%d unchanged=%d failed=%d not_due=%d",
        summary["status"], sources_ok, sources_unchanged, sources_failed,
        sources_skipped_not_due,
    )
    return summary


# Guard fuer die _scheduler_tick — verhindert, dass derselbe Lauf in einer
# Stunde zweimal startet, falls TICK_SECONDS kleiner als 1h ist.
_LAST_BENEFICIARY_AUTO_HARVEST_AT: datetime | None = None


# ─── Scheduler-Loop ───────────────────────────────────────────────────────────

async def _scheduler_tick():
    """Wird alle TICK_SECONDS aufgerufen."""
    now = datetime.utcnow()

    if ENABLE_AUTO_SANCTIONS and _is_daily_window(now, hour=SANCTIONS_REFRESH_HOUR):
        last = _last_sanctions_run()
        if last is None or (now - last).total_seconds() > 23 * 3600:
            log.info("Scheduler: Sanctions-Refresh fällig → starte (cron)")
            try:
                run_sanctions_refresh(triggered_by="cron")
            except Exception:
                log.exception("Sanctions-Refresh-Fehler")

    if ENABLE_AUTO_HARVEST and _is_first_sunday_window(now):
        last = _last_harvest_run()
        if last is None or (now - last).total_seconds() > 6 * 24 * 3600:
            log.info("Scheduler: Begünstigten-Harvest fällig → starte (cron)")
            try:
                # Im Hintergrund ausführen, blockt sonst den Tick
                await asyncio.to_thread(run_beneficiary_harvest, "cron")
            except Exception:
                log.exception("Harvest-Fehler")

    # Phase 6b: Datengetriebener Beneficiary-Auto-Harvest (taeglich).
    # Iteriert die BeneficiarySourceConfig-Tabelle. Pro Tag ein Lauf —
    # Guard ueber _LAST_BENEFICIARY_AUTO_HARVEST_AT, sonst startet das
    # bei TICK_SECONDS=300 alle 5 min im Stundenfenster.
    if (
        ENABLE_BENEFICIARY_AUTO_HARVEST
        and _is_daily_window(now, hour=BENEFICIARY_AUTO_HARVEST_HOUR)
    ):
        global _LAST_BENEFICIARY_AUTO_HARVEST_AT
        last_b = _LAST_BENEFICIARY_AUTO_HARVEST_AT
        if last_b is None or (now - last_b).total_seconds() > 22 * 3600:
            log.info(
                "Scheduler: Beneficiary-Auto-Harvest faellig → starte "
                "(cron, %02d UTC)", BENEFICIARY_AUTO_HARVEST_HOUR,
            )
            try:
                _LAST_BENEFICIARY_AUTO_HARVEST_AT = now
                await asyncio.to_thread(run_beneficiary_auto_harvest, "cron")
            except Exception:
                log.exception("Beneficiary-Auto-Harvest-Fehler")

    # Access-Log: taeglich pruning (Default 03:00 UTC)
    if _is_daily_window(now, hour=ACCESS_LOG_PRUNE_HOUR):
        global _LAST_ACCESS_LOG_PRUNE_AT
        last = _LAST_ACCESS_LOG_PRUNE_AT
        if last is None or (now - last).total_seconds() > 22 * 3600:
            log.info(
                "Scheduler: Access-Log-Pruning faellig "
                "(TTL=%d Tage) → starte (cron)",
                WORKSHOP_ACCESS_LOG_TTL_DAYS,
            )
            try:
                await asyncio.to_thread(prune_access_log, WORKSHOP_ACCESS_LOG_TTL_DAYS)
                _LAST_ACCESS_LOG_PRUNE_AT = now
            except Exception:
                log.exception("Access-Log-Pruning-Fehler")

    if (
        STATE_AID_AUTO_HARVEST
        and STATE_AID_AUTO_HARVEST_SOURCES
        and _is_daily_window(now, hour=STATE_AID_AUTO_HARVEST_HOUR)
    ):
        last = _last_state_aid_run()
        if last is None or (now - last).total_seconds() > 22 * 3600:
            log.info(
                "Scheduler: State-Aid Auto-Harvest fällig → starte (cron, sources=%s)",
                ",".join(STATE_AID_AUTO_HARVEST_SOURCES),
            )
            try:
                # Smart-Mode pro Source — kann je nach Volumen mehrere Minuten dauern,
                # daher in einen Worker-Thread auslagern, damit der Tick nicht blockiert.
                await asyncio.to_thread(run_state_aid_auto_harvest, "cron")
            except Exception:
                log.exception("State-Aid Auto-Harvest-Fehler")

    # State-Aid-Validator: laeuft im Validation-Stundenfenster ab Minute 30,
    # damit der Harvest typischerweise schon durch ist. Guarded durch
    # _LAST_VALIDATION_AT, damit pro Stunde nur ein Lauf passiert.
    if (
        ENABLE_STATE_AID_VALIDATION
        and now.hour == STATE_AID_VALIDATION_HOUR
        and now.minute >= STATE_AID_VALIDATION_MINUTE
    ):
        global _LAST_VALIDATION_AT
        last_v = _LAST_VALIDATION_AT
        if last_v is None or (now - last_v).total_seconds() > 22 * 3600:
            log.info(
                "Scheduler: State-Aid-Validator faellig → starte "
                "(cron, %02d:%02d UTC)",
                STATE_AID_VALIDATION_HOUR, STATE_AID_VALIDATION_MINUTE,
            )
            try:
                _LAST_VALIDATION_AT = now
                await asyncio.to_thread(run_state_aid_validation, "cron")
            except Exception:
                log.exception("State-Aid-Validator-Fehler")

    # Layer C: Naechtlicher Entity-Match-LLM-Batch (~03:00 UTC nach Default —
    # 1 h nach State-Aid-Harvest). Pro Lauf bis zu 500 Matches der letzten
    # 48 h. Maximal ein Lauf pro Tag, geguarded durch DB + In-Memory.
    if (
        ENABLE_ENTITY_MATCH_LLM_BATCH
        and _is_daily_window(now, hour=ENTITY_MATCH_LLM_BATCH_HOUR)
    ):
        global _LAST_ENTITY_MATCH_LLM_RUN_AT
        last_e = _last_entity_match_llm_run()
        last_mem = _LAST_ENTITY_MATCH_LLM_RUN_AT
        eligible_db = (
            last_e is None or (now - last_e).total_seconds() > 22 * 3600
        )
        eligible_mem = (
            last_mem is None or (now - last_mem).total_seconds() > 22 * 3600
        )
        if eligible_db and eligible_mem:
            log.info(
                "Scheduler: Entity-Match-LLM-Batch faellig → starte "
                "(cron, %02d UTC, max=%d, recent_hours=%d)",
                ENTITY_MATCH_LLM_BATCH_HOUR,
                ENTITY_MATCH_LLM_BATCH_MAX,
                ENTITY_MATCH_LLM_BATCH_RECENT_HOURS,
            )
            try:
                _LAST_ENTITY_MATCH_LLM_RUN_AT = now
                await asyncio.to_thread(_run_entity_match_llm_batch, "cron")
            except Exception:
                log.exception("Entity-Match-LLM-Batch-Fehler")


STATE_AID_AUTO_RESUME = os.environ.get("STATE_AID_AUTO_RESUME", "true").lower() == "true"
STATE_AID_RESUME_AFTER_HOURS = int(os.environ.get("STATE_AID_RESUME_AFTER_HOURS", "6"))


async def _state_aid_startup_resume() -> None:
    """Nach Backend-Start: Zombies aufraeumen + Auto-Harvest, falls noetig.

    Wichtig fuer die Workshop-Demo: nach jedem Rebuild laeuft der Voll-Harvest
    automatisch weiter (smart-mode → idempotent, alte Records werden
    uebersprungen). Sonst muesste der Pruefer den Harvest manuell anstossen
    oder bis zum naechsten Tages-Slot warten.
    """
    if not STATE_AID_AUTO_RESUME:
        return
    if not (STATE_AID_AUTO_HARVEST and STATE_AID_AUTO_HARVEST_SOURCES):
        return
    try:
        cleaned = _cleanup_zombie_state_aid_runs()
        if cleaned:
            log.info("State-Aid Zombie-Cleanup: %d 'running'-Eintraege abgeschlossen.", cleaned)

        last = _last_state_aid_any_run()
        if last is None:
            log.info("State-Aid Auto-Resume: noch nie ein erfolgreicher Lauf — starte (startup)")
        else:
            age_h = (datetime.utcnow() - last).total_seconds() / 3600
            if age_h < STATE_AID_RESUME_AFTER_HOURS:
                log.info(
                    "State-Aid Auto-Resume: letzter Lauf vor %.1f h — kein Resume noetig.",
                    age_h,
                )
                return
            log.info(
                "State-Aid Auto-Resume: letzter Lauf vor %.1f h (>= %d h) — starte (startup, sources=%s)",
                age_h, STATE_AID_RESUME_AFTER_HOURS,
                ",".join(STATE_AID_AUTO_HARVEST_SOURCES),
            )
        # Im Worker-Thread, damit der Scheduler-Loop nicht blockiert
        await asyncio.to_thread(run_state_aid_auto_harvest, "startup")
    except Exception:
        log.exception("State-Aid Auto-Resume-Fehler")


async def scheduler_loop():
    log.info(
        "Scheduler gestartet · Tick %ds · NightlyBatchHour=%02d UTC",
        TICK_SECONDS, NIGHTLY_BATCH_HOUR,
    )
    log.info(
        "  Sanctions-Refresh: %s @%02d UTC (taeglich)",
        "ON" if ENABLE_AUTO_SANCTIONS else "OFF", SANCTIONS_REFRESH_HOUR,
    )
    log.info(
        "  Beneficiary-Harvest: %s @%02d UTC (1. Sonntag/Monat)",
        "ON" if ENABLE_AUTO_HARVEST else "OFF", BENEFICIARY_HARVEST_HOUR,
    )
    log.info(
        "  Beneficiary-Auto-Harvest (Phase 6b, datengetrieben): %s @%02d UTC (taeglich)",
        "ON" if ENABLE_BENEFICIARY_AUTO_HARVEST else "OFF",
        BENEFICIARY_AUTO_HARVEST_HOUR,
    )
    log.info(
        "  State-Aid-Harvest: %s @%02d UTC (taeglich, smart, sources=%s)",
        "ON" if STATE_AID_AUTO_HARVEST else "OFF",
        STATE_AID_AUTO_HARVEST_HOUR,
        ",".join(STATE_AID_AUTO_HARVEST_SOURCES) or "—",
    )
    log.info(
        "  Access-Log-Pruning: TTL=%dd @%02d UTC (taeglich)",
        WORKSHOP_ACCESS_LOG_TTL_DAYS, ACCESS_LOG_PRUNE_HOUR,
    )
    log.info(
        "  State-Aid Auto-Resume nach Restart: %s (Schwelle %dh)",
        "ON" if STATE_AID_AUTO_RESUME else "OFF",
        STATE_AID_RESUME_AFTER_HOURS,
    )
    log.info(
        "  State-Aid-Validator: %s @%02d:%02d UTC (taeglich)",
        "ON" if ENABLE_STATE_AID_VALIDATION else "OFF",
        STATE_AID_VALIDATION_HOUR, STATE_AID_VALIDATION_MINUTE,
    )
    log.info(
        "  Entity-Match-LLM-Batch (Layer C): %s @%02d UTC max=%d recent=%dh "
        "timeout=%.0fs (taeglich)",
        "ON" if ENABLE_ENTITY_MATCH_LLM_BATCH else "OFF",
        ENTITY_MATCH_LLM_BATCH_HOUR,
        ENTITY_MATCH_LLM_BATCH_MAX,
        ENTITY_MATCH_LLM_BATCH_RECENT_HOURS,
        ENTITY_MATCH_LLM_BATCH_TIMEOUT_S,
    )
    # Auto-Resume parallel zum Tick-Loop, blockiert nicht.
    asyncio.create_task(_state_aid_startup_resume())
    while True:
        try:
            await _scheduler_tick()
        except Exception:
            log.exception("Scheduler-Tick-Fehler")
        await asyncio.sleep(TICK_SECONDS)
