"""
flowworkshop · routers/checklist_translate.py

LLM-Uebersetzungs-Mechanik (EN→DE) fuer KOM-Checklisten-Knoten.

Reine Inhalts-/Seeding-Mechanik: uebersetzt englischsprachige Knoten-Titel
(``ChecklistTemplateNode.title``) ins Deutsche und sichert das Original in
``source_text_en`` (sofern dort noch nichts steht). KEIN Review-Workflow, KEINE
Status-/Sprachfeld-UI — die Uebersetzungs-Statusfelder des Modells bleiben hier
bewusst ungenutzt.

Bewusst eigenstaendig (eigener Router, lokale Pydantic-Schemas, lokaler
Rechte-Helfer), damit weder ``main.py`` noch ``routers/checklist_templates.py``
angefasst werden muessen. Die Registrierung erfolgt manuell in ``main.py``
(siehe Zusammenfassung am Ende der Implementierung).

Der LLM-Aufruf laeuft ueber ``services.ollama_service.stream`` (egpu-gateway
bzw. Ollama). Dieser Backend kann zur Laufzeit „degraded" sein; jeder Fehler
wird sauber abgefangen. Pro Knoten ein eigener LLM-Call — ein fehlgeschlagener
Knoten bricht den Gesamtlauf NICHT ab, sondern wird im Ergebnis als Fehler
ausgewiesen. Ist das LLM-Backend gar nicht erreichbar, antwortet der Endpunkt
mit HTTP 503 statt zu crashen.
"""
import json
import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models.checklist_template import (
    ChecklistMember,
    ChecklistTemplate,
    ChecklistTemplateNode,
    MemberRole,
)
from routers.auth import require_session
from services import ollama_service

router = APIRouter(
    prefix="/api/checklist-templates",
    tags=["checklist-templates", "translate"],
    dependencies=[Depends(require_session)],
)
log = logging.getLogger(__name__)


# ── System-Prompt fuer die Uebersetzung ───────────────────────────────────────

_TRANSLATE_SYSTEM_PROMPT = (
    "Du bist ein Fachuebersetzer fuer EFRE-Pruefchecklisten. Uebersetze den "
    "folgenden EFRE-Pruefchecklisten-Text praezise und in Behoerdensprache ins "
    "Deutsche. Gib NUR die Uebersetzung zurueck — keine Anmerkungen, keine "
    "Anfuehrungszeichen, keine Erklaerungen."
)

# Knappes Token-Budget — Knoten-Titel sind kurze Saetze, kein Fliesstext.
_TRANSLATE_MAX_TOKENS = 512


# ── Rollen-Rangfolge (lokaler Helfer, NICHT aus checklist_templates importiert) ─
# Hoeherer Rang = mehr Rechte. viewer < commenter < editor < owner.
_ROLE_RANK = {
    MemberRole.VIEWER.value: 1,
    MemberRole.COMMENTER.value: 2,
    MemberRole.EDITOR.value: 3,
    MemberRole.OWNER.value: 4,
}


