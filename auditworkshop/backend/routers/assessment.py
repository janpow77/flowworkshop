"""
flowworkshop · routers/assessment.py
KI-Bewertung: Bemerkungen generieren, akzeptieren, ablehnen, bearbeiten.
"""
import json
import logging
import re
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from models.checklist import WorkshopQuestion, WorkshopEvidence, RemarkAiStatus
from schemas.checklist import RejectFeedbackIn, EditRemarkIn
from services import knowledge_service as ks
from services.ollama_service import stream as ollama_stream
from config import SYSTEM_PROMPTS, DISCLAIMER

router = APIRouter(prefix="/api/assessment", tags=["assessment"])
log = logging.getLogger(__name__)


def _clean_llm_json(text: str) -> str:
    """Entfernt Markdown-Codebloecke um JSON-Antworten des LLM.

    LLMs wrappen JSON haeufig in ```json ... ``` Bloecke.
    Diese Funktion entfernt solche Wrapper und gibt den reinen Text zurueck.
    """
    text = re.sub(r"^```(?:json)?\s*\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n?```\s*$", "", text, flags=re.MULTILINE)
    return text.strip()


def _parse_llm_json(text: str) -> dict | list | None:
    """Versucht JSON aus einer LLM-Antwort zu parsen, auch mit Markdown-Wrapping."""
    cleaned = _clean_llm_json(text)
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        log.warning("LLM-JSON konnte nicht geparst werden: %s...", cleaned[:200])
        return None

ASSESS_SYSTEM_PROMPT = """Du bist ein Hilfswerkzeug fuer EFRE-Pruefer.
Beurteile den folgenden Pruefpunkt auf Basis der beigefuegten Dokumente.
Gib deine Antwort als JSON zurueck:
{
  "status": "erfuellt | nicht_erfuellt | nicht_beurteilbar",
  "begruendung": "Ausfuehrliche Begruendung mit Quellenverweisen.",
  "fundstellen": ["Quelle 1, Absatz X", "Quelle 2, S. Y"]
}
Erfinde keine Informationen. Wenn keine ausreichenden Unterlagen vorliegen,
setze den Status auf "nicht_beurteilbar" und begruende warum."""


def _get_question(question_id: str, db: Session) -> WorkshopQuestion:
    q = db.query(WorkshopQuestion).filter(WorkshopQuestion.id == question_id).first()
    if not q:
        raise HTTPException(404, "Frage nicht gefunden.")
    return q


@router.post("/questions/{question_id}/assess")
async def assess_question(question_id: str, db: Session = Depends(get_db)):
    """KI-Bemerkung fuer eine einzelne Frage generieren (SSE-Stream)."""
    q = _get_question(question_id, db)
    question_id_value = q.id

    # RAG-Suche
    search_text = f"{q.question_text or ''} {q.category or ''}"
    hits = ks.search(search_text.strip(), top_k=3)

    docs = []
    if hits:
        rag_context = "\n\n".join(
            f"[{h['source']} · Chunk {h['chunk_index']}]\n{h['text']}"
            for h in hits
        )
        docs.append(rag_context)

    # Projekt-Metadaten laden
    checklist = q.checklist
    project = checklist.project if checklist else None
    project_context = ""
    if project:
        project_context = (
            f"\nProjekt: {project.projekttitel or project.aktenzeichen}"
            f"\nFoerderphase: {project.foerderphase.value if project.foerderphase else 'k.A.'}"
            f"\nZuwendungsempfaenger: {project.zuwendungsempfaenger or 'k.A.'}"
        )

    user_prompt = (
        f"Pruefpunkt {q.question_key}: {q.question_text or ''}"
        f"\nKategorie: {q.category or 'Allgemein'}"
        f"\nAntworttyp: {q.answer_type.value if q.answer_type else 'boolean'}"
        f"{project_context}"
        f"\n\n---\n{DISCLAIMER}"
    )

    accumulated = []

    async def event_generator():
        async for chunk in ollama_stream(user_prompt, ASSESS_SYSTEM_PROMPT, docs):
            yield chunk
            # Token aus SSE extrahieren
            if chunk.startswith("data: "):
                try:
                    data = json.loads(chunk[6:].strip())
                    token = data.get("token", "")
                    if token:
                        accumulated.append(token)
                except (json.JSONDecodeError, ValueError):
                    pass

        # Nach dem Stream: Ergebnis in DB speichern
        full_response = "".join(accumulated)
        if full_response:
            with SessionLocal() as save_db:
                q_db = (
                    save_db.query(WorkshopQuestion)
                    .filter(WorkshopQuestion.id == question_id_value)
                    .first()
                )
                if q_db:
                    q_db.remark_ai = full_response
                    q_db.remark_ai_status = RemarkAiStatus.DRAFT
                    q_db.evidence.clear()

                    # Evidence-Eintraege aus RAG-Hits erstellen
                    for h in hits:
                        ev = WorkshopEvidence(
                            question_id=q_db.id,
                            source_name=h["source"],
                            filename=h["filename"],
                            location=f"Chunk {h['chunk_index']}",
                            snippet=h["text"][:500],
                            score=h["score"],
                        )
                        save_db.add(ev)

                    save_db.commit()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/checklists/{checklist_id}/assess-all")
