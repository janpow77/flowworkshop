"""
flowworkshop · routers/beneficiaries.py
Begünstigtenverzeichnis: Upload → Auto-Erkennung → Geocoding → Karte.
Alles in einem Flow, kein manuelles Tagging nötig.

Phase 6a: Upload zusaetzlich zur per-Source-Tabelle in die zentrale Tabelle
``workshop_beneficiary_records`` (Smart-Mode-Harvest, idempotent). Default
mode="smart" — bestehende Records bleiben unangetastet, neue werden ergaenzt.
"""
import csv
import io
import logging
import re
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse

from services.geocoding_service import get_beneficiary_map_data, detect_columns
from services.dataframe_service import (
    ingest_dataframe, get_beneficiary_sources, delete_dataframe_table,
    _detect_metadata, search_beneficiary_records, analyze_beneficiary_records,
)
from services.beneficiary_harvester import (
    BeneficiaryHarvestParams, run_beneficiary_harvest,
)
from database import SessionLocal
from services.country_profiles import (
    AUSTRIA_BENEFICIARY_SOURCES,
    COUNTRY_PROFILES,
    country_code_for_bundesland,
    get_country_name,
    get_country_profile,
    get_region_label,
    list_country_codes,
)
from routers.auth import require_moderator, require_moderator_or_worker, require_session

# Plan v3.2 §5.5: Karten- und Quellen-Daten sind nach Art. 49 VO (EU)
# 2021/1060 öffentlich. Daher kein require_session auf Router-Ebene —
# Schreib-/Admin-Endpoints unten setzen require_moderator selbst.
router = APIRouter(
    prefix="/api/beneficiaries",
    tags=["beneficiaries"],
)
log = logging.getLogger(__name__)


def _normalize_country_code(country_code: str | None) -> str | None:
    if not country_code:
        return None
    cc = country_code.strip().upper()
    if cc in COUNTRY_PROFILES:
        return cc
    raise HTTPException(400, f"Unbekannter country_code '{country_code}'.")


@router.get("/countries")
def list_countries():
    """Liefert die verfuegbaren Laender-Profile (DE/AT) inkl. Region-Listen."""
    return {
        "countries": [
            {
                "country_code": code,
                "country_name": profile["country_name"],
                "region_label": profile["region_label"],
                "regions": list(profile["regions"]),
            }
            for code, profile in COUNTRY_PROFILES.items()
        ],
        "presets": {
            "AT": AUSTRIA_BENEFICIARY_SOURCES,
        },
    }


