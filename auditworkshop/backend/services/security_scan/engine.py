"""Scan-Engine: orchestriert die nicht-intrusiven Prüf-Module, holt den
Screenshot, rendert das Architektur-Diagramm und persistiert das Ergebnis.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

from config import (
    SCREENSHOT_SERVICE_URL,
    SECURITY_PROBE_TIMEOUT_S,
    SECURITY_SCAN_STORAGE_ROOT,
)
from .architecture import render_architecture_png
from .checks import http_probe, ports as ports_check, tls as tls_check, version_cve
from .report import aggregate

log = logging.getLogger(__name__)


def normalize_target(raw: str) -> tuple[str, str, int]:
    """(normalisierte_url, host, https_port). Default-Schema https."""
    raw = (raw or "").strip()
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    parsed = urlparse(raw)
    host = parsed.hostname or ""
    port = parsed.port or 443
    norm = f"https://{host}" + (f":{parsed.port}" if parsed.port and parsed.port != 443 else "")
    return norm, host, port


def _storage_dir(scan_id: str) -> Path:
    d = Path(SECURITY_SCAN_STORAGE_ROOT) / scan_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _capture_screenshot(url: str, scan_id: str) -> str | None:
    """Ruft den Screenshot-Microservice; speichert PNG. None bei Ausfall."""
    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(f"{SCREENSHOT_SERVICE_URL}/screenshot",
                               json={"url": url, "full_page": False})
            resp.raise_for_status()
            png = resp.content
        path = _storage_dir(scan_id) / "screenshot.png"
        path.write_bytes(png)
        return str(path)
    except Exception as exc:  # noqa: BLE001
        log.warning("Screenshot fehlgeschlagen für %s: %s", url, exc)
        return None


def perform_scan(scan_id: str, target_url: str) -> dict:
    """Führt alle Module aus und liefert das aggregierte Ergebnis-Dict."""
    timeout = SECURITY_PROBE_TIMEOUT_S
    norm, host, port = normalize_target(target_url)

    findings = []
    observed: dict = {}

    tls_findings, tls_obs = tls_check.check_tls(host, port, timeout, hostname=host)
    findings += tls_findings
    observed["tls"] = tls_obs

    http_findings, http_obs = http_probe.probe_http(host, timeout)
    findings += http_findings
    observed["http"] = http_obs

    findings.append(version_cve.check_cve(http_obs, timeout))

    port_findings, port_obs = ports_check.check_ports(host, timeout)
    findings += port_findings
    observed["ports"] = port_obs

    agg = aggregate(findings)
    findings_by_id = {f.pruef_id: f for f in findings}

    # Architektur-Diagramm
    arch_path = None
    try:
        png = render_architecture_png(host, observed, findings_by_id)
        p = _storage_dir(scan_id) / "architecture.png"
        p.write_bytes(png)
        arch_path = str(p)
    except Exception:  # noqa: BLE001
        log.exception("Architektur-Diagramm fehlgeschlagen für %s", host)

    # Screenshot (Microservice)
    screenshot_path = _capture_screenshot(norm, scan_id)

    return {
        "host": host,
        "norm_url": norm,
        "findings": [f.to_dict() for f in findings],
        "observed": observed,
        "counts": agg["counts"],
        "overall": agg["overall"],
        "screenshot_path": screenshot_path,
        "architecture_path": arch_path,
    }


def run_scan_in_background(scan_id: str, target_url: str) -> None:
    """Eigene DB-Session (Request-Session ist nach dem Response zu)."""
    from database import SessionLocal
    from models.security_scan import SecurityScanRun

    db = SessionLocal()
    try:
        run = db.query(SecurityScanRun).filter(SecurityScanRun.scan_id == scan_id).first()
        if not run:
            log.error("Scan-Run %s nicht gefunden.", scan_id)
            return
        run.status = "running"
        db.commit()
        result = perform_scan(scan_id, target_url)
        run.target_host = result["host"]
        run.findings = result["findings"]
        run.observed = result["observed"]
        run.count_konform = result["counts"].get("konform", 0)
        run.count_gelb = result["counts"].get("gelb", 0)
        run.count_rot = result["counts"].get("rot", 0)
        run.count_grau = result["counts"].get("grau", 0)
        run.overall = result["overall"]
        run.screenshot_path = result["screenshot_path"]
        run.architecture_path = result["architecture_path"]
        run.status = "completed"
        run.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()
        log.info("Security-Scan %s abgeschlossen: overall=%s", scan_id, result["overall"])
    except Exception as exc:  # noqa: BLE001
        log.exception("Security-Scan %s fehlgeschlagen", scan_id)
        try:
            run = db.query(SecurityScanRun).filter(SecurityScanRun.scan_id == scan_id).first()
            if run:
                run.status = "failed"
                run.error_message = str(exc)[:1000]
                run.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
                db.commit()
        except Exception:  # noqa: BLE001
            pass
    finally:
        db.close()