def _utcnow() -> datetime:
    """Naive UTC-Zeit (konsistent mit den tz-losen DateTime-Spalten)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _session_user_id(session: dict) -> str:
    """Liest die Nutzerkennung aus der Session oder wirft 401."""
    uid = session.get("user_id")
    if not uid:
        raise HTTPException(401, "Sitzung ohne Nutzerkennung.")
    return uid


def _require_role(
    template_id: str, user_id: str, min_role: MemberRole, db: Session,
) -> ChecklistMember:
    """Stellt sicher, dass ``user_id`` am Template mindestens ``min_role`` hat.

    Wirft 404, wenn das Template nicht existiert, 403, wenn der Nutzer kein
    Mitglied ist oder seine Rolle nicht ausreicht. Gibt die Mitgliedschaft
    zurueck. Bewusst lokal gehalten (kein Import aus checklist_templates.py).
    """
    template = (
        db.query(ChecklistTemplate)
        .filter(ChecklistTemplate.id == template_id)
        .first()
    )
    if not template:
        raise HTTPException(404, "Checklisten-Template nicht gefunden.")
    member = (
        db.query(ChecklistMember)
        .filter(
            ChecklistMember.template_id == template_id,
            ChecklistMember.user_id == user_id,
        )
        .first()
    )
    if not member:
        raise HTTPException(403, "Kein Zugriff auf dieses Checklisten-Template.")
    have = _ROLE_RANK.get(member.role, 0)
    need = _ROLE_RANK.get(min_role.value, 99)
    if have < need:
        raise HTTPException(
            403,
            f"Unzureichende Berechtigung — erforderlich: {min_role.value}, "
            f"vorhanden: {member.role}.",
        )
    return member


# ── Heuristik: ist ein Titel englischsprachig? ────────────────────────────────

# Haeufige englische Funktionswoerter, die in deutschem Behoerdentext fehlen.
_EN_MARKERS = {
    "the", "and", "or", "of", "to", "in", "is", "are", "was", "were", "be",
    "has", "have", "with", "for", "that", "this", "which", "shall", "must",
    "should", "been", "by", "as", "an", "on", "at", "from", "whether",
    "documents", "evidence", "verification", "audit", "expenditure",
    "compliance", "eligible", "eligibility", "checklist", "question",
}
# Deutsche Marker (Umlaute/ß und typische Funktionswoerter) → wohl schon Deutsch.
_DE_MARKERS = {
    "der", "die", "das", "und", "oder", "wurde", "wurden", "ist", "sind",
    "nicht", "fuer", "mit", "auf", "wird", "werden", "gemaess", "ob", "eine",
    "einen", "einer", "den", "dem", "des", "vorhaben", "beleg", "belege",
    "pruefung", "foerderung", "nachweis", "zuwendung",
}
_WORD_RE = re.compile(r"[a-zäöüß]+", re.IGNORECASE)


def _looks_english(text: str | None) -> bool:
    """Heuristische EN-Erkennung fuer kurze Checklisten-Titel.

    Konservativ: enthaelt der Text echte Umlaute/ß oder deutlich mehr deutsche
    als englische Funktionswoerter, gilt er als (bereits) deutsch und wird NICHT
    uebersetzt. Ueberwiegen englische Marker, gilt er als englisch.
    """
    if not text or not text.strip():
        return False
    # Echte Umlaute/ß sind ein starkes Deutsch-Signal.
    if re.search(r"[äöüÄÖÜß]", text):
        return False

    words = [w.lower() for w in _WORD_RE.findall(text)]
    if not words:
        return False

    en_hits = sum(1 for w in words if w in _EN_MARKERS)
    de_hits = sum(1 for w in words if w in _DE_MARKERS)

    if de_hits > en_hits:
        return False
    # Mindestens ein englischer Funktionswort-Treffer und kein deutsches
    # Uebergewicht → als englisch behandeln.
    return en_hits > 0


# ── LLM-Aufruf: nicht-streamender Wrapper um ollama_service.stream ────────────

class _LlmUnavailable(RuntimeError):
    """LLM-Backend nicht erreichbar / degraded — fuehrt zu HTTP 503."""


async def _translate_text(text: str) -> str:
    """Uebersetzt ``text`` EN→DE ueber das LLM und liefert reinen Text.

    Konsumiert den SSE-Stream aus ``ollama_service.stream`` und setzt die
    Token zu einem String zusammen. Erkennt das ``error``- bzw. ``done``-Event
    des SSE-Protokolls. Bei Backend-Fehler oder leerer Antwort wird eine
    Exception geworfen; ``_LlmUnavailable`` signalisiert ein nicht erreichbares
    Backend (→ 503 im Endpunkt).
    """
    collected: list[str] = []
    error_msg: str | None = None

    try:
        async for line in ollama_service.stream(
            user_prompt=text,
            system_prompt=_TRANSLATE_SYSTEM_PROMPT,
            documents=None,
            max_tokens=_TRANSLATE_MAX_TOKENS,
        ):
            # SSE-Zeilen der Form 'data: {...}\n\n'
            line = line.strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                continue

            if event.get("error"):
                error_msg = str(event["error"])
                break
            token = event.get("token")
            if token:
                collected.append(token)
    except Exception as exc:  # noqa: BLE001 — Backend-Aufruf darf nicht crashen
        raise _LlmUnavailable(f"LLM-Aufruf fehlgeschlagen: {exc}") from exc

    if error_msg:
        # Typische „degraded"-Signale → als nicht erreichbar werten.
        lowered = error_msg.lower()
        if any(
            marker in lowered
            for marker in ("timeout", "connect", "unavailable", "503", "502",
                           "refused", "no healthy", "degraded")
        ):
            raise _LlmUnavailable(error_msg)
        raise RuntimeError(error_msg)

    result = "".join(collected).strip()
    if not result:
        raise _LlmUnavailable("LLM lieferte keine Antwort (leerer Stream).")
    return result


# ── Pydantic-Schemas (lokal) ──────────────────────────────────────────────────

class TranslateRequest(BaseModel):
    """Optionaler Request-Body fuer die Bulk-Uebersetzung.

    ``node_ids`` schraenkt auf bestimmte Knoten ein; ist es leer/nicht gesetzt,
    werden alle englischsprachigen Knoten des Templates uebersetzt."""
    node_ids: list[str] | None = Field(
        default=None,
        description="Optionale Auswahl von Knoten-IDs; sonst alle EN-Knoten.",
    )


class TranslatedNodeOut(BaseModel):
    """Ergebnis eines uebersetzten (oder fehlgeschlagenen) Knotens."""
    id: str
    source_text_en: str | None = None
    title: str | None = None
    ok: bool
    error: str | None = None


class TranslateResultOut(BaseModel):
    """Bulk-Ergebnis: Zaehler + die betroffenen Knoten."""
    template_id: str
    translated_count: int
    skipped_count: int
    failed_count: int
    nodes: list[TranslatedNodeOut]


# ── Gemeinsame Uebersetzungs-Logik fuer einen Knoten ──────────────────────────

async def _translate_node(
    node: ChecklistTemplateNode, db: Session, *, llm_model: str | None,
) -> TranslatedNodeOut:
    """Uebersetzt einen einzelnen Knoten-Titel und persistiert das Ergebnis.

    Sichert das Original in ``source_text_en`` (nur falls dort noch nichts
    steht) und schreibt die deutsche Uebersetzung sowohl nach ``title`` als auch
    nach ``translated_text_de``. Wirft ``_LlmUnavailable`` nach oben, damit der
    Endpunkt eine globale 503-Antwort geben kann; andere Fehler werden als
    fehlgeschlagener Knoten zurueckgegeben (kein Abbruch des Gesamtlaufs).
    """
    original = (node.title or "").strip()
    german = await _translate_text(original)  # _LlmUnavailable propagiert

    if not node.source_text_en:
        node.source_text_en = original
    node.title = german
    node.translated_text_de = german
    if llm_model:
        node.llm_model = llm_model[:80]
    node.translated_at = _utcnow()
    db.flush()
    return TranslatedNodeOut(
        id=node.id,
        source_text_en=node.source_text_en,
        title=node.title,
        ok=True,
    )


# ── Endpunkte ─────────────────────────────────────────────────────────────────

@router.post("/{template_id}/translate", response_model=TranslateResultOut)
async def translate_template_nodes(
    template_id: str,
    request: Request,
    data: TranslateRequest | None = None,
    db: Session = Depends(get_db),
):
    """Uebersetzt alle englischsprachigen Knoten eines Templates ins Deutsche.

    Rechte: mindestens editor. Optionaler Body ``{node_ids: [...]}`` schraenkt
    auf bestimmte Knoten ein, sonst werden alle Knoten betrachtet, deren Titel
    englischsprachig erscheint (Heuristik ``_looks_english``). Pro Knoten ein
    LLM-Call; ein fehlgeschlagener Knoten bricht den Lauf nicht ab. Ist das
    LLM-Backend nicht erreichbar, antwortet der Endpunkt mit HTTP 503.
    """
    session = require_session(request)
    user_id = _session_user_id(session)
    _require_role(template_id, user_id, MemberRole.EDITOR, db)

    requested_ids = set(data.node_ids) if data and data.node_ids else None

    query = db.query(ChecklistTemplateNode).filter(
        ChecklistTemplateNode.template_id == template_id
    )
    if requested_ids:
        query = query.filter(ChecklistTemplateNode.id.in_(requested_ids))
    nodes = query.order_by(ChecklistTemplateNode.sort_order).all()

    # Modellname best-effort fuer die Ablage (rein informativ).
    llm_model = None
    try:
        status = await ollama_service.check_ollama()
        models = status.get("models") if isinstance(status, dict) else None
        if models:
            llm_model = models[0]
    except Exception:  # noqa: BLE001 — rein informativ, nie blockierend
        llm_model = None

    results: list[TranslatedNodeOut] = []
    translated = skipped = failed = 0

    for node in nodes:
        if not _looks_english(node.title):
            skipped += 1
            continue
        try:
            out = await _translate_node(node, db, llm_model=llm_model)
            results.append(out)
            translated += 1
        except _LlmUnavailable as exc:
            # Backend ist generell nicht erreichbar — abbrechen und 503 geben.
            db.rollback()
            log.warning(
                "Uebersetzung abgebrochen — LLM-Backend nicht erreichbar: %s",
                exc,
            )
            raise HTTPException(
                503,
                "Das Uebersetzungs-Backend (LLM) ist derzeit nicht erreichbar. "
                "Bitte spaeter erneut versuchen.",
            ) from exc
        except Exception as exc:  # noqa: BLE001 — Einzelfehler nicht fatal
            failed += 1
            log.warning("Knoten %s konnte nicht uebersetzt werden: %s", node.id, exc)
            results.append(TranslatedNodeOut(
                id=node.id,
                source_text_en=node.source_text_en,
                title=node.title,
                ok=False,
                error=str(exc),
            ))

    db.commit()
    log.info(
        "Template %s: %d uebersetzt, %d uebersprungen, %d fehlgeschlagen (durch %s)",
        template_id, translated, skipped, failed, user_id,
    )
    return TranslateResultOut(
        template_id=template_id,
        translated_count=translated,
        skipped_count=skipped,
        failed_count=failed,
        nodes=results,
    )


@router.post(
    "/{template_id}/nodes/{node_id}/translate",
    response_model=TranslatedNodeOut,
)
async def translate_single_node(
    template_id: str,
    node_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Uebersetzt einen einzelnen Knoten-Titel EN→DE (mindestens editor).

    Anders als beim Bulk-Lauf wird hier nicht auf die EN-Heuristik gefiltert —
    ein gezielter Einzelaufruf uebersetzt den angegebenen Knoten in jedem Fall
    (sofern ein Titel vorhanden ist). Ist das LLM-Backend nicht erreichbar,
    antwortet der Endpunkt mit HTTP 503.
    """
    session = require_session(request)
    user_id = _session_user_id(session)
    _require_role(template_id, user_id, MemberRole.EDITOR, db)

    node = (
        db.query(ChecklistTemplateNode)
        .filter(
            ChecklistTemplateNode.id == node_id,
            ChecklistTemplateNode.template_id == template_id,
        )
        .first()
    )
    if not node:
        raise HTTPException(404, "Knoten nicht gefunden.")
    if not (node.title or "").strip():
        raise HTTPException(422, "Der Knoten hat keinen uebersetzbaren Titel.")

    llm_model = None
    try:
        status = await ollama_service.check_ollama()
        models = status.get("models") if isinstance(status, dict) else None
        if models:
            llm_model = models[0]
    except Exception:  # noqa: BLE001
        llm_model = None

    try:
        out = await _translate_node(node, db, llm_model=llm_model)
    except _LlmUnavailable as exc:
        db.rollback()
        log.warning("Einzel-Uebersetzung fehlgeschlagen (Backend): %s", exc)
        raise HTTPException(
            503,
            "Das Uebersetzungs-Backend (LLM) ist derzeit nicht erreichbar. "
            "Bitte spaeter erneut versuchen.",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        log.warning("Knoten %s konnte nicht uebersetzt werden: %s", node_id, exc)
        raise HTTPException(
            500, f"Uebersetzung fehlgeschlagen: {exc}"
        ) from exc

    db.commit()
    log.info("Knoten %s uebersetzt (durch %s)", node_id, user_id)
    return out
