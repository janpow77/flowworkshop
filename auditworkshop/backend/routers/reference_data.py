"""
flowworkshop · routers/reference_data.py
Lokaler Import und Suche fuer Referenzregister wie Sanktionslisten,
TAM, State Aid oder Cohesio.
"""
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from config import WORKSHOP_ADMIN
from services.dataframe_service import (
    delete_dataframe_table,
    ingest_dataframe,
    list_reference_registry_sources,
    search_reference_registry_records,
)
from services.geocoding_service import detect_columns

router = APIRouter(prefix="/api/reference-data", tags=["reference-data"])

ALLOWED_REGISTRY_TYPES = {"sanctions", "tam", "state_aid", "cohesio", "other"}


def _safe_source_name(value: str) -> str:
    import re

    return re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip().lower()).strip("_")


@router.post("/import")
async def import_reference_data(
    file: UploadFile = File(...),
    registry_type: str = Form(..., description="sanctions|tam|state_aid|cohesio|other"),
    source: str = Form("", description="Optionaler technischer Name"),
    sheet: str = Form("0", description="Blattname oder Index"),
):
    if not WORKSHOP_ADMIN:
        raise HTTPException(403, "Nicht freigeschaltet.")
    if not file.filename:
        raise HTTPException(422, "Dateiname fehlt.")
    if registry_type not in ALLOWED_REGISTRY_TYPES:
        raise HTTPException(422, f"Unbekannter Registertyp '{registry_type}'.")

    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(422, "Datei zu gross (max. 50 MB).")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ("xlsx", "xls", "xlsm", "csv"):
        raise HTTPException(422, "Nur XLSX/XLS/CSV-Dateien werden akzeptiert.")

    safe_source = _safe_source_name(source) if source else ""
    if not safe_source:
        filename_stub = _safe_source_name(file.filename.rsplit(".", 1)[0])
        safe_source = f"{registry_type}_{filename_stub or 'import'}"

    try:
        sheet_val: str | int = int(sheet) if sheet.isdigit() else sheet
        result = ingest_dataframe(
            content,
            file.filename,
            safe_source,
            sheet_val,
            dataset_group="reference_registry",
            registry_type=registry_type,
        )
    except Exception as exc:
        raise HTTPException(422, str(exc))

    return {
        **result,
        "source": safe_source,
        "registry_type": registry_type,
        "columns_detected": detect_columns(safe_source),
    }


@router.get("/sources")
def list_reference_sources():
    return {"sources": list_reference_registry_sources()}


@router.get("/search")
def search_reference_data(
    q: str = Query("", description="Suchbegriff fuer Unternehmen oder Vorhaben"),
    registry_type: str | None = Query(None, description="sanctions|tam|state_aid|cohesio|other"),
    source: str | None = Query(None),
    limit: int = Query(30, ge=1, le=100),
):
    if registry_type and registry_type not in ALLOWED_REGISTRY_TYPES:
        raise HTTPException(422, f"Unbekannter Registertyp '{registry_type}'.")
    return search_reference_registry_records(q, registry_type=registry_type, source=source, limit=limit)


@router.delete("/{source}")
def delete_reference_source(source: str):
    if not WORKSHOP_ADMIN:
        raise HTTPException(403, "Nicht freigeschaltet.")
    delete_dataframe_table(source)
    return {"status": "deleted", "source": source}
