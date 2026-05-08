"""
flowworkshop · routers/beneficiaries_sources.py

Phase 6b — Admin-API fuer die datengetriebene Beneficiary-Quellen-Verwaltung.

Pattern: Worker liest die Config-Tabelle ``workshop_beneficiary_sources_config``
und macht den Smart-Mode-Harvest datengetrieben (kein Code-Patch noetig,
wenn ein neues Bundesland dazukommt).

Endpoints (alle Admin-only):

  - GET    /api/admin/beneficiary-sources                  — Liste aller Configs
  - GET    /api/admin/beneficiary-sources/{source_key}     — eine Config
  - POST   /api/admin/beneficiary-sources                  — neue Config anlegen
  - PUT    /api/admin/beneficiary-sources/{source_key}     — Config updaten
  - DELETE /api/admin/beneficiary-sources/{source_key}     — soft-disable
  - POST   /api/admin/beneficiary-sources/{key}/test-run   — Test-Harvest ohne DB-Write
  - POST   /api/admin/beneficiary-sources/{key}/harvest    — manueller Trigger
  - GET    /api/admin/beneficiary-sources/{key}/runs       — letzte HarvestRun-Eintraege
"""
from __future__ import annotations

import io
import logging
import re
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from database import get_db
from models.beneficiary_records import BeneficiaryHarvestRun, BeneficiaryRecord
from models.beneficiary_sources_config import BeneficiarySourceConfig
from routers.auth import require_admin
from services.beneficiary_harvester import (
    BeneficiaryHarvestParams,
    parse_xlsx_or_csv,
    run_beneficiary_harvest,
)

router = APIRouter(prefix="/api/admin/beneficiary-sources", tags=["beneficiary-sources-admin"])
log = logging.getLogger(__name__)


# ── Pydantic Schemas ──────────────────────────────────────────────────────────


class BeneficiarySourceConfigIn(BaseModel):
    """Input-Schema fuer POST/PUT der Quellen-Config.

    ``source_key`` muss ein technischer Slug sein — kleine Buchstaben, Zahlen,
    Unter-/Bindestriche. Das verhindert Probleme mit URL-Routing und
    vermeidet, dass das Admin-UI versehentlich Sonderzeichen einliefert.
    """

    source_key: str = Field(
        ..., max_length=120, pattern=r"^[a-z0-9_-]+$",
        description="Technischer Slug (lowercase, [a-z0-9_-]).",
    )
    display_name: str = Field(..., max_length=200)
    bundesland: str | None = Field(None, max_length=80)
    fonds: str | None = Field(None, max_length=40)
    periode: str | None = Field(None, max_length=20)
    country_code: str | None = Field(None, max_length=3)
    source_type: Literal["xlsx_url", "csv_url", "manual_upload"]
    source_url: str | None = Field(None, max_length=500)
    source_landing_page: str | None = Field(None, max_length=500)
    update_frequency_days: int | None = Field(None, ge=1, le=3650)
    license: str | None = Field(None, max_length=120)
    sheet_name: str | None = Field(None, max_length=80)
    header_row: int = 0
    field_mapping: dict[str, str] | None = None
    required_fields: list[str] | None = None
    validations: list[dict[str, Any]] | None = None
    enabled: bool = True
    coverage_note: str | None = None
    notes_for_pruefer: str | None = None


class BeneficiarySourceConfigUpdate(BaseModel):
    """PATCH-/PUT-Schema — alle Felder optional.

    ``source_key`` ist nicht aenderbar (Primary-Key, fungiert als logische
    Identitaet der Quelle). Wer den Schluessel aendern will, muss die Config
    loeschen und neu anlegen.
    """

    display_name: str | None = Field(None, max_length=200)
    bundesland: str | None = Field(None, max_length=80)
    fonds: str | None = Field(None, max_length=40)
    periode: str | None = Field(None, max_length=20)
    country_code: str | None = Field(None, max_length=3)
    source_type: Literal["xlsx_url", "csv_url", "manual_upload"] | None = None
    source_url: str | None = Field(None, max_length=500)
    source_landing_page: str | None = Field(None, max_length=500)
    update_frequency_days: int | None = Field(None, ge=1, le=3650)
    license: str | None = Field(None, max_length=120)
    sheet_name: str | None = Field(None, max_length=80)
    header_row: int | None = None
    field_mapping: dict[str, str] | None = None
    required_fields: list[str] | None = None
    validations: list[dict[str, Any]] | None = None
    enabled: bool | None = None
    coverage_note: str | None = None
    notes_for_pruefer: str | None = None


