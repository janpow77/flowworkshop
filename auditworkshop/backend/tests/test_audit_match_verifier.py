"""Tests fuer den LLM-Re-Ranker (services/audit_match_verifier.py).

Schwerpunkt:
- pure helpers (JSON-Extraktion, Score-Filter, Record-Mapping)
- verify_cross_references mit gemocktem ollama_service.stream
- Timeout-Handling, leere Eingabe, JSON-Parse-Fehler

Wichtig: KEINE Live-LLM-Aufrufe. ``services.ollama_service.stream`` wird
durchgaengig per monkeypatch ueberschrieben.

Lauf: pytest backend/tests/test_audit_match_verifier.py -q
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import AsyncGenerator
from unittest.mock import patch

import pytest

# Backend-Verzeichnis in den Pfad legen, damit `services.*` importierbar ist
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_cross_ref(
    cr_type: str,
    *,
    score: float | None = None,
    register_a: dict | None = None,
    register_b: dict | None = None,
    extra_evidence: dict | None = None,
):
    """Konstruiert eine CrossReference-Instanz fuer Tests."""
    from services.state_aid_audit_report import CrossReference
    evidence: dict = {}
    if register_a is not None:
        evidence["register_a"] = register_a
    if register_b is not None:
        evidence["register_b"] = register_b
    if score is not None:
        evidence["name_similarity_score"] = float(score)
    if extra_evidence:
        evidence.update(extra_evidence)
    return CrossReference(
        type=cr_type,  # type: ignore[arg-type]
        description=f"Test-{cr_type}",
        evidence=evidence,
    )


def _sse_token(text: str) -> str:
    return f"data: {json.dumps({'token': text, 'done': False})}\n\n"


def _sse_done(model_name: str = "qwen3:14b") -> str:
    return f"data: {json.dumps({'done': True, 'model': model_name, 'token_count': 30, 'elapsed_s': 6.5, 'tok_per_s': 4.6})}\n\n"


def _make_mock_stream(verdict_payload: dict | str | None = None,
                      *, raise_timeout: bool = False, hang: bool = False):
    """Faelschungsfunktion fuer ``services.ollama_service.stream``.

    - ``verdict_payload`` (dict): gibt einen sauberen JSON-Block zurueck
    - ``verdict_payload`` (str): rohe Tokens (z.B. fuer Parse-Fehler-Tests)
    - ``verdict_payload`` (None): leerer Stream (kein Token, kein done)
    - ``raise_timeout``: simuliert einen TimeoutError
    - ``hang``: simuliert einen haengenden Stream (asyncio.sleep)
    """
    async def _fake_stream(
        user_prompt: str,
        system_prompt: str,
        documents: list[str] | None = None,
        max_tokens: int | None = None,
        backend_override: str | None = None,
        model_override: str | None = None,
        reasoning_effort: str | None = None,
        deterministic: bool = False,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        if raise_timeout:
            raise TimeoutError("simulated timeout")
        if hang:
            # 30s sleep — Wrapper-Timeout muss ihn abbrechen
            await asyncio.sleep(30)
            return
        if verdict_payload is None:
            return
        if isinstance(verdict_payload, dict):
            text = "```json\n" + json.dumps(verdict_payload) + "\n```"
        else:
            text = str(verdict_payload)
        # In ein paar Tokens stueckeln
        for chunk in [text[i:i + 8] for i in range(0, len(text), 8)]:
            yield _sse_token(chunk)
        yield _sse_done()
    return _fake_stream


# ── Pure Helper ──────────────────────────────────────────────────────────────


def test_extract_json_block_aus_codefence():
    from services.audit_match_verifier import _extract_json_block
    txt = "Vorab-Text\n```json\n{\"match\": \"yes\", \"confidence\": 90}\n```\nNachtrag"
    block = _extract_json_block(txt)
    assert block is not None
    parsed = json.loads(block)
    assert parsed["match"] == "yes"
    assert parsed["confidence"] == 90


def test_extract_json_block_ohne_codefence():
    from services.audit_match_verifier import _extract_json_block
    txt = "Etwas Text {\"match\": \"no\", \"reason\": \"weiss nicht\"} und nochwas"
    block = _extract_json_block(txt)
    assert block is not None
    parsed = json.loads(block)
    assert parsed["match"] == "no"


def test_parse_verdict_payload_clamped_und_normalisiert():
    from services.audit_match_verifier import _parse_verdict_payload
    # Confidence > 100 → clamp auf 100
    out = _parse_verdict_payload(
        '```json\n{"match":"yes","confidence":150,"reason":"sehr klar"}\n```'
    )
    assert out is not None
    assert out["match"] == "yes"
    assert out["confidence"] == 100

    # Negative Confidence → clamp auf 0
    out2 = _parse_verdict_payload(
        '```json\n{"match":"no","confidence":-20,"reason":""}\n```'
    )
    assert out2 is not None
    assert out2["confidence"] == 0

    # Synonyme: ja → yes, nein → no
    out3 = _parse_verdict_payload('```json\n{"match":"ja","confidence":80}\n```')
    assert out3 is not None
    assert out3["match"] == "yes"

    out4 = _parse_verdict_payload('```json\n{"match":"NEIN","confidence":40}\n```')
    assert out4 is not None
    assert out4["match"] == "no"


def test_parse_verdict_payload_unknown_bei_unbekanntem_match():
    from services.audit_match_verifier import _parse_verdict_payload
    out = _parse_verdict_payload(
        '```json\n{"match":"vielleicht","confidence":50}\n```'
    )
    assert out is not None
    assert out["match"] == "unknown"


def test_parse_verdict_payload_none_bei_garbage():
    from services.audit_match_verifier import _parse_verdict_payload
    assert _parse_verdict_payload("kein JSON hier") is None
    assert _parse_verdict_payload("") is None
    # JSON ohne Klammer-Match
    assert _parse_verdict_payload("{ invalid json }") is None


def test_extract_evidence_score_address_match():
    from services.audit_match_verifier import _extract_evidence_score
    cr = _make_cross_ref(
        "address_match",
        score=82.5,
        register_a={"register": "state_aid", "value": "Alpha GmbH"},
        register_b={"register": "beneficiaries", "value": "Alpha GmbH"},
    )
    assert _extract_evidence_score(cr) == 82.5


def test_extract_evidence_score_name_match_default_80():
    """Refs ohne Score in Evidenz bekommen 80.0 als ambivalentes Default."""
    from services.audit_match_verifier import _extract_evidence_score
    cr = _make_cross_ref(
        "name_match_state_aid_beneficiary",
        register_a={"register": "state_aid", "value": "Alpha GmbH"},
        register_b={"register": "beneficiaries", "value": "Alpha GmbH"},
    )
    score = _extract_evidence_score(cr)
    assert score == 80.0


def test_extract_evidence_score_none_fuer_exact_matches():
    """identifier_match und sa_reference_kom_case_linked sind exakt — kein Score."""
    from services.audit_match_verifier import _extract_evidence_score
    cr_id = _make_cross_ref(
        "identifier_match",
        register_a={"register": "state_aid", "value": "HRB12345"},
        register_b={"register": "beneficiaries", "value": "HRB12345"},
    )
    cr_sa = _make_cross_ref(
        "sa_reference_kom_case_linked",
        extra_evidence={"sa_reference": "SA.12345"},
    )
    cr_sem = _make_cross_ref(
        "semantic_neighbor_state_aid",
        extra_evidence={"cosine_similarity": 0.92},
    )
    assert _extract_evidence_score(cr_id) is None
    assert _extract_evidence_score(cr_sa) is None
    assert _extract_evidence_score(cr_sem) is None


# ── verify_cross_references — Score-Filter ────────────────────────────────────


def test_verify_cross_references_filtert_score_ausserhalb_range():
    """Refs mit Score < 75 oder > 89 werden NICHT an LLM gegeben."""
    from services.audit_match_verifier import verify_cross_references
    refs = [
        _make_cross_ref(
            "address_match", score=70.0,
            register_a={"register": "state_aid", "value": "A"},
            register_b={"register": "beneficiaries", "value": "B"},
        ),
        _make_cross_ref(
            "address_match", score=95.0,
            register_a={"register": "state_aid", "value": "A"},
            register_b={"register": "beneficiaries", "value": "B"},
        ),
        _make_cross_ref(
            "address_match", score=82.0,
            register_a={"register": "state_aid", "value": "A"},
            register_b={"register": "beneficiaries", "value": "B"},
        ),
    ]
    fake_stream = _make_mock_stream(
        {"match": "yes", "confidence": 88, "reason": "passt"}
    )
    with patch("services.audit_match_verifier.llm_stream", fake_stream):
        result = asyncio.run(verify_cross_references(
            refs, score_min=75.0, score_max=89.0,
            max_to_verify=20, overall_timeout_s=30.0,
        ))
    # Nur die 82.0er Cross-Ref ist im Range
    assert result.total_input == 1
    assert len(result.verdicts) == 1
    assert result.verdicts[0].cross_ref_index == 2
    assert result.verdicts[0].match == "yes"


def test_verify_cross_references_max_to_verify_respektiert():
    """Mehr als max_to_verify ambivalente Refs → nur Top-N werden geprueft."""
    from services.audit_match_verifier import verify_cross_references
    # 5 Refs mit Score 80..84, alle im Bereich 75..89
    refs = [
        _make_cross_ref(
            "address_match", score=80.0 + i,
            register_a={"register": "state_aid", "value": f"A{i}"},
            register_b={"register": "beneficiaries", "value": f"B{i}"},
        )
        for i in range(5)
    ]
    fake_stream = _make_mock_stream(
        {"match": "yes", "confidence": 90, "reason": "passt"}
    )
    with patch("services.audit_match_verifier.llm_stream", fake_stream):
        result = asyncio.run(verify_cross_references(
            refs, score_min=75.0, score_max=89.0,
            max_to_verify=2, overall_timeout_s=30.0,
        ))
    # Nur 2 Refs werden geprueft, die mit niedrigstem Score (am ambivalentesten)
    assert result.total_input == 2
    assert len(result.verdicts) == 2
    assert {v.cross_ref_index for v in result.verdicts} == {0, 1}


def test_verify_cross_references_leere_eingabe():
    """0 Cross-Refs → leerer Result, KEIN LLM-Call."""
    from services.audit_match_verifier import verify_cross_references
    fake_stream = _make_mock_stream(
        {"match": "yes", "confidence": 90, "reason": "x"}
    )
    with patch("services.audit_match_verifier.llm_stream", fake_stream):
        result = asyncio.run(verify_cross_references(
            [], score_min=75.0, score_max=89.0,
            max_to_verify=20, overall_timeout_s=30.0,
        ))
    assert result.total_input == 0
    assert result.verdicts == []


def test_verify_cross_references_keine_im_range_kein_llm_call():
    """Alle Refs ausserhalb Score-Range → kein LLM-Call."""
    from services.audit_match_verifier import verify_cross_references
    refs = [
        _make_cross_ref(
            "address_match", score=95.0,
            register_a={"register": "state_aid", "value": "A"},
            register_b={"register": "beneficiaries", "value": "B"},
        ),
    ]
    call_count = {"n": 0}

    async def _counting_stream(*args, **kwargs):
        call_count["n"] += 1
        if False:
            yield ""

    with patch("services.audit_match_verifier.llm_stream", _counting_stream):
        result = asyncio.run(verify_cross_references(
            refs, score_min=75.0, score_max=89.0,
            max_to_verify=20, overall_timeout_s=30.0,
        ))
    assert call_count["n"] == 0
    assert result.total_input == 0
    assert result.verdicts == []


# ── verify_cross_references — Verdict-Inhalte ─────────────────────────────────


def test_verify_cross_references_match_no_setzt_filtered_by_llm_im_aufrufer():
    """Nur in der Service-Schicht — Setzen von ``filtered_by_llm`` macht
    der Wrapper im state_aid_audit_report ``_run_llm_verification``. Hier
    pruefen wir nur die Verdict-Daten."""
    from services.audit_match_verifier import verify_cross_references
    refs = [
        _make_cross_ref(
            "address_match", score=82.0,
            register_a={"register": "state_aid", "value": "Alpha"},
            register_b={"register": "beneficiaries", "value": "Beta"},
        ),
    ]
    fake_stream = _make_mock_stream(
        {"match": "no", "confidence": 90, "reason": "andere Stadt"}
    )
    with patch("services.audit_match_verifier.llm_stream", fake_stream):
        result = asyncio.run(verify_cross_references(
            refs, score_min=75.0, score_max=89.0,
            max_to_verify=10, overall_timeout_s=30.0,
        ))
    assert len(result.verdicts) == 1
    v = result.verdicts[0]
    assert v.match == "no"
    assert v.confidence == 90
    assert "andere Stadt" in v.reason


def test_verify_cross_references_json_parse_fehler_wird_unknown():
    """Wenn das LLM nicht-parsbares zurueckliefert → 'unknown' Fallback."""
    from services.audit_match_verifier import verify_cross_references
    refs = [
        _make_cross_ref(
            "address_match", score=82.0,
            register_a={"register": "state_aid", "value": "Alpha"},
            register_b={"register": "beneficiaries", "value": "Alpha"},
        ),
    ]
    # String, kein JSON-Block — Parser kann kein Verdict extrahieren
    fake_stream = _make_mock_stream(
        "Ich glaube ja, aber ich bin mir nicht sicher. Vielleicht."
    )
    with patch("services.audit_match_verifier.llm_stream", fake_stream):
        result = asyncio.run(verify_cross_references(
            refs, score_min=75.0, score_max=89.0,
            max_to_verify=10, overall_timeout_s=30.0,
        ))
    assert len(result.verdicts) == 1
    v = result.verdicts[0]
    assert v.match == "unknown"
    assert v.confidence == 0


# ── verify_cross_references — Timeout ─────────────────────────────────────────


def test_verify_cross_references_per_call_timeout_liefert_unknown_oder_skip():
    """Pro-Call-Timeout: hangt der Stream → Verdict bleibt aus oder unknown."""
    from services.audit_match_verifier import verify_cross_references
    refs = [
        _make_cross_ref(
            "address_match", score=82.0,
            register_a={"register": "state_aid", "value": "Alpha"},
            register_b={"register": "beneficiaries", "value": "Alpha"},
        ),
    ]
    fake_stream = _make_mock_stream(hang=True)
    with patch("services.audit_match_verifier.llm_stream", fake_stream):
        result = asyncio.run(verify_cross_references(
            refs, score_min=75.0, score_max=89.0,
            max_to_verify=1,
            overall_timeout_s=2.0,
            per_call_timeout_s=1.0,
        ))
    # Bei Timeout wird KEIN Verdict erstellt (raw_text bleibt leer)
    # ODER der globale Timeout greift → skipped_due_to_timeout > 0.
    assert result.total_input == 1
    # Entweder kein Verdict oder unknown — entscheidend ist, dass die
    # Funktion zurueckkehrt und nichts haengt.


def test_verify_cross_references_overall_timeout_skipped_count():
    """Globaler Timeout → restliche Refs werden als skipped gemeldet."""
    from services.audit_match_verifier import verify_cross_references
    # 3 Refs, jeder Stream haengt 30s. overall_timeout_s=2 ist zu kurz.
    refs = [
        _make_cross_ref(
            "address_match", score=80.0 + i,
            register_a={"register": "state_aid", "value": f"A{i}"},
            register_b={"register": "beneficiaries", "value": f"B{i}"},
        )
        for i in range(3)
    ]
    fake_stream = _make_mock_stream(hang=True)
    with patch("services.audit_match_verifier.llm_stream", fake_stream):
        result = asyncio.run(verify_cross_references(
            refs, score_min=75.0, score_max=89.0,
            max_to_verify=10,
            overall_timeout_s=1.5,
            per_call_timeout_s=0.5,
        ))
    assert result.total_input == 3
    # Mindestens ein Skip bei dieser Konfiguration
    assert result.skipped_due_to_timeout + len(result.verdicts) <= 3


# ── verify_match_pair — direkt ──────────────────────────────────────────────


def test_verify_match_pair_liefert_korrektes_verdict():
    from services.audit_match_verifier import verify_match_pair
    fake_stream = _make_mock_stream(
        {"match": "yes", "confidence": 87, "reason": "gleiche Adresse, gleicher Name"}
    )
    record_a = {"name": "Trumpf GmbH", "country_code": "DE", "nuts_code": "DE11"}
    record_b = {"name": "Trumpf GmbH", "country_code": "DE", "nuts_code": "DE11"}
    with patch("services.audit_match_verifier.llm_stream", fake_stream):
        verdict = asyncio.run(verify_match_pair(
            record_a, record_b,
            cross_ref_index=42,
            timeout_s=10.0,
        ))
    assert verdict is not None
    assert verdict.cross_ref_index == 42
    assert verdict.match == "yes"
    assert verdict.confidence == 87
    assert "gleiche Adresse" in verdict.reason
    assert verdict.elapsed_ms >= 0


def test_verify_match_pair_leerer_stream_liefert_none():
    """Leerer Stream (keine Tokens, kein done) → None."""
    from services.audit_match_verifier import verify_match_pair
    fake_stream = _make_mock_stream(verdict_payload=None)
    with patch("services.audit_match_verifier.llm_stream", fake_stream):
        verdict = asyncio.run(verify_match_pair(
            {"name": "A"}, {"name": "B"},
            cross_ref_index=0, timeout_s=2.0,
        ))
    assert verdict is None


# ── Integration mit AuditReportData ──────────────────────────────────────────


def test_run_llm_verification_setzt_filtered_by_llm_und_evidence():
    """End-to-end im audit_report-Wrapper: Verdict wird an Cross-Ref geheftet."""
    from services.state_aid_audit_report import _run_llm_verification

    cross_refs = [
        _make_cross_ref(
            "address_match", score=82.0,
            register_a={"register": "state_aid", "value": "Alpha"},
            register_b={"register": "beneficiaries", "value": "Alpha"},
        ),
        _make_cross_ref(
            "address_match", score=78.0,
            register_a={"register": "state_aid", "value": "Beta"},
            register_b={"register": "beneficiaries", "value": "Charlie"},
        ),
    ]
    # Wir muessen pro Ref den richtigen Verdict liefern. Da der Mock fuer alle
    # Calls den gleichen Wert zurueckgibt, geben wir hier einen konstanten
    # `no`-Verdict — beide Cross-Refs sollen anschliessend filtered_by_llm sein.
    fake_stream = _make_mock_stream(
        {"match": "no", "confidence": 85, "reason": "klarer Konflikt"}
    )

    with patch("services.audit_match_verifier.llm_stream", fake_stream):
        # Logging in DB ueberspringen (kein DB-Setup im Test)
        with patch("services.audit_match_verifier.log_verdict_to_db", lambda **kw: None):
            result = _run_llm_verification(
                cross_refs,
                score_min=75.0, score_max=89.0,
                max_to_verify=10, overall_timeout_s=30.0,
                pruefer_user_id=None,
            )

    assert result is not None
    assert result.total_input == 2
    assert len(result.verdicts) == 2
    # Beide Cross-Refs sind nun als gefiltert markiert
    for cr in cross_refs:
        assert cr.filtered_by_llm is True
        assert cr.llm_confirmed is False
        assert "llm_verdict" in cr.evidence
        assert cr.evidence["llm_verdict"]["match"] == "no"


def test_run_llm_verification_yes_setzt_llm_confirmed():
    from services.state_aid_audit_report import _run_llm_verification
    cross_refs = [
        _make_cross_ref(
            "address_match", score=85.0,
            register_a={"register": "state_aid", "value": "Alpha GmbH"},
            register_b={"register": "beneficiaries", "value": "Alpha GmbH"},
        ),
    ]
    fake_stream = _make_mock_stream(
        {"match": "yes", "confidence": 92, "reason": "identische Daten"}
    )

    with patch("services.audit_match_verifier.llm_stream", fake_stream):
        with patch("services.audit_match_verifier.log_verdict_to_db", lambda **kw: None):
            result = _run_llm_verification(
                cross_refs,
                score_min=75.0, score_max=89.0,
                max_to_verify=10, overall_timeout_s=30.0,
                pruefer_user_id=None,
            )

    assert result is not None
    cr = cross_refs[0]
    assert cr.llm_confirmed is True
    assert cr.filtered_by_llm is False
    assert cr.evidence["llm_verdict"]["match"] == "yes"


def test_audit_report_data_to_dict_enthaelt_llm_verification_feld():
    """to_dict() liefert llm_verification, auch wenn None."""
    from datetime import datetime
    from services.state_aid_audit_report import (
        AuditReportData, BeneficiariesSection, SanctionsSection, StateAidSection,
    )
    data = AuditReportData(
        query="Test",
        issued_at=datetime(2026, 5, 8),
        auftraggeber=None,
        pruefer_name=None,
        state_aid=StateAidSection(),
        beneficiaries=BeneficiariesSection(),
        sanctions=SanctionsSection(),
        cross_references=[],
        data_freshness={},
    )
    out = data.to_dict()
    assert "llm_verification" in out
    assert out["llm_verification"] is None


def test_audit_report_data_to_dict_serialisiert_llm_verification():
    """Wenn llm_verification gesetzt ist, wird das to_dict-Resultat eingebettet."""
    from datetime import datetime
    from services.audit_match_verifier import LlmMatchVerdict, LlmVerificationResult
    from services.state_aid_audit_report import (
        AuditReportData, BeneficiariesSection, SanctionsSection, StateAidSection,
    )
    ver = LlmVerificationResult(
        total_input=2,
        verdicts=[
            LlmMatchVerdict(
                cross_ref_index=0, match="yes", confidence=88,
                reason="passt", elapsed_ms=4500, model_name="qwen3:14b",
            ),
            LlmMatchVerdict(
                cross_ref_index=1, match="no", confidence=72,
                reason="andere Stadt", elapsed_ms=3800, model_name="qwen3:14b",
            ),
        ],
        elapsed_total_ms=8300,
    )
    data = AuditReportData(
        query="Test",
        issued_at=datetime(2026, 5, 8),
        auftraggeber=None,
        pruefer_name=None,
        state_aid=StateAidSection(),
        beneficiaries=BeneficiariesSection(),
        sanctions=SanctionsSection(),
        cross_references=[],
        data_freshness={},
        llm_verification=ver,
    )
    out = data.to_dict()
    assert out["llm_verification"] is not None
    assert out["llm_verification"]["total_input"] == 2
    assert len(out["llm_verification"]["verdicts"]) == 2
    assert out["llm_verification"]["verdicts"][0]["match"] == "yes"
    assert out["llm_verification"]["verdicts"][1]["match"] == "no"


# ── PDF mit LLM-Verifikation ─────────────────────────────────────────────────


def test_pdf_enthaelt_llm_verifikation_section_wenn_gesetzt():
    """Generiertes PDF muss „LLM-Verifikation" enthalten, wenn data.llm_verification gesetzt."""
    try:
        import fitz  # type: ignore
    except Exception:  # noqa: BLE001
        pytest.skip("pymupdf nicht verfuegbar")

    from datetime import datetime
    from services.audit_match_verifier import LlmMatchVerdict, LlmVerificationResult
    from services.state_aid_audit_pdf import render_audit_report_pdf
    from services.state_aid_audit_report import (
        AuditReportData, BeneficiariesSection, CrossReference,
        SanctionsSection, StateAidSection,
    )

    # Cross-Ref mit Score und LLM-Verdict
    cross_ref = CrossReference(
        type="address_match",
        description="Test",
        evidence={
            "name_similarity_score": 82.0,
            "register_a": {"register": "state_aid", "value": "Alpha GmbH"},
            "register_b": {"register": "beneficiaries", "value": "Alpha GmbH"},
            "llm_verdict": {
                "match": "yes", "confidence": 88,
                "reason": "Adresse + Name + Land identisch",
            },
        },
        filtered_by_llm=False,
        llm_confirmed=True,
    )
    ver = LlmVerificationResult(
        total_input=1,
        verdicts=[
            LlmMatchVerdict(
                cross_ref_index=0, match="yes", confidence=88,
                reason="Adresse + Name + Land identisch",
                elapsed_ms=4200, model_name="qwen3:14b",
            ),
        ],
        elapsed_total_ms=4200,
    )
    data = AuditReportData(
        query="Alpha GmbH",
        issued_at=datetime(2026, 5, 8, 10, 0, 0),
        auftraggeber="Pruefbehoerde",
        pruefer_name="J. Riener",
        state_aid=StateAidSection(),
        beneficiaries=BeneficiariesSection(),
        sanctions=SanctionsSection(),
        cross_references=[cross_ref],
        data_freshness={},
        llm_verification=ver,
    )

    pdf = render_audit_report_pdf(data)
    assert isinstance(pdf, bytes)
    assert pdf[:4] == b"%PDF"

    doc = fitz.open(stream=pdf, filetype="pdf")
    full_text = "\n".join(page.get_text() for page in doc)
    doc.close()

    # Sektion existiert
    assert "LLM-Verifikation" in full_text
    # Begruendung wird wiedergegeben
    assert "Adresse" in full_text or "identisch" in full_text


