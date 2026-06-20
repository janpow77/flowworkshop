"""Router: Webseiten-Sicherheitsprüfung (KA 6 — ISMS-Systemprüfung).

Nicht-intrusiv. Scan nur nach server-seitig erzwungener Berechtigungs-
Selbstbestätigung (Checkbox, §2). Eingeloggte Prüfer (require_session).
"""
from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from config import SECURITY_SCAN_ENABLED, SECURITY_SCAN_RATE_PER_HOUR
from database import get_db
from models.security_scan import SecurityScanRun
from routers.auth import require_session
from services.security_scan import engine

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/security-scan", tags=["security-scan"])

# Rechtstext der Berechtigungs-Selbstbestätigung (wird im Audit-Log gespeichert).
AUTHORIZATION_TEXT = (
    "Ich bestätige, dass ich zur technischen Sicherheitsprüfung dieser Webseite "
    "berechtigt bin bzw. die ausdrückliche Einwilligung des Betreibers vorliegt. "
    "Mir ist bekannt, dass eine Prüfung ohne Berechtigung nach §§ 202a ff., 303a/b "
    "StGB strafbar sein kann. Die Prüfung ist nicht-intrusiv (keine aktiven "
    "Angriffe/Exploits)."
)

# einfaches In-Memory-Rate-Limit pro Nutzer (Stunde)
_rate: dict[str, list[float]] = defaultdict(list)


class ScanRequest(BaseModel):
    url: str = Field(..., min_length=3, max_length=2000)
    authorization_confirmed: bool = False


def _user_key(session: dict) -> str:
    return str(session.get("user_id") or session.get("email") or "unknown")[:80]


def _check_rate(user: str) -> None:
    now = time.monotonic()
    fresh = [t for t in _rate[user] if now - t < 3600]
    if len(fresh) >= SECURITY_SCAN_RATE_PER_HOUR:
        _rate[user] = fresh
        raise HTTPException(429, f"Rate-Limit erreicht ({SECURITY_SCAN_RATE_PER_HOUR} Scans/Stunde).")
    fresh.append(now)
    _rate[user] = fresh


def _status_payload(run: SecurityScanRun) -> dict:
    return {
        "scan_id": run.scan_id,
        "status": run.status,
        "url": run.target_url,
        "host": run.target_host,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "overall": run.overall,
        "counts": {
            "konform": run.count_konform, "gelb": run.count_gelb,
            "rot": run.count_rot, "grau": run.count_grau,
        },
        "has_screenshot": bool(run.screenshot_path),
        "has_architecture": bool(run.architecture_path),
        "error": run.error_message,
    }


@router.post("/scan")
def start_scan(
    body: ScanRequest,
    background_tasks: BackgroundTasks,
    session: dict = Depends(require_session),
    db: Session = Depends(get_db),
) -> dict:
    if not SECURITY_SCAN_ENABLED:
        raise HTTPException(503, "Die Sicherheitsprüfung ist deaktiviert.")
    if not body.authorization_confirmed:
        raise HTTPException(403, "Berechtigungsbestätigung erforderlich: Bitte die Berechtigungs-Checkbox bestätigen.")

    user = _user_key(session)
    _check_rate(user)
    norm, host, _ = engine.normalize_target(body.url)
    if not host:
        raise HTTPException(422, "Bitte eine gültige URL/Domäne angeben.")

    scan_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    run = SecurityScanRun(
        scan_id=scan_id,
        target_url=norm,
        target_host=host,
        triggered_by=f"user:{user}",
        authorization_confirmed=True,
        authorization_declared_by=str(session.get("email") or session.get("user_id") or user),
        authorization_text=AUTHORIZATION_TEXT,
        authorized_at=now,
        status="pending",
    )
    db.add(run)
    db.commit()
    log.info("Security-Scan %s gestartet für %s durch %s", scan_id, host, user)

    background_tasks.add_task(engine.run_scan_in_background, scan_id, norm)
    return {"scan_id": scan_id, "status": "pending",
            "hinweis": "Scan läuft — Status über GET /api/security-scan/scan/{scan_id} abrufbar."}


def _get_run(scan_id: str, db: Session) -> SecurityScanRun:
    run = db.query(SecurityScanRun).filter(SecurityScanRun.scan_id == scan_id).first()
    if not run:
        raise HTTPException(404, "Scan nicht gefunden.")
    return run


@router.get("/scan/{scan_id}")
def scan_status(scan_id: str, session: dict = Depends(require_session), db: Session = Depends(get_db)) -> dict:
    return _status_payload(_get_run(scan_id, db))


@router.get("/scan/{scan_id}/report")
def scan_report(scan_id: str, session: dict = Depends(require_session), db: Session = Depends(get_db)) -> dict:
    run = _get_run(scan_id, db)
    return {
        **_status_payload(run),
        "authorized_by": run.authorization_declared_by,
        "authorization_text": run.authorization_text,
        "bezugsrahmen": "APP.3.1, NET.3.3, BSI TR-02102-2",
        "findings": run.findings or [],
        "observed": run.observed or {},
    }


@router.get("/scan/{scan_id}/pdf")
def scan_pdf(scan_id: str, session: dict = Depends(require_session), db: Session = Depends(get_db)) -> Response:
    run = _get_run(scan_id, db)
    if run.status != "completed":
        raise HTTPException(409, "Scan noch nicht abgeschlossen.")
    from services.security_scan.pdf import render_security_pdf
    pdf = render_security_pdf(run)
    fname = f"sicherheitspruefung_{(run.target_host or 'ziel').replace('.', '_')}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.get("/scan/{scan_id}/screenshot")
def scan_screenshot(scan_id: str, session: dict = Depends(require_session), db: Session = Depends(get_db)) -> FileResponse:
    run = _get_run(scan_id, db)
    if not run.screenshot_path or not Path(run.screenshot_path).exists():
        raise HTTPException(404, "Kein Screenshot vorhanden.")
    return FileResponse(run.screenshot_path, media_type="image/png")


@router.get("/scan/{scan_id}/architecture")
def scan_architecture(scan_id: str, session: dict = Depends(require_session), db: Session = Depends(get_db)) -> FileResponse:
    run = _get_run(scan_id, db)
    if not run.architecture_path or not Path(run.architecture_path).exists():
        raise HTTPException(404, "Kein Architektur-Diagramm vorhanden.")
    return FileResponse(run.architecture_path, media_type="image/png")
