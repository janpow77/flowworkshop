"""
flowworkshop · routers/knowledge.py
Endpunkte für die RAG-Wissensdatenbank (pgvector).

GET  /api/knowledge/stats
GET  /api/knowledge/search?q=...&top_k=5&source=...
POST /api/knowledge/ingest        — Datei hochladen (nur WORKSHOP_ADMIN)
DELETE /api/knowledge/source/{source}  — Quelle entfernen (nur WORKSHOP_ADMIN)
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query

from config import WORKSHOP_ADMIN
from services import knowledge_service as ks
from services.file_parser import extract

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("/stats")
def get_stats():
    """Anzahl Dokumente und Chunks in der Wissensdatenbank."""
    return ks.stats()


@router.get("/search")
def search(
    q: str = Query(..., min_length=3, description="Suchanfrage"),
    top_k: int = Query(5, ge=1, le=20),
    source: str | None = Query(None, description="Nur diese Quelle durchsuchen"),
):
    """Semantische Ähnlichkeitssuche in den gespeicherten Chunks."""
    results = ks.search(q, top_k=top_k, source_filter=source)
    return {"query": q, "results": results}


@router.post("/ingest")
async def ingest_document(
    file: UploadFile = File(...),
    source: str = Form(..., description="Logischer Name, z. B. 'foerderbescheid_musterstadt'"),
):
    """
    Liest eine Datei ein, extrahiert den Text und speichert Chunks in pgvector.
    Unterstuetzt: PDF, XLSX, XLS, XLSM, DOCX, DOCM, HTML, RTF, TXT.
    Nur verfuegbar wenn WORKSHOP_ADMIN=true.
    Idempotent: erneuter Ingest derselben Quelle ueberschreibt bestehende Chunks.
    """
    if not WORKSHOP_ADMIN:
        raise HTTPException(status_code=403, detail="Ingest-Endpunkt nicht freigeschaltet.")

    if not file.filename:
        raise HTTPException(status_code=422, detail="Dateiname fehlt.")

    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="Datei zu gross (max. 50 MB).")

    try:
        parsed = extract(content, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if not parsed["text"]:
        raise HTTPException(status_code=422,
                            detail=f"Kein Text extrahierbar. Warnungen: {parsed['warnings']}")

    result = ks.ingest(parsed["text"], source=source, filename=file.filename)

    return {
        **result,
        "pages": parsed["pages"],
        "char_count": parsed["char_count"],
        "method": parsed["method"],
        "warnings": parsed["warnings"],
        "total_in_db": ks.stats(),
    }


@router.get("/source/{source}/chunks")
def get_source_chunks(
    source: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    """Gibt die Chunks einer Quelle paginiert zurueck (fuer Transparenz-Ansicht)."""
    chunks = ks.get_chunks(source, offset=offset, limit=limit)
    return chunks


@router.delete("/source/{source}")
def delete_source(source: str):
    """Entfernt alle Chunks einer Quelle aus der Wissensdatenbank."""
    if not WORKSHOP_ADMIN:
        raise HTTPException(status_code=403, detail="Nicht freigeschaltet.")
    deleted = ks.delete_source(source)
    return {"deleted_chunks": deleted, "source": source}