@router.post("/upload")
async def upload_beneficiary_list(
    file: UploadFile = File(...),
    mode: str = Form(
        "smart",
        description=(
            "smart|full-refresh|force — Schreibstrategie fuer die zentrale "
            "Beneficiary-Tabelle. smart = idempotent (Default). "
            "full-refresh = Update bei Konflikt. force = Pre-Delete der Quelle."
        ),
    ),
    _session: dict = Depends(require_moderator_or_worker),
):
    """
    Begünstigtenverzeichnis hochladen.

    - Erkennt automatisch Bundesland, Fonds, Förderperiode und Land (DE/AT)
    - Erstellt eindeutigen Source-Namen (z.B. 'hessen_efre_2021-2027')
    - Ersetzt Duplikate (gleiches Bundesland+Fonds+Periode) in der per-Source
      Legacy-Tabelle (workshop_df_*)
    - Schreibt zusaetzlich Smart-Mode in die zentrale Tabelle
      ``workshop_beneficiary_records``: bei mode='smart' bleiben bestehende
      Records unberuehrt, neue werden ergaenzt — gewuenscht fuer Workshop-
      betrieb (Original-Bestand bleibt stabil, Korrekturen kontrolliert).
    """
    if not file.filename:
        raise HTTPException(422, "Dateiname fehlt.")

    if mode not in ("smart", "full-refresh", "force"):
        raise HTTPException(422, "mode muss smart|full-refresh|force sein.")

    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(422, "Datei zu gross (max. 50 MB).")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ("xlsx", "xls", "xlsm", "csv"):
        raise HTTPException(422, "Nur XLSX/XLS/CSV-Dateien werden akzeptiert.")

    # 1. Metadaten erkennen
    metadata = _detect_metadata(content, ext, source=file.filename)
    bundesland = metadata.get("bundesland") or "unbekannt"
    fonds = (metadata.get("fonds") or "EFRE").lower()
    periode = metadata.get("periode") or ""
    country_code = metadata.get("country_code") or country_code_for_bundesland(bundesland)
    country_name = metadata.get("country_name") or get_country_name(country_code)

    # 2. Source-Name generieren (eindeutig pro Land+Bundesland+Fonds+Periode)
    fonds_slug = fonds.replace("/", "_").replace("+", "plus")
    source = f"{bundesland.lower()}_{fonds_slug}"
    if country_code and country_code != "DE":
        source = f"{country_code.lower()}_{source}"
    if periode:
        source += f"_{periode.replace('-', '_')}"

    # 3. Prüfen ob Duplikat in der Legacy-Tabelle existiert.
    # Legacy-Tabelle bleibt fuer Backward-Compat erhalten — sie liefert die
    # Karte (Geocoding) und die alte Spalten-Erkennung. Phase 6a:
    # zusaetzlich die zentrale Tabelle befuellen.
    existing = get_beneficiary_sources()
    replaced = False
    for ex in existing:
        ex_cc = ex.get("country_code") or country_code_for_bundesland(ex.get("bundesland"))
        if ex_cc != country_code:
            continue
        if ex["bundesland"] == bundesland and ex["fonds"] == (metadata.get("fonds") or "EFRE"):
            if ex["periode"] == periode or (not ex["periode"] and not periode):
                # Duplikat → alte Tabelle löschen (Legacy-Pfad).
                delete_dataframe_table(ex["source"])
                log.info("Duplikat ersetzt: %s → %s", ex["source"], source)
                replaced = True
                break

    result = None
    last_error: Exception | None = None
    if ext == "csv":
        try:
            result = ingest_dataframe(
                content,
                file.filename,
                source,
                0,
                dataset_group="beneficiary",
            )
        except Exception as exc:
            last_error = exc
            log.warning("Beneficiary-CSV-Ingest fehlgeschlagen: %s (%s)", file.filename, exc)
            result = None
    else:
        # 4. Als DataFrame einlesen (smart header detection)
        for sheet in [
            0,
            "Liste der Vorhaben", "Vorhaben", "Begünstigte",
            "Transparenzliste", "Beneficiaries", "Förderempfänger",
            "Daten", "Data", "Übersicht", "Overview",
            "EFRE", "ESF", "JTF", "ELER",
            "Sheet1", "Tabelle1", "Blatt1",
        ]:
            try:
                result = ingest_dataframe(
                    content,
                    file.filename,
                    source,
                    sheet,
                    dataset_group="beneficiary",
                )
                if result["rows"] > 0:
                    break
            except Exception as exc:
                last_error = exc
                continue

    if not result or result["rows"] == 0:
        if last_error:
            log.warning("Beneficiary-Ingest ohne Ergebnis: %s (%s)", file.filename, last_error)
        raise HTTPException(422, "Keine Daten erkannt. Prüfen Sie das Dateiformat.")

    # 5. Spalten-Erkennung für Karte
    cols = detect_columns(source)
    has_location = bool(
        cols.get("standort") or cols.get("ort") or cols.get("plz")
        or (cols.get("latitude") and cols.get("longitude"))
    )

    # 6. Phase 6a: Smart-Mode-Harvest in die zentrale Tabelle.
    # Pflicht-Mappings (bundesland, fonds, periode, country_code) kommen
    # aus den oben erkannten Metadaten. Fehler im Harvest fuehren NICHT
    # zum Upload-Fehler — die Legacy-Tabelle ist ja schon befuellt.
    central_summary: dict | None = None
    db = SessionLocal()
    try:
        params = BeneficiaryHarvestParams(
            source_key=source,
            bundesland=bundesland if bundesland != "unbekannt" else None,
            fonds=metadata.get("fonds") or "EFRE",
            periode=periode or None,
            country_code=country_code,
            file_content=content,
            file_name=file.filename,
            sheet_name=None,
            header_row=0,
            mode=mode,  # type: ignore[arg-type]
            triggered_by=f"upload:{_session.get('user_id') or 'unknown'}",
        )
        central_summary = run_beneficiary_harvest(db, params)
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "Beneficiary-Harvest in zentrale Tabelle fehlgeschlagen "
            "(Legacy-Upload bleibt aktiv): %s", exc,
        )
    finally:
        db.close()

    return {
        "status": "replaced" if replaced else "created",
        "source": source,
        "filename": file.filename,
        "metadata": {
            "bundesland": bundesland,
            "fonds": metadata.get("fonds") or "EFRE",
            "periode": periode,
            "country_code": country_code,
            "country_name": country_name,
        },
        "rows": result["rows"],
        "columns": result["columns"],
        "has_location": has_location,
        "columns_detected": cols,
        "mode": mode,
        # Phase 6a: Insert/Skip/Failed-Zaehler aus dem Harvest in die
        # zentrale Tabelle. None, wenn der Harvest fehlgeschlagen ist
        # (Legacy-Upload war dennoch erfolgreich).
        "central_table": central_summary,
    }


