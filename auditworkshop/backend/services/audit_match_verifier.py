"""LLM-Re-Ranker fuer ambivalente Cross-References im Audit-Report (Layer B).

Plan: Qwen3-14B prueft Match-Vorschlaege heuristisch ermittelter Querbezuege
und liefert ein strukturiertes JSON-Verdict (yes/no/unknown + confidence +
1-Satz-Begruendung). Das Verdict wird:
    1) als ``llm_verdict`` an die ``CrossReference.evidence`` gehaengt
    2) bei ``match=='no'`` als ``filtered_by_llm`` markiert (raw bleibt im
       Audit-Trail)
    3) im PDF in einer eigenen Sektion „LLM-Verifikation" sichtbar gemacht

Garantie: niemals halluzinieren — das LLM bewertet ausschliesslich die
uebergebenen Felder. Erfindet die JSON-Antwort nicht das vorgeschriebene
Format, gilt ``unknown`` als Default.

Latenz pro Verdict ~6-10s auf qwen3:14b (qwen3:8b deutlich schneller). Bei
Top-20 ambivalenten Cross-References = ~2-3 Min on-demand. Akzeptabel fuer
einen Pruefbericht-Aufruf, der nicht waehrend einer Live-Demo laeuft.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from services.ollama_service import stream as llm_stream

log = logging.getLogger(__name__)


# ── System-Prompt ────────────────────────────────────────────────────────────


VERIFY_SYSTEM_PROMPT = """Du pruefst, ob zwei Datensaetze denselben Akteur (Firma/Person) bezeichnen.
Antworte AUSSCHLIESSLICH als JSON-Block in dieser Form:
```json
{"match": "yes" | "no" | "unknown", "confidence": 0..100, "reason": "kurze Begruendung in einem Satz"}
```
Erfinde keine Daten. Bewerte nur, was uebergeben wurde.
match=yes nur, wenn Adresse/Identifier/Tochter-Beziehung dafuer sprechen.
match=unknown bei zu wenig Information.
match=no bei klaren Konflikten (anderes Land, andere Stadt, andere Branche).
"""


# Cross-Reference-Typen, fuer die eine LLM-Verifikation sinnvoll ist.
# Exakte Treffer (identifier_match, sa_reference_kom_case_linked) brauchen
# keine LLM-Ueberpruefung — sie sind per Definition deterministisch.
_VERIFIABLE_TYPES: frozenset[str] = frozenset({
    "name_match_state_aid_beneficiary",
    "address_match",
    "duplicate_award_within_year",
})


# ── Datenklassen ─────────────────────────────────────────────────────────────


@dataclass
class LlmMatchVerdict:
    """Ergebnis einer einzelnen Match-Verifikation durch das LLM."""
    cross_ref_index: int
    match: Literal["yes", "no", "unknown"]
    confidence: int                    # 0..100
    reason: str                        # 1 Satz Klartext
    elapsed_ms: int
    model_name: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


@dataclass
class LlmVerificationResult:
    """Aggregat ueber alle vom LLM verifizierten Cross-References."""
    total_input: int                   # Anzahl Cross-Refs an LLM gegeben
    verdicts: list[LlmMatchVerdict] = field(default_factory=list)
    elapsed_total_ms: int = 0
    skipped_due_to_timeout: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_input": self.total_input,
            "verdicts": [v.to_dict() for v in self.verdicts],
            "elapsed_total_ms": self.elapsed_total_ms,
            "skipped_due_to_timeout": self.skipped_due_to_timeout,
            "error": self.error,
        }


# ── JSON-Parser (drift-safe) ────────────────────────────────────────────────


def _extract_json_block(text: str) -> str | None:
    """Holt den JSON-Block aus einer LLM-Antwort.

    Bevorzugt einen Markdown-Codeblock mit Triple-Backticks; faellt zurueck
    auf den ersten ausgeglichenen ``{...}``-Match per Klammern-Balance.
    Identische Logik wie in services/state_aid_llm.py — bewusst dupliziert,
    damit dieses Modul standalone testbar bleibt.
    """
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        return fence.group(1)
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def _parse_verdict_payload(raw_text: str) -> dict[str, Any] | None:
    """Validiert und sanitisiert das LLM-JSON.

    Rueckgabe: ``{"match": "yes"|"no"|"unknown", "confidence": int 0..100,
    "reason": str}`` oder ``None`` bei nicht-parsbarer Antwort.
    """
    block = _extract_json_block(raw_text)
    if not block:
        return None
    try:
        obj = json.loads(block)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None

    # match
    match_raw = str(obj.get("match", "")).strip().lower()
    if match_raw not in {"yes", "no", "unknown"}:
        # Tolerant gegenueber Synonymen
        if match_raw in {"true", "ja", "y"}:
            match_raw = "yes"
        elif match_raw in {"false", "nein", "n"}:
            match_raw = "no"
        else:
            match_raw = "unknown"

    # confidence — auf 0..100 clampen
    try:
        confidence = int(round(float(obj.get("confidence", 0))))
    except (TypeError, ValueError):
        confidence = 0
    confidence = max(0, min(100, confidence))

    # reason — auf 240 Zeichen kuerzen
    reason = str(obj.get("reason") or "").strip().replace("\n", " ")
    if len(reason) > 240:
        reason = reason[:237] + "..."

    return {"match": match_raw, "confidence": confidence, "reason": reason}


# ── Score-Extraktion aus CrossReference.evidence ─────────────────────────────


def _extract_evidence_score(cross_ref: Any) -> float | None:
    """Liest den Aehnlichkeits-Score aus der Evidenz heraus.

    - ``address_match``                : ``evidence.name_similarity_score`` (0..100)
    - ``name_match_state_aid_beneficiary`` und ``duplicate_award_within_year``:
      kein Fuzzy-Score in der Evidenz, wir nehmen 80.0 als neutrales Default,
      damit auch diese Refs in der LLM-Pruefung erscheinen.

    Rueckgabe: float oder ``None`` bei nicht ueberpruefbaren Refs.
    """
    if cross_ref is None:
        return None
    cr_type = getattr(cross_ref, "type", None)
    if cr_type not in _VERIFIABLE_TYPES:
        return None

    evidence = getattr(cross_ref, "evidence", None) or {}
    if isinstance(evidence, dict):
        score = evidence.get("name_similarity_score")
        if isinstance(score, (int, float)):
            return float(score)

    # Fallback fuer Refs ohne Score in Evidenz: 80.0 = mittiges, ambivalentes Default
    if cr_type in {"name_match_state_aid_beneficiary", "duplicate_award_within_year"}:
        return 80.0

    return None


# ── LLM-Call Helpers ────────────────────────────────────────────────────────


async def _collect_llm_text(
    user_prompt: str,
    system_prompt: str,
    *,
    max_tokens: int,
    timeout_s: float,
    deterministic: bool = True,
) -> tuple[str, str | None]:
    """Sammelt einen LLM-Stream zu einem Text.

    Liefert ``(volltext, model_name)`` — ``model_name`` kann ``None`` sein,
    wenn kein ``done``-Frame eintraf.

    ``deterministic`` (Default True) erzwingt temperature=0 + fixen Seed, damit
    Verifikations-Verdicts ueber Re-Runs/Report-Laeufe reproduzierbar sind
    (Befund Entity-Resolution #6).
    """
    parts: list[str] = []
    model_name: str | None = None
    try:
        async with asyncio.timeout(timeout_s):
            async for sse_chunk in llm_stream(
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                documents=None,
                max_tokens=max_tokens,
                deterministic=deterministic,
            ):
                for line in sse_chunk.splitlines():
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if not data_str or data_str == "[DONE]":
                        continue
                    try:
                        obj = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("error"):
                        log.warning("Verifier-LLM-Fehler: %s", obj.get("error"))
                        continue
                    token = obj.get("token")
                    if token:
                        parts.append(token)
                    if obj.get("done"):
                        model_name = obj.get("model") or model_name
    except (TimeoutError, asyncio.TimeoutError):
        log.warning("Verifier-LLM Timeout nach %.1fs", timeout_s)
    return "".join(parts), model_name


def _format_record(label: str, record: dict[str, Any]) -> list[str]:
    """Formatiert einen Datensatz (Beneficiary oder State-Aid) als Klartext.

    Reihenfolge ist relevant — Schlussfolgerungen wie „anderes Land" sollen
    fuer das LLM offensichtlich sein.
    """
    if not record:
        return [f"{label}: (kein Datensatz)"]
    lines = [f"{label}:"]
    fields_in_order = [
        ("Name", record.get("name") or record.get("beneficiary_name")
         or record.get("company_name")),
        ("Identifier", record.get("identifier")
         or record.get("beneficiary_identifier")
         or record.get("aktenzeichen")),
        ("Land", record.get("country_code") or record.get("country")),
        ("NUTS-Code", record.get("nuts_code")),
        ("Bundesland", record.get("bundesland") or record.get("region")),
        ("Stadt/Adresse", record.get("location") or record.get("address")
         or record.get("nuts_label")),
        ("Vorhaben", record.get("project_name") or record.get("aid_measure_title")
         or record.get("aid_objective")),
        ("Behoerde", record.get("granting_authority")),
        ("Betrag (EUR)", record.get("aid_amount_eur") or record.get("kosten")),
        ("Quelle", record.get("source") or record.get("source_key")),
    ]
    for name, val in fields_in_order:
        if val is None or val == "":
            continue
        s = str(val)
        if len(s) > 160:
            s = s[:157] + "..."
        lines.append(f"  - {name}: {s}")
    return lines


def _build_user_prompt(record_a: dict[str, Any], record_b: dict[str, Any]) -> str:
    """Baut den User-Prompt fuer einen einzelnen Verifikations-Aufruf."""
    lines: list[str] = []
    lines.extend(_format_record("Datensatz A (State-Aid-Register)", record_a))
    lines.append("")
    lines.extend(_format_record("Datensatz B (Beguenstigtenverzeichnis)", record_b))
    lines.append("")
    lines.append(
        "Aufgabe: Bezeichnen A und B denselben Akteur? Antworte AUSSCHLIESSLICH "
        "als JSON-Block (siehe System-Anweisung)."
    )
    return "\n".join(lines)


# ── Public API: einzelner Match ──────────────────────────────────────────────


async def verify_match_pair(
    record_a: dict[str, Any],
    record_b: dict[str, Any],
    *,
    cross_ref_index: int = 0,
    timeout_s: float = 15.0,
) -> LlmMatchVerdict | None:
    """Eine einzige Match-Verifikation — ein LLM-Call.

    Liefert ``None`` bei vollstaendigem Timeout/Stream-Fehler — der Aufrufer
    entscheidet, das als ``unknown`` einzuhaengen oder zu skippen.
    """
    user_prompt = _build_user_prompt(record_a or {}, record_b or {})
    started = time.monotonic()
    raw_text, model_name = await _collect_llm_text(
        user_prompt,
        VERIFY_SYSTEM_PROMPT,
        max_tokens=200,
        timeout_s=timeout_s,
    )
    elapsed_ms = int((time.monotonic() - started) * 1000)

    parsed = _parse_verdict_payload(raw_text)
    if parsed is None:
        # JSON-Parse-Fehler oder leerer Stream → 'unknown'-Fallback
        if not raw_text:
            return None
        return LlmMatchVerdict(
            cross_ref_index=cross_ref_index,
            match="unknown",
            confidence=0,
            reason="LLM-Antwort nicht im erwarteten JSON-Format.",
            elapsed_ms=elapsed_ms,
            model_name=model_name or "",
        )
    return LlmMatchVerdict(
        cross_ref_index=cross_ref_index,
        match=parsed["match"],
        confidence=parsed["confidence"],
        reason=parsed["reason"],
        elapsed_ms=elapsed_ms,
        model_name=model_name or "",
    )


# ── Record-Extraktion aus CrossReference.evidence ───────────────────────────


def _extract_records_from_cross_ref(cross_ref: Any) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Liest die zwei Datensaetze (A,B) aus einer CrossReference.evidence aus.

    Mappt unterschiedliche Cross-Reference-Typen auf ein einheitliches
    Klartext-Schema fuer das LLM. Liefert ``None``, wenn die Evidenz nicht
    in das ``register_a/register_b``-Schema oder das Duplikat-Schema passt.
    """
    if cross_ref is None:
        return None
    evidence = getattr(cross_ref, "evidence", None) or {}
    if not isinstance(evidence, dict):
        return None

    cr_type = getattr(cross_ref, "type", None)

    # 1) Standard-Schema: register_a + register_b
    a_raw = evidence.get("register_a")
    b_raw = evidence.get("register_b")
    if isinstance(a_raw, dict) and isinstance(b_raw, dict):
        record_a = {
            "name": a_raw.get("value") or a_raw.get("context"),
            "identifier": a_raw.get("field") if a_raw.get("field") else None,
            "nuts_code": a_raw.get("nuts_code") or evidence.get("nuts_code"),
            "country_code": a_raw.get("country_code"),
            "source": a_raw.get("register"),
        }
        record_b = {
            "name": b_raw.get("value") or b_raw.get("context"),
            "identifier": b_raw.get("value") if b_raw.get("field") == "aktenzeichen" else None,
            "nuts_code": b_raw.get("nuts_code") or evidence.get("nuts_code"),
            "bundesland": b_raw.get("bundesland") or evidence.get("bundesland"),
            "country_code": b_raw.get("country_code"),
            "source": b_raw.get("register"),
        }
        return record_a, record_b

    # 2) Duplikat-Schema: ein Beguenstigter, mehrere Awards in 12 Mon.
    if cr_type == "duplicate_award_within_year":
        record_a = {
            "name": evidence.get("normalized_value"),
            "source": "state_aid",
        }
        record_b = {
            "name": evidence.get("normalized_value"),
            "source": "state_aid",
            "project_name": (
                f"{evidence.get('award_count', 0)} Vorhaben im Fenster "
                f"{evidence.get('window_start', '')} … "
                f"{evidence.get('window_end', '')}"
            ),
            "aid_amount_eur": evidence.get("total_amount_eur"),
        }
        return record_a, record_b

    return None


# ── Public API: Re-Rank von Cross-References ────────────────────────────────


async def verify_cross_references(
    cross_references: list[Any],
    *,
    score_min: float = 75.0,
    score_max: float = 89.0,
    max_to_verify: int = 20,
    overall_timeout_s: float = 240.0,
    per_call_timeout_s: float = 15.0,
) -> LlmVerificationResult:
    """Filtert ambivalente Cross-References und ruft das LLM Top-N mal auf.

    Filterung:
        - Nur Cross-Reference-Typen aus ``_VERIFIABLE_TYPES``
        - Score (aus ``evidence.name_similarity_score``) im Bereich
          ``[score_min, score_max]``
        - Maximal ``max_to_verify`` Refs

    Bei Erreichen von ``overall_timeout_s`` wird die Schleife gestoppt und
    bisher ermittelte Verdicts werden zurueckgegeben (``skipped_due_to_timeout``
    > 0). Pro LLM-Call wird zusaetzlich ``per_call_timeout_s`` als Schutz
    gegen einzelne haengende Streams gesetzt.

    Liefert immer ein ``LlmVerificationResult`` (auch bei 0 Eingaben).
    """
    started = time.monotonic()

    # 1) Filterung
    candidates: list[tuple[int, Any, float]] = []
    for idx, cr in enumerate(cross_references or []):
        score = _extract_evidence_score(cr)
        if score is None:
            continue
        if score < score_min or score > score_max:
            continue
        candidates.append((idx, cr, score))

    # Bei mehr als max_to_verify: niedrigste Scores zuerst (am ambivalentesten)
    candidates.sort(key=lambda t: t[2])
    candidates = candidates[:max_to_verify]

    result = LlmVerificationResult(total_input=len(candidates))
    if not candidates:
        result.elapsed_total_ms = int((time.monotonic() - started) * 1000)
        return result

    # 2) Sequentielle Verifikation (LLM-GPU ist single-tenant)
    deadline = started + overall_timeout_s
    for idx, cr, _score in candidates:
        # Globaler Timeout-Schutz
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            result.skipped_due_to_timeout = len(candidates) - len(result.verdicts)
            log.warning(
                "Verifier-Overall-Timeout: %d von %d Cross-Refs uebersprungen.",
                result.skipped_due_to_timeout, len(candidates),
            )
            break

        records = _extract_records_from_cross_ref(cr)
        if records is None:
            continue
        record_a, record_b = records

        try:
            call_timeout = min(per_call_timeout_s, max(2.0, remaining))
            verdict = await verify_match_pair(
                record_a, record_b,
                cross_ref_index=idx,
                timeout_s=call_timeout,
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("Verifier-Call fehlgeschlagen (idx=%d): %s", idx, exc)
            verdict = LlmMatchVerdict(
                cross_ref_index=idx,
                match="unknown",
                confidence=0,
                reason=f"LLM-Aufruf fehlgeschlagen: {exc}",
                elapsed_ms=0,
                model_name="",
            )

        if verdict is not None:
            result.verdicts.append(verdict)

    result.elapsed_total_ms = int((time.monotonic() - started) * 1000)
    return result


# ── DB-Logging ───────────────────────────────────────────────────────────────


def log_verdict_to_db(
    *,
    cross_ref: Any,
    verdict: LlmMatchVerdict,
    user_id: str | None = None,
) -> None:
    """Persistiert ein Verdict in ``LlmQuestionLog`` (Audit-Trail).

    Best-Effort, non-blocking — Fehler werden geloggt, aber niemals geworfen.
    Plan v3.2 §16.4: scenario=99 (Sentinel "kein Workshop-Szenario"),
    matched_mode='audit_match_verify'.
    """
    try:
        from database import SessionLocal
        from models.automation import LlmQuestionLog

        records = _extract_records_from_cross_ref(cross_ref)
        if records:
            record_a, record_b = records
            prompt = _build_user_prompt(record_a, record_b)
        else:
            prompt = "(Cross-Reference ohne extrahierbare Records)"

        excerpt = json.dumps(
            {
                "match": verdict.match,
                "confidence": verdict.confidence,
                "reason": verdict.reason,
                "cross_ref_type": getattr(cross_ref, "type", None),
                "cross_ref_index": verdict.cross_ref_index,
            },
            ensure_ascii=False,
        )[:500]

        normalized = " ".join(prompt.lower().split())[:480]

        # tok_per_s schaetzen — wir kennen Tokens nicht, also als None lassen
        db_log = SessionLocal()
        try:
            db_log.add(LlmQuestionLog(
                user_id=user_id,
                scenario=99,
                prompt=prompt[:4000],
                prompt_normalized=normalized,
                answer_path="audit_match_verify",
                matched_mode="audit_match_verify",
                items_returned=1,
                model_name=verdict.model_name or "audit-match-verify",
                elapsed_ms=verdict.elapsed_ms,
                response_excerpt=excerpt,
                response_total_chars=len(excerpt),
            ))
            db_log.commit()
        finally:
            db_log.close()
    except Exception:  # noqa: BLE001
        log.exception(
            "LLM-Logging audit_match_verify fehlgeschlagen (non-blocking)",
        )
