"""
flowworkshop · routers/beneficiaries.py
Begünstigtenverzeichnis: Upload → Auto-Erkennung → Geocoding → Karte.
Alles in einem Flow, kein manuelles Tagging nötig.

Phase 6a: Upload zusaetzlich zur per-Source-Tabelle in die zentrale Tabelle
``workshop_beneficiary_records`` (Smart-Mode-Harvest, idempotent). Default
mode="smart" — bestehende Records bleiben unangetastet, neue werden ergaenzt.
"""
import logging
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query, Depends
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
    company_limit: int = Query(14, ge=1, le=50),
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
    mode: str = Query("top_beneficiaries", description="top_beneficiaries|repeat_beneficiaries|state_fund_totals|top_locations"),
    bundesland: str | None = Query(None),
    fonds: str | None = Query(None),
    source: str | None = Query(None),
    min_cost: float | None = Query(None, ge=0),
    limit: int = Query(10, ge=1, le=20),
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
