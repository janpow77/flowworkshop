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
import threading
import time as _time
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
from routers.auth import require_moderator, require_moderator_or_worker

# Plan v3.2 §5.5: Karten- und Quellen-Daten sind nach Art. 49 VO (EU)
# 2021/1060 öffentlich. Daher kein require_session auf Router-Ebene —
# Schreib-/Admin-Endpoints unten setzen require_moderator selbst.
router = APIRouter(
    prefix="/api/beneficiaries",
    tags=["beneficiaries"],
)
log = logging.getLogger(__name__)


# ── Map-Cache ──────────────────────────────────────────────────────────────
# Der Aufbau der Kartendaten (Geocoding + Serialisierung von ~72k Records über
# 33 Quellen-Tabellen) dauert auf der CCX23 ~19 s und wurde bislang bei JEDEM
# Aufruf neu berechnet — Ursache für „failed to fetch" (Gateway-Timeout) sowohl
# auf der Karte als auch auf der HomePage. Die Daten ändern sich nur bei
# Upload/Delete, daher cachen wir das fertige Ergebnis pro country_code.
# Die TTL ist ein Sicherheitsnetz für Out-of-Band-Ingest (harvest_*.py).
_MAP_CACHE: dict[str | None, tuple[float, dict]] = {}
_MAP_CACHE_TTL = 3600.0  # 1 h
_MAP_CACHE_LOCK = threading.Lock()   # schützt nur das Cache-Dict (schnell)
_MAP_BUILD_LOCK = threading.Lock()   # serialisiert teure Builds (Stampede-Schutz)


def invalidate_map_cache() -> None:
    """Verwirft den kompletten Map-Cache — nach Upload/Delete aufrufen.

    Invalidiert zugleich den Begünstigten-Analytics-/Scan-Cache (Befund 3),
    damit top_locations/top_sectors denselben Lebenszyklus haben."""
    with _MAP_CACHE_LOCK:
        _MAP_CACHE.clear()
    try:
        from services.dataframe_service import invalidate_analytics_cache
        invalidate_analytics_cache()
    except Exception:  # noqa: BLE001 — Cache-Invalidierung darf nie brechen
        log.exception("Analytics-Cache-Invalidierung fehlgeschlagen.")
    log.info("Map-Cache invalidiert.")


def _build_map_payload(cc: str | None) -> dict:
    """Baut die Kartendaten frisch auf (teuer, ~19 s). Quelle der Wahrheit
    für get_map_data — wird nur über get_cached_map_payload aufgerufen."""
    sources = get_beneficiary_sources(country_code=cc)
    all_beneficiaries: list[dict] = []
    sources_info: list[dict] = []

    for src in sources:
        src_cc = src.get("country_code") or country_code_for_bundesland(src.get("bundesland"))
        data = get_beneficiary_map_data(src["source"], country_code=src_cc)
        for b in data.get("beneficiaries", []):
            b["bundesland"] = src.get("bundesland") or src["source"]
            b["fonds"] = src.get("fonds") or ""
            b["country_code"] = src_cc
            b["country_name"] = src.get("country_name") or get_country_name(src_cc)
            # nuts3/region werden im Frontend nicht gerendert → Payload schlank halten.
            b.pop("nuts3", None)
            b.pop("region", None)
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


def get_cached_map_payload(cc: str | None, *, force: bool = False) -> dict:
    """Liefert die Kartendaten aus dem Cache oder baut sie (einmalig) auf.

    Cache-Treffer werden nie durch einen laufenden Build blockiert; gleichzeitige
    Cold-Aufrufe werden über _MAP_BUILD_LOCK serialisiert (kein Stampede).
    """
    now = _time.time()
    if not force:
        with _MAP_CACHE_LOCK:
            hit = _MAP_CACHE.get(cc)
        if hit and (now - hit[0]) < _MAP_CACHE_TTL:
            return hit[1]

    with _MAP_BUILD_LOCK:
        # Double-Check: ein paralleler Thread könnte gerade fertig gebaut haben.
        if not force:
            with _MAP_CACHE_LOCK:
                hit = _MAP_CACHE.get(cc)
            if hit and (_time.time() - hit[0]) < _MAP_CACHE_TTL:
                return hit[1]
        payload = _build_map_payload(cc)
        with _MAP_CACHE_LOCK:
            _MAP_CACHE[cc] = (_time.time(), payload)
        return payload


