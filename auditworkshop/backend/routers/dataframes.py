"""
flowworkshop · routers/dataframes.py
API fuer DataFrame-Tabellen (XLSX/CSV → SQL).
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query
from services.dataframe_service import (
    ingest_dataframe, query_dataframe, get_table_info,
    get_summary_stats, list_dataframe_tables, delete_dataframe_table,
)
from config import WORKSHOP_ADMIN

router = APIRouter(prefix="/api/dataframes", tags=["dataframes"])


@router.get("/")
def list_tables():
    """Alle DataFrame-Tabellen auflisten."""
    return {"tables": list_dataframe_tables()}


@router.post("/ingest")
async def ingest(
    file: UploadFile = File(...),
    source: str = Form(..., description="Logischer Name, z.B. 'transparenzliste_hessen'"),
    sheet: str = Form("0", description="Blattname oder Index (default: 0)"),
):
    """XLSX/CSV als SQL-Tabelle speichern."""
    if not WORKSHOP_ADMIN:
        raise HTTPException(403, "Nicht freigeschaltet.")
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(422, "Datei zu gross (max. 50 MB).")
    try:
        sheet_val: str | int = int(sheet) if sheet.isdigit() else sheet
        result = ingest_dataframe(content, file.filename or "unknown.xlsx", source, sheet_val)
    except Exception as e:
        raise HTTPException(422, str(e))
    return result


@router.get("/{source}/info")
def table_info(source: str):
    """Schema und Statistiken einer DataFrame-Tabelle."""
    info = get_table_info(source)
    if not info.get("exists"):
        raise HTTPException(404, f"Tabelle '{source}' nicht gefunden.")
    return info


@router.get("/{source}/summary")
def table_summary(source: str):
    """Menschenlesbare Zusammenfassung (fuer LLM-Kontext)."""
    summary = get_summary_stats(source)
    return {"source": source, "summary": summary}


@router.get("/{source}/query")
def query_table(
    source: str,
    sql: str = Query(..., description="SELECT-Query mit {table} als Platzhalter"),
):
    """SQL-Query auf DataFrame-Tabelle ausfuehren (nur SELECT)."""
    try:
        rows = query_dataframe(source, sql)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"source": source, "rows": rows, "count": len(rows)}


@router.delete("/{source}")
def delete_table(source: str):
    """DataFrame-Tabelle loeschen."""
    if not WORKSHOP_ADMIN:
        raise HTTPException(403, "Nicht freigeschaltet.")
    delete_dataframe_table(source)
    return {"status": "deleted", "source": source}
