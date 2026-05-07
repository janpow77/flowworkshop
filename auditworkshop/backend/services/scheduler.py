"""
flowworkshop · services/scheduler.py
Leichtgewichtiger Background-Scheduler für Auto-Tasks (Plan v3.2 §16).

Nutzt asyncio.create_task im Lifespan, ohne separaten Worker-Container.
- Begünstigten-Harvest: monatlich (erster Sonntag, 03:00 UTC)
- Sanktions-Refresh: täglich (04:00 UTC)

Tasks sind idempotent: speichern Zeitstempel des letzten erfolgreichen
Laufs in der DB; bei jedem Tick (5-Min-Intervall) wird geprüft, ob fällig.
"""
from __future__ import annotations
import asyncio
import hashlib
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import desc, func

from database import SessionLocal
from models.automation import (
    HarvestRun, HarvestSourceUpdate, SanctionsRefreshRun,
)

log = logging.getLogger(__name__)

TICK_SECONDS = int(os.environ.get("SCHEDULER_TICK_SECONDS", "300"))  # 5 min
ENABLE_AUTO_HARVEST = os.environ.get("ENABLE_AUTO_HARVEST", "true").lower() == "true"
ENABLE_AUTO_SANCTIONS = os.environ.get("ENABLE_AUTO_SANCTIONS", "true").lower() == "true"


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


def _is_first_sunday_window(now: datetime) -> bool:
    """True, wenn now im Zeitfenster 'erster Sonntag des Monats, 03:00-04:00 UTC'."""
    if now.weekday() != 6:  # Sonntag
        return False
    if now.day > 7:
        return False
    if now.hour != 3:
        return False
    return True


def _is_daily_window(now: datetime, hour: int = 4) -> bool:
    return now.hour == hour


# ─── Sanktions-Refresh ────────────────────────────────────────────────────────

def run_sanctions_refresh(triggered_by: str = "cron") -> dict:
    """Führt einen Sanktions-Refresh aus, schreibt Audit-Eintrag.
    Sync, weil das CSV-Lesen blockiert; aber schnell (<10s).
    """
    from services.sanctions_service import get_index, FSF_CSV_PATH

    db = SessionLocal()
    started = datetime.utcnow()
    sha_old = ""
    rows_before = 0
    persons_before = 0
    orgs_before = 0
    try:
        idx = get_index()
        stats_before = idx.stats()
        rows_before = stats_before.get("total_entries", 0)
        persons_before = stats_before.get("persons", 0)
        orgs_before = stats_before.get("organizations", 0)
        # Hash der bestehenden Datei
        if Path(FSF_CSV_PATH).exists():
            sha_old = hashlib.sha256(Path(FSF_CSV_PATH).read_bytes()).hexdigest()

        result = idx.refresh_from_source()
        sha_new = ""
        size = 0
        if Path(FSF_CSV_PATH).exists():
            content = Path(FSF_CSV_PATH).read_bytes()
            sha_new = hashlib.sha256(content).hexdigest()
            size = len(content)

        run = SanctionsRefreshRun(
            started_at=started,
            finished_at=datetime.utcnow(),
            triggered_by=triggered_by,
            status="success",
            source_url=stats_before.get("download_url"),
            file_size_bytes=size,
            sha256_old=sha_old,
            sha256_new=sha_new,
            rows_before=rows_before,
            rows_after=result.get("total_entries", 0),
            persons_before=persons_before,
            persons_after=result.get("persons", 0),
            organizations_before=orgs_before,
            organizations_after=result.get("organizations", 0),
        )
        db.add(run)
        db.commit()
        log.info(
            "Sanctions-Refresh ok (%s): %d → %d Einträge",
            triggered_by, rows_before, result.get("total_entries", 0),
        )
        return {"status": "success", "rows_after": result.get("total_entries", 0)}
    except Exception as e:
        log.exception("Sanctions-Refresh fehlgeschlagen")
        db.add(SanctionsRefreshRun(
            started_at=started,
            finished_at=datetime.utcnow(),
            triggered_by=triggered_by,
            status="failed",
            error=str(e)[:2000],
            rows_before=rows_before,
            persons_before=persons_before,
            organizations_before=orgs_before,
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
            env={**os.environ, "BACKEND_BASE": "http://localhost:8000"},
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
                try: run.sources_ok = int(line.split(":")[1].strip())
                except Exception: pass
            elif line.startswith("Quellen fehler:"):
                try: run.sources_failed = int(line.split(":")[1].strip())
                except Exception: pass
            elif line.startswith("Quellen total:"):
                try: run.sources_total = int(line.split(":")[1].strip())
                except Exception: pass
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


# ─── Scheduler-Loop ───────────────────────────────────────────────────────────

async def _scheduler_tick():
    """Wird alle TICK_SECONDS aufgerufen."""
    now = datetime.utcnow()

    if ENABLE_AUTO_SANCTIONS and _is_daily_window(now, hour=4):
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


async def scheduler_loop():
    log.info(
        "Scheduler gestartet (Tick %ds · auto_harvest=%s · auto_sanctions=%s)",
        TICK_SECONDS, ENABLE_AUTO_HARVEST, ENABLE_AUTO_SANCTIONS,
    )
    while True:
        try:
            await _scheduler_tick()
        except Exception:
            log.exception("Scheduler-Tick-Fehler")
        await asyncio.sleep(TICK_SECONDS)