def warm_map_cache(country_codes: tuple[str | None, ...] = (None, "DE", "AT")) -> None:
    """Baut den Map-Cache im Hintergrund vor (beim App-Start). Fehler pro Land
    werden geschluckt — der Cache füllt sich sonst beim ersten Request."""
    for cc in country_codes:
        try:
            t0 = _time.time()
            payload = get_cached_map_payload(cc, force=True)
            log.info(
                "Map-Cache vorgewärmt: %s → %d Records in %.1fs",
                cc or "ALLE", payload.get("count", 0), _time.time() - t0,
            )
        except Exception as exc:  # noqa: BLE001 — Warmup darf den Start nie brechen
            log.warning("Map-Cache-Warmup für %s fehlgeschlagen: %s", cc, exc)


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

    # Neue/ersetzte Quelle → Map-Cache verwerfen, sonst zeigt die Karte
    # weiterhin den alten Stand bis zum TTL-Ablauf.
    invalidate_map_cache()

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

    Ergebnis wird pro country_code gecacht (siehe get_cached_map_payload) — der
    teure Geocoding-/Serialisierungs-Aufbau läuft nur bei kaltem Cache bzw. nach
    Upload/Delete erneut.
    """
    cc = _normalize_country_code(country_code)
    return get_cached_map_payload(cc)


@router.get("/summary")
def beneficiaries_summary(country_code: str | None = Query(None, description="Optional Filter DE oder AT")):
    """Schlanke Kennzahlen für HomePage/Übersichtskacheln.

    Liefert NUR Aggregatzahlen statt des vollen (~27 MB) Map-Payloads. Nutzt den
    Map-Cache, wenn er warm ist (exakte geocodierte Anzahl), sonst eine günstige
    Zeilensumme aus den Quellen-Metadaten — in beiden Fällen im Millisekunden-
    Bereich, ohne Geocoding-Aufbau.
    """
    cc = _normalize_country_code(country_code)
    with _MAP_CACHE_LOCK:
        hit = _MAP_CACHE.get(cc)
    if hit and (_time.time() - hit[0]) < _MAP_CACHE_TTL:
        payload = hit[1]
        return {
            "count": payload.get("count", 0),
            "source_count": len(payload.get("sources", [])),
            "cached": True,
        }
    sources = get_beneficiary_sources(country_code=cc)
    # Befund 5: Bei kaltem Cache NICHT SUM(row_count) der Legacy-Metadaten
    # nehmen — die enthält Header-Artefakt-/Duplikatzeilen und divergiert von
    # Karte/Suche. Stattdessen COUNT(*) der zentralen, deduplizierten Tabelle
    # workshop_beneficiary_records (konsistent zu search/Karten-Anzahl).
    from sqlalchemy import text as _text
    from database import engine as _engine

    where = "1=1"
    params: dict[str, str] = {}
    if cc:
        where = "country_code = :cc"
        params["cc"] = cc
    try:
        with _engine.connect() as conn:
            total = int(
                conn.execute(
                    _text(
                        f"SELECT COUNT(*) FROM workshop_beneficiary_records WHERE {where}"
                    ),
                    params,
                ).scalar()
                or 0
            )
    except Exception:  # noqa: BLE001 — Fallback auf Legacy-Summe
        log.exception("Summary-COUNT auf zentraler Tabelle fehlgeschlagen.")
        total = sum(int(s.get("row_count") or 0) for s in sources)
    return {"count": total, "source_count": len(sources), "cached": False}


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


# ── NUTS-GeoJSON ──────────────────────────────────────────────────────────────
# Liefert die Polygone fuer die Choropleth-Karte. DE: NUTS-1 (16 Bundeslaender),
# AT: NUTS-2 (9 Bundeslaender, in unserer Choropleth-API als "level=1" gefuehrt,
# weil AT auf NUTS-1 nur drei Grossregionen hat). Die Dateien sind aus dem
# Frontend (`public/state_aid/*.geojson`) uebernommen — siehe data/geo/.

import json as _json  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

_GEO_DIR = _Path(__file__).resolve().parent.parent / "data" / "geo"

_GEOJSON_PATHS: dict[tuple[str, int], _Path] = {
    ("DE", 1): _GEO_DIR / "nuts1_de.geojson",
    ("AT", 1): _GEO_DIR / "nuts1_at.geojson",
    ("DE", 3): _GEO_DIR / "nuts3_de.geojson",
    ("AT", 3): _GEO_DIR / "nuts3_at.geojson",
}


@router.get("/nuts-geojson")
def get_nuts_geojson(
    country_code: str = Query("DE", description="DE oder AT"),
    level: int = Query(1, ge=1, le=3, description="1 = Bundesland (NUTS-1/-2), 3 = Kreis (NUTS-3)"),
):
    """Liefert das NUTS-Polygon-GeoJSON fuer die Choropleth-Karte.

    Unterstuetzt: DE/AT auf Level 1 (NUTS-1/-2 Bundeslaender) und
    Level 3 (NUTS-3 Kreise/kreisfreie Staedte; Quelle: Eurostat
    GISCO NUTS-2021 1:10M, EPSG:4326).
    """
    cc = _normalize_country_code(country_code) or "DE"
    if cc not in {"DE", "AT"}:
        raise HTTPException(400, f"country_code '{cc}' wird nicht unterstuetzt.")
    if level not in {1, 3}:
        raise HTTPException(
            404,
            "GeoJSON nur fuer level=1 (Bundesland) oder level=3 (Kreis) verfuegbar.",
        )

    path = _GEOJSON_PATHS.get((cc, level))
    if not path or not path.exists():
        raise HTTPException(404, f"Kein GeoJSON fuer {cc} level={level} hinterlegt.")
    try:
        data = _json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.exception("GeoJSON-Datei nicht ladbar: %s", path)
        raise HTTPException(500, f"GeoJSON nicht ladbar: {exc}")
    return data


# ── Choropleth ────────────────────────────────────────────────────────────────
# Aggregiert die Beneficiary-Records auf NUTS-Ebene fuer Frontend-Karten.
# Datenquelle ist `analyze_beneficiary_records` (Mode region_project_counts /
# kreis_project_counts) — die Analytics-Pipeline liefert bereits Bundesland-
# bzw. NUTS-3-Aggregate, wir mappen sie hier nur in das Choropleth-Schema und
# ergaenzen NUTS-1-Codes pro Bundesland.

# DE-Bundesland → NUTS-1 (Original-Schreibweise wie in den Records).
_DE_BUNDESLAND_TO_NUTS1: dict[str, str] = {
    "Baden-Württemberg": "DE1", "Bayern": "DE2", "Berlin": "DE3",
    "Brandenburg": "DE4", "Bremen": "DE5", "Hamburg": "DE6",
    "Hessen": "DE7", "Mecklenburg-Vorpommern": "DE8",
    "Niedersachsen": "DE9", "Nordrhein-Westfalen": "DEA",
    "Rheinland-Pfalz": "DEB", "Saarland": "DEC",
    "Sachsen": "DED", "Sachsen-Anhalt": "DEE",
    "Schleswig-Holstein": "DEF", "Thüringen": "DEG",
}
# AT-Bundesland → NUTS-2 (als "Level 1" in der Choropleth-API, da AT auf
# NUTS-1 nur drei Grossregionen kennt — fuer eine Bundeslaender-Karte
# liefern wir die NUTS-2-Codes).
_AT_BUNDESLAND_TO_NUTS2: dict[str, str] = {
    "Burgenland": "AT11", "Niederösterreich": "AT12", "Wien": "AT13",
    "Kärnten": "AT21", "Steiermark": "AT22",
    "Oberösterreich": "AT31", "Salzburg": "AT32", "Tirol": "AT33",
    "Vorarlberg": "AT34",
}


def _format_choropleth_value(metric: str, value: float | int | None) -> str:
    """Formatiert den Wert als deutschen Label-String (analog Analytics-Schema)."""
    if value is None:
        return "k.A." if metric == "value" else "0"
    if metric == "value":
        return f"{float(value):,.0f}".replace(",", ".") + " €"
    return f"{int(value):,}".replace(",", ".") + " Vorhaben"


@router.get("/choropleth")
def get_choropleth(
    country_code: str = Query("DE", description="DE oder AT"),
    level: int = Query(1, ge=1, le=3, description="1 = Bundesland (NUTS-1/-2), 3 = Kreis (NUTS-3)"),
    metric: str = Query("count", description="count = Anzahl Vorhaben, value = Gesamtkosten"),
):
    """Aggregierte Werte pro NUTS-Region fuer eine Choropleth-Karte.

    Antwort-Schema:
    ``{country_code, level, metric, regions: [{nuts_code, name, value, value_label}],
       total, total_label, max_value}``

    Public — analog ``/api/beneficiaries/map`` ohne Auth, weil die Daten
    nach Art. 49/69 VO (EU) 2021/1060 oeffentlich sind.
    """
    cc = _normalize_country_code(country_code) or "DE"
    if cc not in {"DE", "AT"}:
        raise HTTPException(400, f"country_code '{cc}' wird nicht unterstuetzt.")
    if metric not in {"count", "value"}:
        raise HTTPException(400, "metric muss 'count' oder 'value' sein.")
    if level not in {1, 3}:
        raise HTTPException(400, "level muss 1 (Bundesland) oder 3 (Kreis) sein.")

    regions: list[dict] = []
    max_value: float = 0.0
    summary: dict | None = None

    if level == 1:
        # Level 1: Aggregation per NUTS-1 (DE) / NUTS-2 (AT) Prefix direkt
        # aus workshop_beneficiary_records. Der Prefix-Pfad ist robust auch
        # fuer Records ohne `bundesland`-Spalte (z.B. AT-Quellen liefern nur
        # NUTS-Code) — in DE deckt er die ~99 % gefuellten Records ab.
        from sqlalchemy import text  # local import: nur in diesem Pfad noetig
        from database import engine

        prefix_len = 3 if cc == "DE" else 4
        bl_to_nuts = (
            _DE_BUNDESLAND_TO_NUTS1 if cc == "DE" else _AT_BUNDESLAND_TO_NUTS2
        )
        nuts_to_name = {code: name for name, code in bl_to_nuts.items()}

        sql = text(
            """
            SELECT UPPER(LEFT(nuts_code, :pl)) AS prefix,
                   COUNT(*) AS cnt,
                   COALESCE(SUM(cost_total), 0) AS sum_cost
            FROM workshop_beneficiary_records
            WHERE country_code = :cc
              AND nuts_code IS NOT NULL AND nuts_code <> ''
            GROUP BY prefix
            """
        )
        # Befund 6: Records ohne (verwertbaren) NUTS-Code fallen aus der
        # Prefix-Aggregation. Ihre Anzahl im summary mitliefern, damit auf der
        # Karte transparent ist, wie viele Vorhaben „ohne Zuordnung" bleiben
        # (statt sie still zu verschlucken). Choropleth bleibt NUTS-Prefix-
        # basiert (kein Umbau auf bundesland-primär — sonst gingen AT-Quellen
        # ohne bundesland-Spalte verloren).
        discarded_sql = text(
            """
            SELECT COUNT(*) AS cnt
            FROM workshop_beneficiary_records
            WHERE country_code = :cc
              AND (nuts_code IS NULL OR nuts_code = ''
                   OR LENGTH(UPPER(LEFT(nuts_code, :pl))) <> :pl)
            """
        )
        with engine.connect() as conn:
            rows = conn.execute(sql, {"pl": prefix_len, "cc": cc}).fetchall()
            discarded_unmapped = int(
                conn.execute(discarded_sql, {"pl": prefix_len, "cc": cc}).scalar() or 0
            )

        for row in rows:
            r = dict(row._mapping)
            nuts_code = (r.get("prefix") or "").strip().upper()
            if not nuts_code or len(nuts_code) != prefix_len:
                continue
            count_value = int(r.get("cnt") or 0)
            cost_value = float(r.get("sum_cost") or 0.0)
            value: float = float(count_value) if metric == "count" else cost_value
            if value > max_value:
                max_value = value
            regions.append({
                "nuts_code": nuts_code,
                "name": nuts_to_name.get(nuts_code, nuts_code),
                "value": int(value) if metric == "count" else value,
                "value_label": _format_choropleth_value(metric, value),
                "project_count": count_value,
                "total_volume": cost_value,
                "bundesland": nuts_to_name.get(nuts_code, ""),
            })

        mapped_records = sum(int(r["project_count"] or 0) for r in regions)
        summary = {
            "records_mapped": mapped_records,
            "records_unmapped": discarded_unmapped,
            "records_total": mapped_records + discarded_unmapped,
            "note": (
                f"{discarded_unmapped} Vorhaben ohne NUTS-Zuordnung "
                "(nicht auf der Karte dargestellt)."
                if discarded_unmapped
                else "Alle Vorhaben sind einer Region zugeordnet."
            ),
        }

    else:  # level == 3 — Aggregation aus kreis_project_counts
        try:
            analytics = analyze_beneficiary_records(
                mode="kreis_project_counts",
                country_code=cc,
                limit=100,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        summary = analytics.get("summary")
        seen_codes: set[str] = set()
        for item in analytics.get("items", []):
            nuts_code = (item.get("nuts_code") or "").strip().upper()
            if not nuts_code or nuts_code in seen_codes:
                continue
            # Nur echte NUTS-3-Codes durchlassen. NUTS-3 ist 5-stellig
            # (DE: DEA11, AT: AT130). Der Backfill enthaelt teilweise auch
            # NUTS-1 (3-stellig) und NUTS-2 (4-stellig), die hier in Level=3
            # ausgeschlossen werden — sonst mischen sich die Granularitaeten
            # in der Choropleth.
            if len(nuts_code) != 5:
                continue
            seen_codes.add(nuts_code)
            label_raw = (item.get("label") or "").strip()
            # "Frankfurt am Main, Stadt (DE712)" → "Frankfurt am Main, Stadt"
            name = re.sub(r"\s*\([^)]*\)\s*$", "", label_raw) or nuts_code
            count_value = int(item.get("project_count") or 0)
            cost_value = float(item.get("total_volume") or 0.0)
            value = float(count_value) if metric == "count" else cost_value
            if value > max_value:
                max_value = value
            regions.append({
                "nuts_code": nuts_code,
                "name": name,
                "value": int(value) if metric == "count" else value,
                "value_label": _format_choropleth_value(metric, value),
                "project_count": count_value,
                "total_volume": cost_value,
                "bundesland": item.get("bundesland") or "",
            })

    regions.sort(key=lambda r: -float(r["value"] or 0))

    total: float = sum(float(r["value"] or 0) for r in regions)
    return {
        "country_code": cc,
        "level": level,
        "metric": metric,
        "regions": regions,
        "total": total if metric == "value" else int(total),
        "total_label": _format_choropleth_value(metric, total),
        "max_value": max_value if metric == "value" else int(max_value),
        "summary": summary,
    }


@router.delete("/{source}")
def delete_source(source: str, _session: dict = Depends(require_moderator)):
    """Begünstigtenverzeichnis entfernen."""
    delete_dataframe_table(source)
    invalidate_map_cache()
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