# ── Helper ────────────────────────────────────────────────────────────────────


def _config_to_dict(cfg: BeneficiarySourceConfig) -> dict[str, Any]:
    """Serialisiert eine Config-Zeile fuer JSON-Responses.

    Datums-Felder werden als ISO-Strings ausgegeben — sonst wuerde Pydantic
    sie nicht JSON-serialisieren koennen (DateTime ist nicht json-kompatibel).
    """
    return {
        "source_key": cfg.source_key,
        "display_name": cfg.display_name,
        "bundesland": cfg.bundesland,
        "fonds": cfg.fonds,
        "periode": cfg.periode,
        "country_code": cfg.country_code,
        "source_type": cfg.source_type,
        "source_url": cfg.source_url,
        "source_landing_page": cfg.source_landing_page,
        "update_frequency_days": cfg.update_frequency_days,
        "license": cfg.license,
        "sheet_name": cfg.sheet_name,
        "header_row": int(cfg.header_row or 0),
        "field_mapping": cfg.field_mapping or {},
        "required_fields": cfg.required_fields or [],
        "validations": cfg.validations or [],
        "enabled": bool(cfg.enabled),
        "last_successful_harvest_at": (
            cfg.last_successful_harvest_at.isoformat()
            if cfg.last_successful_harvest_at else None
        ),
        "last_harvest_run_id": cfg.last_harvest_run_id,
        "last_seen_sha256": cfg.last_seen_sha256,
        "record_count": int(cfg.record_count or 0),
        "quality": cfg.quality,
        "coverage_note": cfg.coverage_note,
        "notes_for_pruefer": cfg.notes_for_pruefer,
        "created_at": cfg.created_at.isoformat() if cfg.created_at else None,
        "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
    }


def _validate_row(
    row: dict[str, Any],
    required_fields: list[str] | None,
    validations: list[dict[str, Any]] | None,
) -> list[str]:
    """Prueft eine geparste Zeile gegen required_fields + Regex-Validations.

    Liefert eine Liste menschenlesbarer Fehlertexte. Leer = ok.
    Validations-Format::

        [{"field": "cost_total", "regex": "^\\d", "message": "Pflicht"}]
    """
    findings: list[str] = []
    for fld in required_fields or []:
        v = row.get(fld)
        if v is None or (isinstance(v, str) and not v.strip()):
            findings.append(f"Pflichtfeld '{fld}' fehlt.")
    for rule in validations or []:
        fld = rule.get("field")
        rx = rule.get("regex")
        if not fld or not rx:
            continue
        v = row.get(fld)
        if v is None:
            continue
        try:
            if not re.search(rx, str(v)):
                msg = rule.get("message") or f"Regex '{rx}' verletzt"
                findings.append(f"{fld}: {msg} (Wert='{v}')")
        except re.error as exc:
            findings.append(f"{fld}: ungueltiges Regex ({exc})")
    return findings


