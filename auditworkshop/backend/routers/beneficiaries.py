"""
flowworkshop · routers/beneficiaries.py
Begünstigtenverzeichnis: Upload → Auto-Erkennung → Geocoding → Karte.
Alles in einem Flow, kein manuelles Tagging nötig.
"""
import logging
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from services.geocoding_service import get_beneficiary_map_data, detect_columns
from services.dataframe_service import (
    ingest_dataframe, get_beneficiary_sources, delete_dataframe_table,
    _detect_metadata, _safe_table_name, search_beneficiary_records,
)

router = APIRouter(prefix="/api/beneficiaries", tags=["beneficiaries"])
log = logging.getLogger(__name__)


@router.post("/upload")
async def upload_beneficiary_list(file: UploadFile = File(...)):
    """
    Begünstigtenverzeichnis hochladen.
    - Erkennt automatisch Bundesland, Fonds, Förderperiode
    - Erstellt eindeutigen Source-Namen (z.B. 'hessen_efre_2021-2027')
    - Ersetzt Duplikate (gleiches Bundesland+Fonds+Periode)
    - Speichert als SQL-Tabelle + erkennt Standort-Spalten
    """
    if not file.filename:
        raise HTTPException(422, "Dateiname fehlt.")

    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(422, "Datei zu gross (max. 50 MB).")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ("xlsx", "xls", "xlsm"):
        raise HTTPException(422, "Nur XLSX/XLS-Dateien werden akzeptiert.")

    # 1. Metadaten erkennen
    metadata = _detect_metadata(content, ext, source=file.filename)
    bundesland = metadata.get("bundesland") or "unbekannt"
    fonds = (metadata.get("fonds") or "EFRE").lower()
    periode = metadata.get("periode") or ""

    # 2. Source-Name generieren (eindeutig pro Bundesland+Fonds+Periode)
    source = f"{bundesland.lower()}_{fonds}"
    if periode:
        source += f"_{periode.replace('-', '_')}"

    # 3. Prüfen ob Duplikat existiert
    existing = get_beneficiary_sources()
    replaced = False
    for ex in existing:
        if ex["bundesland"] == bundesland and ex["fonds"] == (metadata.get("fonds") or "EFRE"):
            if ex["periode"] == periode or (not ex["periode"] and not periode):
                # Duplikat → alte Tabelle löschen
                delete_dataframe_table(ex["source"])
                log.info("Duplikat ersetzt: %s → %s", ex["source"], source)
                replaced = True
                break

    # 4. Als DataFrame einlesen (smart header detection)
    # Versuche verschiedene Blätter (oft heißt das erste "Liste der Vorhaben" o.ä.)
    result = None
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
        except Exception:
            continue

    if not result or result["rows"] == 0:
        raise HTTPException(422, "Keine Daten erkannt. Prüfen Sie das Dateiformat.")

    # 5. Spalten-Erkennung für Karte
    cols = detect_columns(source)
    has_location = bool(cols.get("standort") or cols.get("ort") or cols.get("plz"))

    return {
        "status": "replaced" if replaced else "created",
        "source": source,
        "filename": file.filename,
        "metadata": {
            "bundesland": bundesland,
            "fonds": metadata.get("fonds") or "EFRE",
            "periode": periode,
        },
        "rows": result["rows"],
        "columns": result["columns"],
        "has_location": has_location,
        "columns_detected": cols,
    }


@router.get("/sources")
def list_sources():
    """Alle erkannten Begünstigtenverzeichnisse mit Metadaten."""
    return {"sources": get_beneficiary_sources()}


@router.get("/map")
def get_map_data():
    """
    Kartendaten für alle eingelesenen Begünstigtenverzeichnisse.
    Aggregiert automatisch alle Quellen.
    """
    sources = get_beneficiary_sources()
    all_beneficiaries = []
    sources_info = []

    for src in sources:
        data = get_beneficiary_map_data(src["source"])
        for b in data.get("beneficiaries", []):
            b["bundesland"] = src.get("bundesland") or src["source"]
            b["fonds"] = src.get("fonds") or ""
        all_beneficiaries.extend(data.get("beneficiaries", []))
        sources_info.append({
            "source": src["source"],
            "bundesland": src.get("bundesland"),
            "fonds": src.get("fonds"),
            "periode": src.get("periode"),
            "count": data.get("count", 0),
            "total_rows": src.get("row_count", 0),
        })

    return {
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
):
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
def delete_source(source: str):
    """Begünstigtenverzeichnis entfernen."""
    delete_dataframe_table(source)
    return {"status": "deleted", "source": source}