async def assess_all(checklist_id: str, db: Session = Depends(get_db)):
    """Alle Fragen einer Checkliste bewerten (SSE-Stream mit Fortschritt)."""
    from models.checklist import WorkshopChecklist

    cl = db.query(WorkshopChecklist).filter(WorkshopChecklist.id == checklist_id).first()
    if not cl:
        raise HTTPException(404, "Checkliste nicht gefunden.")

    questions = [q for q in cl.questions if q.remark_ai_status is None]
    total = len(questions)

    async def event_generator():
        for idx, q in enumerate(questions):
            # Fortschritt melden
            progress = json.dumps({
                "type": "progress",
                "current": idx + 1,
                "total": total,
                "question_key": q.question_key,
            })
            yield f"data: {progress}\n\n"

            # RAG-Suche
            search_text = f"{q.question_text or ''} {q.category or ''}"
            hits = ks.search(search_text.strip(), top_k=3)
            docs = []
            if hits:
                rag_context = "\n\n".join(
                    f"[{h['source']} · Chunk {h['chunk_index']}]\n{h['text']}"
                    for h in hits
                )
                docs.append(rag_context)

            user_prompt = (
                f"Pruefpunkt {q.question_key}: {q.question_text or ''}"
                f"\nKategorie: {q.category or 'Allgemein'}"
                f"\n\n---\n{DISCLAIMER}"
            )

            # LLM-Antwort sammeln (nicht streamen, nur Ergebnis)
            accumulated = []
            async for chunk in ollama_stream(user_prompt, ASSESS_SYSTEM_PROMPT, docs):
                if chunk.startswith("data: "):
                    try:
                        data = json.loads(chunk[6:].strip())
                        token = data.get("token", "")
                        if token:
                            accumulated.append(token)
                    except (json.JSONDecodeError, ValueError):
                        pass

            full_response = "".join(accumulated)
            if full_response:
                q.remark_ai = full_response
                q.remark_ai_status = RemarkAiStatus.DRAFT
                q.evidence.clear()

                for h in hits:
                    ev = WorkshopEvidence(
                        question_id=q.id,
                        source_name=h["source"],
                        filename=h["filename"],
                        location=f"Chunk {h['chunk_index']}",
                        snippet=h["text"][:500],
                        score=h["score"],
                    )
                    db.add(ev)

                db.commit()

            result = json.dumps({
                "type": "result",
                "question_id": q.id,
                "question_key": q.question_key,
                "status": "done",
            })
            yield f"data: {result}\n\n"

        yield f"data: {json.dumps({'type': 'complete', 'assessed': total})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.put("/questions/{question_id}/accept")
def accept_remark(question_id: str, db: Session = Depends(get_db)):
    q = _get_question(question_id, db)
    if not q.remark_ai:
        raise HTTPException(400, "Keine KI-Bemerkung vorhanden.")
    q.remark_ai_status = RemarkAiStatus.ACCEPTED
    db.commit()
    return {"status": "accepted"}


@router.put("/questions/{question_id}/reject")
def reject_remark(
    question_id: str, body: RejectFeedbackIn | None = None, db: Session = Depends(get_db),
):
    q = _get_question(question_id, db)
    if not q.remark_ai:
        raise HTTPException(400, "Keine KI-Bemerkung vorhanden.")
    q.remark_ai_status = RemarkAiStatus.REJECTED
    if body and body.feedback:
        q.reject_feedback = body.feedback
    db.commit()
    return {"status": "rejected", "feedback_saved": bool(body and body.feedback)}


@router.put("/questions/{question_id}/edit")
def edit_remark(question_id: str, body: EditRemarkIn, db: Session = Depends(get_db)):
    q = _get_question(question_id, db)
    q.remark_ai_edited = body.remark_text
    q.remark_ai_status = RemarkAiStatus.EDITED
    db.commit()
    return {"status": "edited", "remark_ai_edited": body.remark_text}