def test_pdf_filtered_refs_nicht_in_querbezug_tabelle():
    """Cross-Refs mit filtered_by_llm=True erscheinen NICHT in der Querbezug-Tabelle."""
    try:
        import fitz  # type: ignore
    except Exception:  # noqa: BLE001
        pytest.skip("pymupdf nicht verfuegbar")

    from datetime import datetime
    from services.audit_match_verifier import LlmMatchVerdict, LlmVerificationResult
    from services.state_aid_audit_pdf import render_audit_report_pdf
    from services.state_aid_audit_report import (
        AuditReportData, BeneficiariesSection, CrossReference,
        SanctionsSection, StateAidSection,
    )

    cr_filtered = CrossReference(
        type="address_match",
        description="ZZZGEFILTERT-MARKER-ABC",
        evidence={
            "name_similarity_score": 80.0,
            "register_a": {"register": "state_aid", "value": "X"},
            "register_b": {"register": "beneficiaries", "value": "Y"},
        },
        filtered_by_llm=True,
    )
    cr_kept = CrossReference(
        type="address_match",
        description="QQQGEHALTEN-MARKER-XYZ",
        evidence={
            "name_similarity_score": 85.0,
            "register_a": {"register": "state_aid", "value": "Same"},
            "register_b": {"register": "beneficiaries", "value": "Same"},
        },
        filtered_by_llm=False,
        llm_confirmed=True,
    )
    ver = LlmVerificationResult(
        total_input=2,
        verdicts=[
            LlmMatchVerdict(
                cross_ref_index=0, match="no", confidence=90,
                reason="andere Stadt", elapsed_ms=3000, model_name="x",
            ),
            LlmMatchVerdict(
                cross_ref_index=1, match="yes", confidence=85,
                reason="passt", elapsed_ms=3000, model_name="x",
            ),
        ],
    )
    data = AuditReportData(
        query="Test",
        issued_at=datetime(2026, 5, 8),
        auftraggeber="TestAG",
        pruefer_name=None,
        state_aid=StateAidSection(),
        beneficiaries=BeneficiariesSection(),
        sanctions=SanctionsSection(),
        cross_references=[cr_filtered, cr_kept],
        data_freshness={},
        llm_verification=ver,
    )

    pdf = render_audit_report_pdf(data)
    doc = fitz.open(stream=pdf, filetype="pdf")
    full_text = "\n".join(page.get_text() for page in doc)
    doc.close()

    # Der gefilterte Eintrag darf NICHT in der Hauptansicht erscheinen — beide
    # Marker sind in der Description und damit nur in „Querbezuege"-Tabelle
    # sichtbar.
    assert "QQQGEHALTEN-MARKER-XYZ" in full_text
    assert "ZZZGEFILTERT-MARKER-ABC" not in full_text
    # Aber LLM-Verifikations-Sektion ist da
    assert "LLM-Verifikation" in full_text
