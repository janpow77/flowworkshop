"""
flowworkshop · routers/workshop.py
Streaming-Endpunkt für alle sechs Workshop-Szenarien + PDF-Parse-Endpunkt.
"""
import asyncio
import json
import logging
import re
import time
from collections import defaultdict

from fastapi import APIRouter, UploadFile, File, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from config import SYSTEM_PROMPTS, DISCLAIMER
from services import knowledge_service as ks
from services.dataframe_service import (
    build_beneficiary_analysis_answer,
    get_beneficiary_llm_context,
)
from services.ollama_service import stream
from services.file_parser import extract as file_extract, ALLOWED_EXTENSIONS

router = APIRouter(prefix="/api/workshop", tags=["workshop"])
log = logging.getLogger(__name__)


# ── Rate-Limiting (In-Memory, 10 Requests/Minute pro IP) ────────────────────
_rate_limit: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_MAX = 10
RATE_LIMIT_WINDOW = 60  # Sekunden


def _check_rate_limit(client_ip: str) -> None:
    """Prueft ob die IP das Rate-Limit ueberschritten hat."""
    now = time.monotonic()
    timestamps = _rate_limit[client_ip]
    # Alte Eintraege entfernen
    _rate_limit[client_ip] = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW]
    if len(_rate_limit[client_ip]) >= RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=429,
            detail=f"Zu viele Anfragen. Maximal {RATE_LIMIT_MAX} LLM-Aufrufe pro Minute.",
        )
    _rate_limit[client_ip].append(now)


def _chunk_text_for_sse(text: str, chunk_size: int = 56) -> list[str]:
    parts = re.findall(r"\S+\s*|\n", text)
    if not parts:
        return [text] if text else []

    chunks: list[str] = []
    current = ""
    for part in parts:
        if current and len(current) + len(part) > chunk_size and not part.endswith("\n"):
            chunks.append(current)
            current = part
            continue
        current += part
        if part.endswith("\n"):
            chunks.append(current)
            current = ""

    if current:
        chunks.append(current)
    return chunks


async def _stream_static_response(text: str, model: str) -> StreamingResponse:
    async def event_generator():
        chunks = _chunk_text_for_sse(text)
        for chunk in chunks:
            yield f"data: {json.dumps({'token': chunk, 'done': False})}\n\n"
            await asyncio.sleep(0)
        yield (
            "data: "
            + json.dumps(
                {
                    "done": True,
                    "token_count": len(chunks),
                    "model": model,
                    "elapsed_s": 0.0,
                    "tok_per_s": 0.0,
                }
            )
            + "\n\n"
        )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _build_extract_response(hits: list[dict]) -> str:
    cleaned_hits = sorted(
        hits,
        key=lambda hit: (
            0 if str(hit.get("text", "")).strip()[:1].isupper() else 1,
            -float(hit.get("score") or 0.0),
            int(hit.get("chunk_index") or 0),
        ),
    )
    uppercase_hits = [
        hit for hit in cleaned_hits
        if str(hit.get("text", "")).strip()[:1].isupper()
    ]
    if uppercase_hits:
        cleaned_hits = uppercase_hits

    lines = ["Relevante Fundstellen aus den geladenen Dokumenten:"]
    for idx, hit in enumerate(cleaned_hits[:2], start=1):
        excerpt = re.sub(r"\s+", " ", str(hit.get("text") or "")).strip()
        excerpt = excerpt[:420]
        if excerpt and not excerpt.endswith("."):
            excerpt += " …"
        lines.append(
            f"{idx}. [{hit['source']} · Abschnitt {hit['chunk_index'] + 1}] {excerpt}"
        )
    lines.append(
        "Die Antwort wird hier direkt aus den gefundenen Fundstellen wiedergegeben. "
        "Wenn der Ausschnitt unvollständig wirkt, sollte der Volltext geprüft werden."
    )
    return "\n".join(lines)


class StreamRequest(BaseModel):
    scenario: int = Field(..., ge=1, le=6)
    prompt: str = Field(..., min_length=1, max_length=2000)
    documents: list[str] = Field(default_factory=list, max_length=5)
    with_context: bool = True   # Szenario 3: Kontext an/aus
    demo_doc: str | None = None  # Name des Demo-Dokuments (wird serverseitig geladen)