def _get_config_or_404(db: Session, source_key: str) -> BeneficiarySourceConfig:
    cfg = (
        db.query(BeneficiarySourceConfig)
        .filter(BeneficiarySourceConfig.source_key == source_key)
        .first()
    )
    if not cfg:
        raise HTTPException(404, f"Quelle '{source_key}' nicht gefunden.")
    return cfg


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("")
def list_sources(
    _session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Listet alle Quellen-Configs (auch disabled).

    Sortiert nach country_code, display_name fuer eine stabile Anzeige im
    Admin-UI. Die Liste ist klein genug (~50 Eintraege), sodass Pagination
    nicht noetig ist.
    """
    rows = (
        db.query(BeneficiarySourceConfig)
        .order_by(
            BeneficiarySourceConfig.country_code.asc().nullslast(),
            BeneficiarySourceConfig.display_name.asc(),
        )
        .all()
    )
    return {"count": len(rows), "sources": [_config_to_dict(r) for r in rows]}


@router.get("/{source_key}")
def get_source(
    source_key: str,
    _session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Eine einzelne Quellen-Config inkl. Field-Mapping/Validations."""
    cfg = _get_config_or_404(db, source_key)
    return _config_to_dict(cfg)


@router.post("", status_code=201)
def create_source(
    body: BeneficiarySourceConfigIn,
    _session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Neue Config anlegen.

    Validiert source_key auf Eindeutigkeit. Bei xlsx_url/csv_url ist
    ``source_url`` Pflicht — sonst kann der Worker nichts laden.
    """
    existing = (
        db.query(BeneficiarySourceConfig)
        .filter(BeneficiarySourceConfig.source_key == body.source_key)
        .first()
    )
    if existing:
        raise HTTPException(409, f"Quelle '{body.source_key}' existiert bereits.")

    if body.source_type in ("xlsx_url", "csv_url") and not body.source_url:
        raise HTTPException(
            422,
            f"source_type='{body.source_type}' erfordert eine source_url.",
        )

    cfg = BeneficiarySourceConfig(
        source_key=body.source_key,
        display_name=body.display_name,
        bundesland=body.bundesland,
        fonds=body.fonds,
        periode=body.periode,
        country_code=body.country_code,
        source_type=body.source_type,
        source_url=body.source_url,
        source_landing_page=body.source_landing_page,
        update_frequency_days=body.update_frequency_days,
        license=body.license,
        sheet_name=body.sheet_name,
        header_row=body.header_row,
        field_mapping=body.field_mapping,
        required_fields=body.required_fields,
        validations=body.validations,
        enabled=body.enabled,
        coverage_note=body.coverage_note,
        notes_for_pruefer=body.notes_for_pruefer,
    )
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    log.info("Beneficiary-Quelle angelegt: %s (%s)", cfg.source_key, cfg.source_type)
    return _config_to_dict(cfg)


@router.put("/{source_key}")
def update_source(
    source_key: str,
    body: BeneficiarySourceConfigUpdate,
    _session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Config-Felder updaten.

    None-Felder im Body werden ignoriert (PATCH-Semantik). source_key kann
    nicht geaendert werden — wer das will, soll loeschen + neu anlegen.
    """
    cfg = _get_config_or_404(db, source_key)
    payload = body.model_dump(exclude_unset=True)
    for field, value in payload.items():
        setattr(cfg, field, value)
    db.commit()
    db.refresh(cfg)
    log.info("Beneficiary-Quelle aktualisiert: %s", source_key)
    return _config_to_dict(cfg)


@router.delete("/{source_key}")
def delete_source(
    source_key: str,
    _session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Soft-Disable: ``enabled=false``.

    Wir loeschen Configs nicht hart — sonst gehen die last_seen_sha256-
    Hashes verloren, die wichtig sind, falls die Quelle spaeter wieder
    eingeschaltet wird (Worker erkennt sonst unveraenderte Datei als
    'neu' und macht einen unnoetigen Re-Harvest).
    """
    cfg = _get_config_or_404(db, source_key)
    cfg.enabled = False
    db.commit()
    log.info("Beneficiary-Quelle soft-disabled: %s", source_key)
    return {"status": "disabled", "source_key": source_key}


@router.post("/{source_key}/test-run")
async def test_run_source(
    source_key: str,
    file: UploadFile | None = File(None),
    _session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Test-Harvest ohne DB-Write.

    Liest die XLSX/CSV (entweder vom Upload oder per source_url), parsed sie
    mit dem konfigurierten ``field_mapping`` und liefert eine Vorschau:
    erkannte Felder + erste 10 Zeilen + Validation-Findings. Schreibt nichts
    in die zentrale Tabelle.

    Bei source_type=manual_upload muss eine Datei mit-hochgeladen werden.
    Bei source_type=xlsx_url/csv_url wird die source_url geholt — wenn
    eine Datei mit-hochgeladen wird, hat die Vorrang.
    """
    cfg = _get_config_or_404(db, source_key)

    file_content: bytes | None = None
    file_name: str = ""
    fetch_source: str = "upload"

    if file is not None:
        file_content = await file.read()
        file_name = file.filename or f"{source_key}.xlsx"
    elif cfg.source_type in ("xlsx_url", "csv_url") and cfg.source_url:
        # Lazy-Import von httpx — nur wenn URL-Mode wirklich gebraucht wird.
        try:
            import httpx
            with httpx.Client(timeout=60.0, follow_redirects=True) as client:
                r = client.get(cfg.source_url)
                r.raise_for_status()
                file_content = r.content
                file_name = (
                    cfg.source_url.rsplit("/", 1)[-1]
                    or f"{source_key}.xlsx"
                )
                fetch_source = "url"
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                502, f"Quelle nicht erreichbar: {exc}"
            ) from exc
    else:
        raise HTTPException(
            422,
            "Bitte eine Datei hochladen oder source_type auf xlsx_url/csv_url "
            "mit gueltiger source_url setzen.",
        )

    if not file_content:
        raise HTTPException(422, "Leere Datei oder leerer URL-Inhalt.")

    # Parse — ohne DB-Write. Wir nehmen die ersten 10 Datenzeilen.
    preview: list[dict[str, Any]] = []
    detected_mapping: dict[str, str] = {}
    skipped_no_name = 0
    validation_findings: list[dict[str, Any]] = []

    try:
        for parsed in parse_xlsx_or_csv(
            file_content,
            file_name=file_name,
            sheet=cfg.sheet_name,
            header_row=int(cfg.header_row or 0),
            field_mapping=cfg.field_mapping,
        ):
            if parsed.get("_skip_reason") == "no_name":
                skipped_no_name += 1
                continue
            if not detected_mapping and parsed.get("mapping"):
                detected_mapping = dict(parsed["mapping"])
            if len(preview) < 10:
                preview_row = {
                    k: v for k, v in parsed.items()
                    if not k.startswith("_") and k not in ("raw_row", "mapping")
                }
                # Validations gegen die kanonisch-extrahierten Felder.
                findings = _validate_row(
                    preview_row,
                    cfg.required_fields,
                    cfg.validations,
                )
                if findings:
                    validation_findings.append({
                        "row_number": parsed.get("_row_number"),
                        "issues": findings,
                    })
                preview.append({
                    "row_number": parsed.get("_row_number"),
                    "fields": preview_row,
                })
    except Exception as exc:  # noqa: BLE001
        log.warning("Test-Run fehlgeschlagen fuer %s: %s", source_key, exc)
        raise HTTPException(
            422, f"Datei konnte nicht geparst werden: {exc}"
        ) from exc

    return {
        "source_key": source_key,
        "fetch_source": fetch_source,
        "file_name": file_name,
        "file_size_bytes": len(file_content),
        "rows_parsed": len(preview) + skipped_no_name,
        "preview_rows_returned": len(preview),
        "skipped_no_name": skipped_no_name,
        "detected_field_mapping": detected_mapping,
        "preview": preview,
        "validation_findings": validation_findings,
        "validation_findings_count": len(validation_findings),
    }


@router.post("/{source_key}/harvest")
async def harvest_source(
    source_key: str,
    file: UploadFile | None = File(None),
    mode: str = Form("smart"),
    session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Manueller Harvest-Trigger.

    Bei source_type=manual_upload muss eine Datei mit-hochgeladen werden.
    Bei xlsx_url/csv_url wird die source_url verwendet, falls keine Datei
    da ist. Verwendet ``run_beneficiary_harvest`` mit dem konfigurierten
    field_mapping. Der ``mode``-Parameter erlaubt smart (Default),
    full-refresh oder force.
    """
    if mode not in ("smart", "full-refresh", "force"):
        raise HTTPException(422, "mode muss smart|full-refresh|force sein.")

    cfg = _get_config_or_404(db, source_key)

    file_content: bytes | None = None
    file_name: str = ""

    if file is not None:
        file_content = await file.read()
        file_name = file.filename or f"{source_key}.xlsx"
    elif cfg.source_type in ("xlsx_url", "csv_url") and cfg.source_url:
        try:
            import httpx
            with httpx.Client(timeout=180.0, follow_redirects=True) as client:
                r = client.get(cfg.source_url)
                r.raise_for_status()
                file_content = r.content
                file_name = (
                    cfg.source_url.rsplit("/", 1)[-1]
                    or f"{source_key}.xlsx"
                )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(502, f"Quelle nicht erreichbar: {exc}") from exc
    else:
        raise HTTPException(
            422,
            "Bitte eine Datei hochladen oder source_type auf xlsx_url/csv_url "
            "setzen.",
        )

    actor_id = session.get("user_id") or "unknown"
    triggered_by = f"admin:{actor_id}"

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
        mode=mode,  # type: ignore[arg-type]
        triggered_by=triggered_by,
    )

    try:
        result = run_beneficiary_harvest(db, params)
    except Exception as exc:  # noqa: BLE001
        log.exception("Manueller Harvest fehlgeschlagen fuer %s", source_key)
        raise HTTPException(502, f"Harvest fehlgeschlagen: {exc}") from exc

    # Worker-Status pflegen — analog zur Auto-Harvest-Logik im Scheduler.
    try:
        cfg.last_harvest_run_id = result.get("run_id")
        if result.get("status") in ("ok", "partial"):
            cfg.last_successful_harvest_at = datetime.utcnow()
        # record_count = aktuelle Anzahl der Records dieser Quelle.
        rc = (
            db.query(BeneficiaryRecord)
            .filter(BeneficiaryRecord.source_key == source_key)
            .count()
        )
        cfg.record_count = rc
        if result.get("status") == "ok":
            cfg.quality = "green"
        elif result.get("status") == "partial":
            cfg.quality = "yellow"
        else:
            cfg.quality = "red"
        db.commit()
    except Exception:  # noqa: BLE001
        log.exception("Status-Update der Config nach Harvest fehlgeschlagen")

    return result


@router.get("/{source_key}/runs")
def list_runs(
    source_key: str,
    limit: int = 10,
    _session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Letzte ``limit`` Harvest-Run-Eintraege fuer eine Quelle.

    Sortierung: neueste zuerst. Default 10 Eintraege — fuer das Admin-UI
    ausreichend, ohne dass die UI grosse Listen pagen muss.
    """
    _get_config_or_404(db, source_key)  # 404, falls Config fehlt
    limit = max(1, min(100, int(limit)))

    rows = (
        db.query(BeneficiaryHarvestRun)
        .filter(BeneficiaryHarvestRun.source_key == source_key)
        .order_by(desc(BeneficiaryHarvestRun.started_at))
        .limit(limit)
        .all()
    )
    return {
        "source_key": source_key,
        "count": len(rows),
        "runs": [
            {
                "id": r.id,
                "source_key": r.source_key,
                "status": r.status,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "records_seen": int(r.records_seen or 0),
                "records_inserted": int(r.records_inserted or 0),
                "records_skipped": int(r.records_skipped or 0),
                "records_failed": int(r.records_failed or 0),
                "triggered_by": r.triggered_by,
                "error_message": r.error_message,
                "parameters": r.parameters or {},
            }
            for r in rows
        ],
    }