@router.get("/sources")
def list_sources(country_code: str | None = Query(None, description="Optional Filter DE oder AT")):
    """Alle erkannten Begünstigtenverzeichnisse mit Metadaten (optional pro Land)."""
    cc = _normalize_country_code(country_code)
    sources = get_beneficiary_sources(country_code=cc)
    return {
        "country_code": cc,
        "available_country_codes": list_country_codes(),
        "sources": sources,
    }


@router.get("/map")
def get_map_data(country_code: str | None = Query(None, description="Optional Filter DE oder AT")):
    """
    Kartendaten für die eingelesenen Begünstigtenverzeichnisse.
    Wenn country_code gesetzt ist, werden nur Quellen dieses Landes aggregiert,
    damit DE und AT auf der Karte nicht vermischt werden.
    """
    cc = _normalize_country_code(country_code)
    sources = get_beneficiary_sources(country_code=cc)
    all_beneficiaries = []
    sources_info = []

    for src in sources:
        src_cc = src.get("country_code") or country_code_for_bundesland(src.get("bundesland"))
        data = get_beneficiary_map_data(src["source"], country_code=src_cc)
        for b in data.get("beneficiaries", []):
            b["bundesland"] = src.get("bundesland") or src["source"]
            b["fonds"] = src.get("fonds") or ""
            b["country_code"] = src_cc
            b["country_name"] = src.get("country_name") or get_country_name(src_cc)
        all_beneficiaries.extend(data.get("beneficiaries", []))
        sources_info.append({
            "source": src["source"],
            "country_code": src_cc,
            "country_name": src.get("country_name") or get_country_name(src_cc),
            "bundesland": src.get("bundesland"),
            "region_label": get_region_label(src_cc),
            "fonds": src.get("fonds"),
            "periode": src.get("periode"),
            "count": data.get("count", 0),
            "total_rows": src.get("row_count", 0),
        })

    profile = get_country_profile(cc) if cc else None
    return {
        "country_code": cc,
        "country_name": profile["country_name"] if profile else None,
        "region_label": profile["region_label"] if profile else "Region/Bundesland",
        "count": len(all_beneficiaries),
        "beneficiaries": all_beneficiaries,
        "sources": sources_info,
    }


