"""
flowworkshop · routers/knowledge.py
Endpunkte für die RAG-Wissensdatenbank (pgvector).

GET  /api/knowledge/stats
GET  /api/knowledge/search?q=...&top_k=5&source=...
POST /api/knowledge/ingest        — Datei hochladen (nur WORKSHOP_ADMIN)
DELETE /api/knowledge/source/{source}  — Quelle entfernen (nur WORKSHOP_ADMIN)
"""
import json
import re

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from config import (
    WORKSHOP_ADMIN,
    KB_RESEARCH_MODEL,
    KB_RESEARCH_REASONING_EFFORT,
    KB_RESEARCH_TOP_K,
    KB_RESEARCH_SYSTEM_PROMPT,
    KB_RERANK_ENABLED,
    KB_RERANK_POOL,
    KB_RERANK_THRESHOLD,
    KB_SOURCE_GROUPS,
    KB_DEFAULT_SOURCE,
)
from services import knowledge_service as ks
from services.file_parser import extract
from services.ollama_service import stream
from routers.auth import require_moderator, require_session

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


def _resolve_source(source: str | None) -> str | list[str] | None:
    """Loest einen Quellen-Parameter auf: Gruppenname → Quellen-Liste,
    Einzelquelle → str, leer/None → None (alle Quellen)."""
    if not source:
        return None
    if source in KB_SOURCE_GROUPS:
        return KB_SOURCE_GROUPS[source]
    return source

# Laengen-Steuerung der Generierung → Token-Budget.
# Seit der Umstellung auf qwen3:14b mit reasoning_effort="none" (siehe config.py)
# entfaellt der frueher noetige grosse Puffer fuer den Thinking-Block — das Budget
# deckt nur noch die reine Antwort. Werte bleiben grosszuegig, damit lange
# Berichtspassagen nicht abgeschnitten werden.
_LENGTH_TOKENS = {"kurz": 220, "mittel": 700, "lang": 1500}

# Max. Zeichen je Fundstelle, die als Kontext ins LLM gehen. Statt des vollen
# Chunks (~5.300 Zeichen) nur ein Fenster um die Trefferstelle → drastisch
# weniger Prefill-Tokens → schnelleres erstes Token. Die vollstaendige Fundstelle
# bleibt ueber die Quellen-Anzeige (Snippet + Abschnitt) nachvollziehbar.
_CONTEXT_CHARS = 1400


def _focus_window(text: str, query: str, max_chars: int = _CONTEXT_CHARS) -> str:
    """Schneidet ein Fenster um die beste Query-Trefferstelle aus dem Chunk."""
    if len(text) <= max_chars:
        return text
    terms = [w for w in re.split(r"\W+", query.lower()) if len(w) >= 4]
    low = text.lower()
    pos = next((low.find(w) for w in terms if low.find(w) != -1), -1)
    if pos == -1:
        return text[:max_chars].rstrip() + " …"
    half = max_chars // 2
    start, end = max(0, pos - half), min(len(text), pos + half)
    out = text[start:end].strip()
    if start > 0:
        out = "… " + out
    if end < len(text):
        out = out + " …"
    return out
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


@router.get("/groups")
def get_groups(_session: dict = Depends(require_session)):
    """Quellen-Gruppen + Standard-Auswahl fuer das Recherche-Dropdown."""
    return {"groups": KB_SOURCE_GROUPS, "default_source": KB_DEFAULT_SOURCE}


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
    results = ks.search(q, top_k=top_k, source_filter=_resolve_source(source))
    return {"query": q, "results": results}


@router.post("/generate")
async def generate(req: KbGenerateRequest, _session: dict = Depends(require_session)):
    """
    Belegbasierte Textgenerierung über die Wissensbasis.

    Holt RAG-Kontext via pgvector und streamt eine belegbasierte Antwort
    (Modell ``KB_RESEARCH_MODEL``, Default qwen3:14b mit reasoning_effort="none")
    über das Gateway/den ai-router. Streamt als Server-Sent-Events:

      data: {"sources": [...]}                 — einmalig zu Beginn
      data: {"token": "...", "done": false}    — Antwort-Tokens
      data: {"done": true, "model": "...", ...} — Abschluss
    """
    # Reranking: grob KB_RERANK_POOL Treffer holen, per Cross-Encoder auf die
    # besten KB_RESEARCH_TOP_K sortieren (loest die „Artikel 74"-Kollision
    # VO/AI-Act domaenenneutral). Fallback in rerank() auf Vektor-Reihenfolge.
    if KB_RERANK_ENABLED:
        pool = ks.search(req.query, top_k=KB_RERANK_POOL, source_filter=_resolve_source(req.source))
        hits = ks.rerank(req.query, pool, top_k=KB_RESEARCH_TOP_K, threshold=KB_RERANK_THRESHOLD)
    else:
        hits = ks.search(req.query, top_k=KB_RESEARCH_TOP_K, source_filter=_resolve_source(req.source))

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
        f"[{h['source']} · Abschnitt {h['chunk_index'] + 1}]\n{_focus_window(h['text'], req.query)}"
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
            reasoning_effort=KB_RESEARCH_REASONING_EFFORT,
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
