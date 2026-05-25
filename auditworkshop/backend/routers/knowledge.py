"""
flowworkshop · routers/knowledge.py
Endpunkte für die RAG-Wissensdatenbank (pgvector).

GET  /api/knowledge/stats
GET  /api/knowledge/search?q=...&top_k=5&source=...
POST /api/knowledge/ingest        — Datei hochladen (nur WORKSHOP_ADMIN)
DELETE /api/knowledge/source/{source}  — Quelle entfernen (nur WORKSHOP_ADMIN)
"""
import json

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from config import (
    WORKSHOP_ADMIN,
    KB_RESEARCH_MODEL,
    KB_RESEARCH_TOP_K,
    KB_RESEARCH_SYSTEM_PROMPT,
)
from services import knowledge_service as ks
from services.file_parser import extract
from services.ollama_service import stream
from routers.auth import require_moderator, require_session

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

# Laengen-Steuerung der Generierung → Token-Budget.
# Hoch angesetzt, weil qwen3.5:35b-fast ein Reasoning-Modell ist und ~1500-1900
# Tokens fuer den (separat gestreamten) Thinking-Block verbraucht, BEVOR Content
# kommt. Zu kleine Budgets → 0 Content-Tokens. Das Budget deckt Reasoning + Antwort.
_LENGTH_TOKENS = {"kurz": 2200, "mittel": 3200, "lang": 4200}
# Textart → Instruktion, die an den Basis-System-Prompt angehaengt wird.
_TEXT_TYPE_HINTS = {
    "analyse": "Erstelle eine strukturierte Analyse mit nummerierten Kernpunkten.",
    "zusammenfassung": "Fasse die Antwort knapp und präzise in wenigen Sätzen zusammen.",
    "stellungnahme": "Formuliere eine sachliche Stellungnahme mit Begründung.",
    "vermerk": "Formuliere einen behördlichen Vermerk (Sachverhalt, Bewertung, Ergebnis).",
    "pruefbericht": "Formuliere eine Berichtspassage im Stil eines Prüfberichts.",
}


class KbGenerateRequest(BaseModel):
    query: str = Field(..., min_length=3, description="Frage / Thema")
    text_type: str = Field("analyse", description="analyse|zusammenfassung|stellungnahme|vermerk|pruefbericht")
    length: str = Field("mittel", description="kurz|mittel|lang")
    source: str | None = Field(None, description="Nur diese Quelle als Kontext nutzen")


@router.get("/stats")
def get_stats(_session: dict = Depends(require_session)):
    """Anzahl Dokumente und Chunks in der Wissensdatenbank."""
    return ks.stats()


@router.get("/search")
def search(
    q: str = Query(..., min_length=3, description="Suchanfrage"),
    top_k: int = Query(5, ge=1, le=20),
    source: str | None = Query(None, description="Nur diese Quelle durchsuchen"),
    _session: dict = Depends(require_session),
):
    """Semantische Ähnlichkeitssuche in den gespeicherten Chunks."""
    results = ks.search(q, top_k=top_k, source_filter=source)
    return {"query": q, "results": results}


@router.post("/generate")
async def generate(req: KbGenerateRequest, _session: dict = Depends(require_session)):
    """
    Belegbasierte Textgenerierung über die Wissensbasis.

    Holt RAG-Kontext via pgvector und streamt eine Antwort des stärkeren
    Reasoning-Modells (qwen3.5:35b) über das Gateway/den ai-router
    (Route ``qwen3.5:* → evo-x2``). Streamt als Server-Sent-Events:

      data: {"sources": [...]}                 — einmalig zu Beginn
      data: {"token": "...", "done": false}    — Antwort-Tokens
      data: {"done": true, "model": "...", ...} — Abschluss
    """
    hits = ks.search(req.query, top_k=KB_RESEARCH_TOP_K, source_filter=req.source)

    sources = [
        {
            "source": h["source"],
            "filename": h.get("filename"),
            "chunk_index": h["chunk_index"],
            "score": h["score"],
            "snippet": (h["text"][:280] + "…") if len(h["text"]) > 280 else h["text"],
        }
        for h in hits
    ]

    documents = [
        f"[{h['source']} · Abschnitt {h['chunk_index'] + 1}]\n{h['text']}"
        for h in hits
    ]

    hint = _TEXT_TYPE_HINTS.get(req.text_type, _TEXT_TYPE_HINTS["analyse"])
    system_prompt = f"{KB_RESEARCH_SYSTEM_PROMPT}\n\n{hint}"
    max_tokens = _LENGTH_TOKENS.get(req.length, _LENGTH_TOKENS["mittel"])

    async def event_generator():
        yield f"data: {json.dumps({'sources': sources}, ensure_ascii=False)}\n\n"
        async for chunk in stream(
            req.query,
            system_prompt,
            documents,
            max_tokens=max_tokens,
            model_override=KB_RESEARCH_MODEL,
        ):
            yield chunk

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/ingest")
async def ingest_document(
    file: UploadFile = File(...),
    source: str = Form(..., description="Logischer Name, z. B. 'foerderbescheid_musterstadt'"),
    _session: dict = Depends(require_session),
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
    _session: dict = Depends(require_session),
):
    """Gibt die Chunks einer Quelle paginiert zurueck (fuer Transparenz-Ansicht)."""
    chunks = ks.get_chunks(source, offset=offset, limit=limit)
    return chunks


@router.delete("/source/{source}")
def delete_source(source: str, _session: dict = Depends(require_moderator)):
    """Entfernt alle Chunks einer Quelle aus der Wissensdatenbank."""
    if not WORKSHOP_ADMIN:
        raise HTTPException(status_code=403, detail="Nicht freigeschaltet.")
    deleted = ks.delete_source(source)
    return {"deleted_chunks": deleted, "source": source}