@router.get("/search")
def search_beneficiaries(
    q: str = Query("", description="Suchbegriff fuer Unternehmen, Vorhaben oder Aktenzeichen"),
    scope: str = Query("all", description="all|company|project|aktenzeichen|location"),
    bundesland: str | None = Query(None),
    fonds: str | None = Query(None),
    source: str | None = Query(None),
    min_cost: float | None = Query(None, ge=0),
    limit: int = Query(60, ge=1, le=200),
    company_limit: int = Query(14, ge=1, le=200),
    country_code: str | None = Query(None, description="Optional Filter DE oder AT"),
    min_score: float | None = Query(
        None, ge=40.0, le=100.0,
        description=(
            "Fuzzy-Schwellwert (0..100). Wenn nicht gesetzt, wird er adaptiv "
            "aus der Query-Laenge bestimmt (1 Token=80, 2=70, ≥3=60) — "
            "konsistent mit /api/state-aid/search."
        ),
    ),
):
    cc = _normalize_country_code(country_code)
    try:
        return search_beneficiary_records(
            query=q,
            scope=scope,
            bundesland=bundesland,
            fonds=fonds,
            source=source,
            min_cost=min_cost,
            limit=limit,
            company_limit=company_limit,
            country_code=cc,
            min_score=min_score,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/analytics")
def analyze_beneficiaries(
    mode: str = Query("top_beneficiaries", description="top_beneficiaries|repeat_beneficiaries|state_fund_totals|top_locations|top_sectors|multi_state_beneficiaries|region_project_counts|kreis_project_counts"),
    bundesland: str | None = Query(None),
    fonds: str | None = Query(None),
    source: str | None = Query(None),
    min_cost: float | None = Query(None, ge=0),
    limit: int = Query(10, ge=1, le=100),
    country_code: str | None = Query(None, description="Optional Filter DE oder AT"),
):
    cc = _normalize_country_code(country_code)
    try:
        return analyze_beneficiary_records(
            mode=mode,
            bundesland=bundesland,
            fonds=fonds,
            source=source,
            min_cost=min_cost,
            limit=limit,
            country_code=cc,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/nuts")
def get_nuts_regions():
    """Gibt alle deutschen NUTS-3 Regionen zurueck."""
    from services.geocoding_service import _load_nuts
    nuts = _load_nuts()
    return {"count": len(nuts), "regions": nuts}


@router.delete("/{source}")
def delete_source(source: str, _session: dict = Depends(require_moderator)):
    """Begünstigtenverzeichnis entfernen."""
    delete_dataframe_table(source)
    return {"status": "deleted", "source": source}


# ── Export ────────────────────────────────────────────────────────────────────


_BEN_EXPORT_PFLICHTHINWEIS = (
    "Datenstand abhaengig vom letzten Upload pro Bundesland. Die Verzeichnisse "
    "werden aus den Transparenz-/Beguenstigtenlisten der Foerderbehoerden "
    "(Art. 49/69 VO (EU) 2021/1060) eingelesen. Mehrfacheintraege moeglich, "
    "wenn ein Beguenstigter in mehreren Vorhaben gefoerdert wurde."
)

_BEN_EXPORT_COLUMNS = [
    "company_name", "project_name", "aktenzeichen",
    "kosten", "kosten_label",
    "location", "bundesland", "fonds", "periode",
    "country_code", "country_name",
    "category", "description",
    "source", "nuts_code",
    "match_score", "match_confidence", "matched_fields",
]


def _safe_ben_filename_part(value: str) -> str:
    """Macht aus einem Suchbegriff einen sicheren Dateinamen-Bestandteil."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", (value or "").strip())[:40]
    return cleaned or "alle"


@router.get("/export")
def export_beneficiaries(
    format: str = Query("csv", pattern="^(csv|xlsx|pdf)$"),
    q: str = Query("", description="Suchbegriff fuer Unternehmen, Vorhaben oder Aktenzeichen"),
    scope: str = Query("all", description="all|company|project|aktenzeichen|location"),
    bundesland: str | None = Query(None),
    fonds: str | None = Query(None),
    source: str | None = Query(None),
    min_cost: float | None = Query(None, ge=0),
    limit: int = Query(500, ge=1, le=2000),
    country_code: str | None = Query(None, description="Optional Filter DE oder AT"),
    min_score: float | None = Query(
        None, ge=40.0, le=100.0,
        description="Fuzzy-Schwellwert (0..100). Default adaptiv aus Query-Laenge.",
    ),
):
    """Beneficiary-Search-Export — alle gefundenen Records als CSV / XLSX / PDF.

    Gleiche Filter-Parameter wie GET /search. Limit erhoeht (bis 2000), damit
    Pruefer den vollstaendigen Treffer-Satz exportieren koennen.
    """
    cc = _normalize_country_code(country_code)
    try:
        result = search_beneficiary_records(
            query=q,
            scope=scope,
            bundesland=bundesland,
            fonds=fonds,
            source=source,
            min_cost=min_cost,
            limit=limit,
            company_limit=1,  # Companies-Block ignorieren — wir exportieren records
            country_code=cc,
            min_score=min_score,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    raw_records = result.get("records") or []
    summary = result.get("summary") or {}

    rows: list[dict] = []
    for r in raw_records:
        rows.append({
            "company_name": r.get("company_name") or "",
            "project_name": r.get("project_name") or "",
            "aktenzeichen": r.get("aktenzeichen") or "",
            "kosten": r.get("kosten") if r.get("kosten") is not None else "",
            "kosten_label": r.get("kosten_label") or "",
            "location": r.get("location") or "",
            "bundesland": r.get("bundesland") or "",
            "fonds": r.get("fonds") or "",
            "periode": r.get("periode") or "",
            "country_code": r.get("country_code") or "",
            "country_name": r.get("country_name") or "",
            "category": r.get("category") or "",
            "description": r.get("description") or "",
            "source": r.get("source") or "",
            "nuts_code": r.get("nuts_code") or "",
            "match_score": r.get("match_score") if r.get("match_score") is not None else "",
            "match_confidence": r.get("match_confidence") or "",
            "matched_fields": r.get("matched_fields") or [],
        })

    metadata: dict[str, str] = {
        "Suchbegriff": q or "(leer)",
        "Scope": scope,
        "Trefferzahl": str(len(rows)),
        "Records gescannt": str(int(summary.get("records_scanned") or 0)),
        "Quellen": str(int(summary.get("sources_considered") or 0)),
    }
    if cc:
        metadata["Land"] = cc
    if bundesland:
        metadata["Bundesland"] = bundesland
    if fonds:
        metadata["Fonds"] = fonds
    if source:
        metadata["Quelle"] = source
    if min_cost is not None:
        metadata["Mindestbetrag"] = f"{min_cost:.0f} EUR"
    if min_score is not None:
        metadata["Schwellenwert"] = f"{min_score:.1f}"

    safe_q = _safe_ben_filename_part(q or "alle")
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    if format == "xlsx":
        from services.excel_export import (
            XLSX_MEDIA_TYPE,
            make_xlsx,
            xlsx_response_headers,
        )
        xlsx_bytes = make_xlsx(
            rows,
            sheet_name="Beguenstigte",
            headers=_BEN_EXPORT_COLUMNS,
            table_name="Beguenstigte",
            pflichthinweis=_BEN_EXPORT_PFLICHTHINWEIS,
            metadata=metadata,
            notes_title="Beguenstigtenverzeichnis · Hinweise",
        )
        filename = f"beguenstigte_{safe_q}_{timestamp}.xlsx"
        return StreamingResponse(
            iter([xlsx_bytes]),
            media_type=XLSX_MEDIA_TYPE,
            headers=xlsx_response_headers(filename),
        )

    if format == "pdf":
        return _stream_beneficiaries_pdf(rows, metadata)

    # CSV (default)
    buf = io.StringIO()
    buf.write("﻿")  # UTF-8 BOM für Excel
    buf.write(f"# FlowWorkshop · Beguenstigtensuche-Export · {datetime.utcnow().isoformat()}Z\n")
    buf.write(f"# {_BEN_EXPORT_PFLICHTHINWEIS}\n")
    for k, v in metadata.items():
        buf.write(f"# {k}: {v}\n")

    writer = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(_BEN_EXPORT_COLUMNS)
    for d in rows:
        cells = []
        for k in _BEN_EXPORT_COLUMNS:
            v = d.get(k)
            if v is None or v == "":
                cells.append("")
            elif isinstance(v, (list, tuple)):
                cells.append(" | ".join(str(x) for x in v if x))
            else:
                cells.append(str(v))
        writer.writerow(cells)

    filename = f"beguenstigte_{safe_q}_{timestamp}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _stream_beneficiaries_pdf(rows: list[dict], metadata: dict[str, str]) -> StreamingResponse:
    """Beneficiary-PDF analog zu state_aid: pymupdf, A4 quer, Pflichthinweis im Footer."""
    try:
        import fitz  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            501,
            f"PDF-Export nicht verfuegbar: pymupdf nicht installiert ({exc}).",
        ) from exc

    doc = fitz.open()
    page = doc.new_page(width=842, height=595)
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

    _write("FlowWorkshop · Beguenstigtensuche", size=14, bold=True)
    _write(datetime.utcnow().strftime("Erstellt: %Y-%m-%d %H:%M UTC"), size=9)
    for k, v in metadata.items():
        _write(f"  · {k}: {v}", size=8)
    cursor_y += line_height // 2

    _write(f"Treffer: {len(rows)}", size=10, bold=True)
    cursor_y += line_height // 2

    for r in rows:
        kosten_label = r.get("kosten_label") or "—"
        _write(
            f"{r.get('company_name', '')} · {r.get('bundesland') or '—'} · "
            f"{kosten_label}",
            size=9, bold=True,
        )
        if r.get("project_name"):
            _write(f"   Vorhaben: {r['project_name'][:160]}", size=8)
        if r.get("aktenzeichen"):
            _write(f"   Aktenzeichen: {r['aktenzeichen']}", size=8)
        if r.get("location"):
            _write(f"   Standort: {r['location'][:120]}", size=8)
        if r.get("fonds") or r.get("periode"):
            _write(
                f"   Fonds: {r.get('fonds') or '—'} · Periode: {r.get('periode') or '—'}",
                size=8,
            )
        cursor_y += 2

    _write("", size=8)
    _write(_BEN_EXPORT_PFLICHTHINWEIS, size=7)

    pdf_bytes = doc.tobytes()
    doc.close()

    suchbegriff = metadata.get("Suchbegriff", "alle")
    filename = (
        f"beguenstigte_{_safe_ben_filename_part(suchbegriff)}_"
        f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
    )
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