SCENARIO_MAX_TOKENS = {
    1: 320,
    2: 260,
    3: 180,
    4: 320,
    5: 220,
    6: 180,
}


@router.post("/stream")
async def workshop_stream(req: StreamRequest, request: Request):
    """
    Streamt eine LLM-Antwort als Server-Sent-Events.

    SSE-Format:
      data: {"token": "...", "done": false}
      data: {"done": true, "token_count": N, "model": "...", "tok_per_s": N}
      data: {"error": "...", "done": true}
    """
    _check_rate_limit(request.client.host if request.client else "unknown")

    # System-Prompt auswählen
    if req.scenario == 3:
        key = "3_mit" if req.with_context else "3_ohne"
    else:
        key = req.scenario
    system_prompt = SYSTEM_PROMPTS.get(key, SYSTEM_PROMPTS[1])

    # Dokumente zusammenstellen
    docs = list(req.documents)

    # Szenario 3 mit Kontext: RAG-Retrieval aus pgvector
    article_prompt = bool(re.search(r"[Aa]rt(?:ikel)?\.?\s*\d+", req.prompt))

    if req.scenario == 3 and req.with_context:
        try:
            hits = ks.search(req.prompt, top_k=3 if article_prompt else 2)
            if article_prompt and hits:
                return await _stream_static_response(
                    _build_extract_response(hits),
                    "knowledge-extract",
                )
            rag_context = "\n\n".join(
                f"[{h['source']} · Abschnitt {h['chunk_index'] + 1}]\n{h['text'][:650 if article_prompt else 850]}"
                for h in hits
            )
            if rag_context:
                docs.insert(0, rag_context)
        except Exception:
            log.exception("RAG-Kontext fuer Szenario 3 fehlgeschlagen.")

    # Szenario 5: RAG-Retrieval auf Vorab-Upload-Dokumente
    if req.scenario == 5 and req.with_context:
        try:
            hits = ks.search(req.prompt, top_k=3 if article_prompt else 2)
            if article_prompt and hits:
                return await _stream_static_response(
                    _build_extract_response(hits),
                    "knowledge-extract",
                )
            rag_context = "\n\n".join(
                f"[{h['source']} · S. {h['chunk_index'] + 1}]\n{h['text'][:650 if article_prompt else 850]}"
                for h in hits
            )
            if rag_context:
                docs.insert(0, rag_context)
        except Exception:
            log.exception("RAG-Kontext fuer Szenario 5 fehlgeschlagen.")

    if req.scenario == 6:
        direct_answer = build_beneficiary_analysis_answer(req.prompt, limit=5)
        if direct_answer:
            return await _stream_static_response(direct_answer, "beneficiary-analytics")
        beneficiary_context = get_beneficiary_llm_context(req.prompt, max_entries_per_source=4)
        if beneficiary_context:
            docs.insert(0, beneficiary_context)

    # Disclaimer ans Ende des Prompts
    full_prompt = f"{req.prompt}\n\n---\n{DISCLAIMER}"

    async def event_generator():
        async for chunk in stream(
            full_prompt,
            system_prompt,
            docs,
            max_tokens=SCENARIO_MAX_TOKENS.get(req.scenario),
        ):
            yield chunk

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/parse-file")
async def parse_file(file: UploadFile = File(...)):
    """
    Extrahiert Text aus einer Datei (PDF, XLSX, DOCX, HTML, RTF, TXT).
    Dokument wird NICHT in der Knowledge-DB gespeichert.
    """
    if not file.filename:
        raise HTTPException(422, "Dateiname fehlt.")
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(422, "Datei zu gross (max. 50 MB).")
    try:
        parsed = file_extract(content, file.filename)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if not parsed["text"]:
        raise HTTPException(422, f"Kein Text extrahierbar: {parsed['warnings']}")
    return {
        "text": parsed["text"],
        "filename": file.filename,
        "pages": parsed["pages"],
        "char_count": parsed["char_count"],
        "method": parsed["method"],
        "warnings": parsed["warnings"],
    }


@router.get("/supported-formats")
def supported_formats():
    """Gibt die unterstuetzten Dateiformate zurueck."""
    return {"extensions": sorted(ALLOWED_EXTENSIONS)}
