"""
Unit-Tests fuer services/state_aid_llm.py — Pure-Funktionen + LLM-Mocking.

Reine Unit-Tests ohne laufenden Server, ohne echtes Ollama. Der LLM-Stream
wird ueber `monkeypatch` durch einen synthetischen async-Generator ersetzt.

Lauf: pytest backend/tests/test_state_aid_llm.py -q
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import AsyncGenerator

import pytest

# Backend-Verzeichnis in den Pfad legen, damit `services.*` importierbar ist
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ── Helpers fuer LLM-Mocking ─────────────────────────────────────────────────


def _sse_frame(token: str, done: bool = False) -> str:
    """Erzeugt einen SSE-Frame, wie ihn der echte ollama_service.stream produziert."""
    payload = {"token": token, "done": done}
    return f"data: {json.dumps(payload)}\n\n"


def _make_llm_mock(full_response: str):
    """Liefert einen async-Generator, der `full_response` Token-fuer-Token streamt."""
    async def fake_stream(*args, **kwargs) -> AsyncGenerator[str, None]:
        # Token in 8-Zeichen-Chunks aufsplitten, wie es das Gateway tut
        for i in range(0, len(full_response), 8):
            chunk = full_response[i:i + 8]
            yield _sse_frame(chunk, done=False)
        yield (
            "data: " + json.dumps({"done": True, "token_count": 1, "model": "mock"}) + "\n\n"
        )

    return fake_stream


# ── _extract_json_block ──────────────────────────────────────────────────────


def test_extract_json_block_with_fence():
    from services.state_aid_llm import _extract_json_block
    text = 'Hier kommt der Filter:\n```json\n{"q": "BMW", "country_code": "DE"}\n```\nFertig.'
    assert _extract_json_block(text) == '{"q": "BMW", "country_code": "DE"}'


def test_extract_json_block_without_fence():
    from services.state_aid_llm import _extract_json_block
    text = 'Filter: {"min_amount": 1000000}'
    assert _extract_json_block(text) == '{"min_amount": 1000000}'


def test_extract_json_block_balanced_braces():
    from services.state_aid_llm import _extract_json_block
    text = 'Vorab {"a": {"b": 1}, "c": 2} und Nachgesetz'
    assert _extract_json_block(text) == '{"a": {"b": 1}, "c": 2}'


def test_extract_json_block_empty_returns_none():
    from services.state_aid_llm import _extract_json_block
    assert _extract_json_block("") is None
    assert _extract_json_block("Kein JSON hier.") is None


# ── _sanitize_filter_dict ────────────────────────────────────────────────────


def test_sanitize_filter_dict_keeps_whitelist():
    from services.state_aid_llm import _sanitize_filter_dict
    raw = {"q": "BMW AG", "country_code": "de", "min_amount": "1000000"}
    out = _sanitize_filter_dict(raw)
    assert out["q"] == "BMW AG"
    assert out["country_code"] == "DE"
    assert out["min_amount"] == 1_000_000.0


def test_sanitize_filter_dict_drops_unknown_fields():
    from services.state_aid_llm import _sanitize_filter_dict
    raw = {"q": "BMW", "evil_sql": "DROP TABLE awards;", "limit": 999}
    out = _sanitize_filter_dict(raw)
    assert "evil_sql" not in out
    assert "limit" not in out
    assert out["q"] == "BMW"


def test_sanitize_filter_dict_invalid_country_dropped():
    from services.state_aid_llm import _sanitize_filter_dict
    raw = {"country_code": "FR"}  # nicht erlaubt (nur DE/AT)
    out = _sanitize_filter_dict(raw)
    assert "country_code" not in out


def test_sanitize_filter_dict_invalid_nuts_dropped():
    from services.state_aid_llm import _sanitize_filter_dict
    raw = {"nuts_code": "Bayern"}  # kein Code-Format
    out = _sanitize_filter_dict(raw)
    assert "nuts_code" not in out


def test_sanitize_filter_dict_valid_nuts_kept():
    from services.state_aid_llm import _sanitize_filter_dict
    raw = {"nuts_code": "de212"}
    out = _sanitize_filter_dict(raw)
    assert out["nuts_code"] == "DE212"


def test_sanitize_filter_dict_invalid_date_dropped():
    from services.state_aid_llm import _sanitize_filter_dict
    raw = {"since": "irgendwas"}
    out = _sanitize_filter_dict(raw)
    assert "since" not in out


def test_sanitize_filter_dict_negative_amount_dropped():
    from services.state_aid_llm import _sanitize_filter_dict
    raw = {"min_amount": -100}
    out = _sanitize_filter_dict(raw)
    assert "min_amount" not in out


def test_sanitize_filter_dict_empty_dict():
    from services.state_aid_llm import _sanitize_filter_dict
    assert _sanitize_filter_dict({}) == {}


def test_sanitize_filter_dict_none_input():
    from services.state_aid_llm import _sanitize_filter_dict
    assert _sanitize_filter_dict(None) == {}


# ── parse_question (mit gemocktem LLM) ───────────────────────────────────────


def test_parse_question_with_clean_json_block(monkeypatch):
    """LLM liefert sauberen JSON-Block -> Filter wird uebernommen."""
    from services import state_aid_llm

    response = (
        'Hier der Filter:\n'
        '```json\n'
        '{"q": "BMW", "country_code": "DE", "since": "2022-01-01", '
        '"until": "2022-12-31", "min_amount": 1000000}\n'
        '```'
    )
    monkeypatch.setattr(state_aid_llm, "llm_stream", _make_llm_mock(response))

    filter_dict, raw, source = asyncio.run(
        state_aid_llm.parse_question("Zeig mir BMW-Beihilfen 2022 ueber 1 Mio")
    )
    assert source == "llm"
    assert filter_dict["q"] == "BMW"
    assert filter_dict["country_code"] == "DE"
    assert filter_dict["since"] == "2022-01-01"
    assert filter_dict["until"] == "2022-12-31"
    assert filter_dict["min_amount"] == 1_000_000.0


def test_parse_question_with_broken_llm_response_falls_back(monkeypatch):
    """LLM antwortet Muell -> deterministischer Fallback greift (Jahr/Region)."""
    from services import state_aid_llm

    monkeypatch.setattr(
        state_aid_llm, "llm_stream",
        _make_llm_mock("Das ist keine JSON-Antwort, sondern Prosa."),
    )

    filter_dict, _, source = asyncio.run(
        state_aid_llm.parse_question("Beihilfen aus Bayern 2023")
    )
    assert source == "fallback"
    # Bayern -> DE2, 2023 -> Jahresfenster
    assert filter_dict.get("nuts_code") == "DE2"
    assert filter_dict.get("country_code") == "DE"
    assert filter_dict.get("since") == "2023-01-01"
    assert filter_dict.get("until") == "2023-12-31"


def test_parse_question_empty_llm_and_empty_fallback(monkeypatch):
    """Komplett leere LLM-Antwort + nichts erkennbares -> leerer Filter."""
    from services import state_aid_llm

    monkeypatch.setattr(state_aid_llm, "llm_stream", _make_llm_mock(""))

    filter_dict, _, source = asyncio.run(
        state_aid_llm.parse_question("ein bisschen text ohne anhaltspunkte"),
    )
    assert filter_dict == {}
    assert source == "fallback"


def test_parse_question_country_voreinsteller_aus_ui(monkeypatch):
    """Wenn LLM keinen country_code liefert, uebernimmt UI-Voreinsteller."""
    from services import state_aid_llm

    monkeypatch.setattr(
        state_aid_llm, "llm_stream",
        _make_llm_mock('```json\n{"q": "Test"}\n```'),
    )
    filter_dict, _, source = asyncio.run(
        state_aid_llm.parse_question("Test", country_code="AT"),
    )
    assert filter_dict["country_code"] == "AT"
    assert filter_dict["q"] == "Test"
    assert source == "llm"


def test_parse_question_llm_country_wins_over_ui(monkeypatch):
    """Wenn LLM explizit ein anderes Land liefert, gewinnt das LLM."""
    from services import state_aid_llm

    monkeypatch.setattr(
        state_aid_llm, "llm_stream",
        _make_llm_mock('```json\n{"country_code": "AT", "q": "Wien-Firma"}\n```'),
    )
    filter_dict, _, _ = asyncio.run(
        state_aid_llm.parse_question("Wien-Firma", country_code="DE"),
    )
    assert filter_dict["country_code"] == "AT"


def test_parse_question_drops_disallowed_fields(monkeypatch):
    """LLM liefert verbotenes Feld -> wird verworfen."""
    from services import state_aid_llm

    response = '```json\n{"q": "BMW", "drop_table": "awards", "limit": 99}\n```'
    monkeypatch.setattr(state_aid_llm, "llm_stream", _make_llm_mock(response))

    filter_dict, _, _ = asyncio.run(state_aid_llm.parse_question("BMW"))
    assert "drop_table" not in filter_dict
    assert "limit" not in filter_dict
    assert filter_dict["q"] == "BMW"


def test_parse_question_empty_question_returns_empty():
    from services import state_aid_llm
    filter_dict, raw, source = asyncio.run(state_aid_llm.parse_question(""))
    assert filter_dict == {}
    assert raw == ""


# ── Fallback-Detection (pure) ────────────────────────────────────────────────


def test_fallback_detects_min_amount_million():
    from services.state_aid_llm import _detect_min_amount
    assert _detect_min_amount("ueber 1 Mio EUR") == 1_000_000.0
    assert _detect_min_amount("mehr als 2,5 Millionen") == 2_500_000.0
    # Deutsche Tausenderpunkte werden erkannt
    assert _detect_min_amount("> 500.000 EUR") == 500_000.0
    assert _detect_min_amount("ueber 1.500.000 EUR") == 1_500_000.0


def test_fallback_min_amount_returns_none_without_marker():
    from services.state_aid_llm import _detect_min_amount
    # Ohne 'ueber'/'mehr als'/... -> kein Match
    assert _detect_min_amount("Beihilfen aus Bayern") is None
    assert _detect_min_amount("") is None


def test_fallback_detects_min_amount_with_milliarde():
    from services.state_aid_llm import _detect_min_amount
    assert _detect_min_amount("mindestens 1 Mrd EUR") == 1_000_000_000.0


def test_fallback_detects_year_window():
    from services.state_aid_llm import _detect_year_window
    since, until = _detect_year_window("Beihilfen aus 2022 in Hessen")
    assert since == "2022-01-01"
    assert until == "2022-12-31"


def test_fallback_detects_no_year():
    from services.state_aid_llm import _detect_year_window
    since, until = _detect_year_window("Was war das fuer eine Foerderung?")
    assert since is None and until is None


def test_fallback_nuts_alias_hessen():
    from services.state_aid_llm import _detect_nuts_alias
    assert _detect_nuts_alias("Vorhaben in Hessen") == "DE7"


def test_fallback_nuts_alias_bayern():
    from services.state_aid_llm import _detect_nuts_alias
    assert _detect_nuts_alias("Maschinenbau in Bayern") == "DE2"


def test_fallback_nuts_alias_wien():
    from services.state_aid_llm import _detect_nuts_alias
    assert _detect_nuts_alias("Foerderungen in Wien") == "AT13"


def test_fallback_nuts_alias_none():
    from services.state_aid_llm import _detect_nuts_alias
    assert _detect_nuts_alias("Beihilfen ueber 1 Mio") is None


def test_fallback_full_for_typical_question():
    from services.state_aid_llm import _fallback_filter_from_question
    out = _fallback_filter_from_question("Zeig mir Beihilfen aus Bayern 2022 ueber 1 Mio")
    assert out["nuts_code"] == "DE2"
    assert out["country_code"] == "DE"
    assert out["since"] == "2022-01-01"
    assert out["until"] == "2022-12-31"
    assert out["min_amount"] == 1_000_000.0


def test_fallback_detects_sa_reference():
    from services.state_aid_llm import _fallback_filter_from_question
    out = _fallback_filter_from_question("Was steht zu SA.40478?")
    assert out["sa_reference"] == "SA.40478"


# ── relax_filters ────────────────────────────────────────────────────────────


def test_relax_filters_drops_min_amount_first():
    from services.state_aid_llm import relax_filters
    f = {"q": "BMW", "country_code": "DE", "min_amount": 1000000, "nuts_code": "DE2"}
    new_f, removed = relax_filters(f)
    assert removed == "min_amount"
    assert "min_amount" not in new_f
    assert new_f["q"] == "BMW"


def test_relax_filters_drops_nuts_before_country():
    from services.state_aid_llm import relax_filters
    f = {"country_code": "DE", "nuts_code": "DE2"}
    new_f, removed = relax_filters(f)
    assert removed == "nuts_code"
    assert new_f == {"country_code": "DE"}


def test_relax_filters_eventually_empty():
    from services.state_aid_llm import relax_filters
    f = {"country_code": "DE"}
    new_f, removed = relax_filters(f)
    assert removed == "country_code"
    assert new_f == {}


def test_relax_filters_nothing_to_remove():
    from services.state_aid_llm import relax_filters
    new_f, removed = relax_filters({"q": "BMW"})  # q ist nicht in RELAX_ORDER
    assert removed is None
    assert new_f == {"q": "BMW"}


# ── compute_stats (synthetische Hits) ────────────────────────────────────────


def _hit(name: str, amount: float, *, authority: str = "AB",
         nuts: str = "DE7", region_label: str = "Hessen",
         year: str = "2022", objective: str = "Forschung") -> dict:
    return {
        "beneficiary_name": name,
        "aid_amount_eur": amount,
        "granting_authority": authority,
        "nuts_code": nuts,
        "nuts_label": region_label,
        "aid_objective": objective,
        "granting_date": f"{year}-06-01",
    }


def test_compute_stats_empty():
    from services.state_aid_llm import compute_stats
    s = compute_stats([])
    assert s.total_hits == 0
    assert s.total_eur == 0.0
    assert s.top_beneficiaries == []
    assert s.by_year == {}


def test_compute_stats_basic_aggregates():
    from services.state_aid_llm import compute_stats
    hits = [
        _hit("BMW AG", 500_000),
        _hit("BMW AG", 300_000),
        _hit("Mercedes", 400_000),
        _hit("Bosch GmbH", 200_000),
    ]
    s = compute_stats(hits)
    assert s.total_hits == 4
    assert s.total_eur == 1_400_000.0
    # BMW summiert auf 800k -> Top 1
    top1 = s.top_beneficiaries[0]
    assert top1.name == "BMW AG"
    assert top1.count == 2
    assert top1.total_eur == 800_000.0


def test_compute_stats_top_share_pct():
    from services.state_aid_llm import compute_stats
    hits = [
        _hit("BigCo", 900_000),
        _hit("SmallCo", 100_000),
    ]
    s = compute_stats(hits)
    assert s.total_eur == 1_000_000.0
    assert abs(s.top_share_pct - 90.0) < 0.01


def test_compute_stats_by_year_aggregation():
    from services.state_aid_llm import compute_stats
    hits = [
        _hit("A", 100_000, year="2022"),
        _hit("B", 200_000, year="2022"),
        _hit("C", 300_000, year="2023"),
    ]
    s = compute_stats(hits)
    assert s.by_year[2022]["count"] == 2
    assert s.by_year[2022]["total_eur"] == 300_000.0
    assert s.by_year[2023]["count"] == 1


def test_compute_stats_handles_missing_amount():
    from services.state_aid_llm import compute_stats
    hits = [
        _hit("A", 100_000),
        {"beneficiary_name": "B", "aid_amount_eur": None,
         "granting_date": "2022-01-01"},
    ]
    s = compute_stats(hits)
    assert s.total_hits == 2
    assert s.total_eur == 100_000.0


def test_compute_stats_to_dict_serializable():
    from services.state_aid_llm import compute_stats
    s = compute_stats([_hit("A", 100_000.5)])
    d = s.to_dict()
    # JSON-serialisierbar?
    json.dumps(d)
    assert d["total_hits"] == 1
    assert d["total_eur"] == 100_000.5
    assert d["top_beneficiaries"][0]["name"] == "A"


def test_compute_stats_top_regions_uses_label_when_present():
    from services.state_aid_llm import compute_stats
    hits = [
        _hit("A", 100_000, nuts="DE7", region_label="Hessen"),
        _hit("B", 200_000, nuts="DE2", region_label="Bayern"),
    ]
    s = compute_stats(hits)
    names = [r.name for r in s.top_regions]
    assert "Bayern" in names or "Hessen" in names
    # Bayern hat hoeheren Betrag -> Top 1
    assert s.top_regions[0].name == "Bayern"


# ── _format_eur ──────────────────────────────────────────────────────────────


def test_format_eur_basic():
    from services.state_aid_llm import _format_eur
    assert _format_eur(1_234_567.89) == "1.234.567,89 EUR"


def test_format_eur_zero():
    from services.state_aid_llm import _format_eur
    assert _format_eur(0.0) == "0,00 EUR"


def test_format_eur_small():
    from services.state_aid_llm import _format_eur
    assert _format_eur(123.45) == "123,45 EUR"


# ── _build_summary_user_prompt ───────────────────────────────────────────────


def test_summary_prompt_includes_required_fields():
    from services.state_aid_llm import _build_summary_user_prompt, compute_stats
    hits = [_hit("BMW", 500_000), _hit("Mercedes", 300_000)]
    stats = compute_stats(hits)
    prompt = _build_summary_user_prompt("Wer hat 2022 viel bekommen?", hits, stats)
    assert "Treffer-Anzahl: 2" in prompt
    assert "BMW" in prompt
    assert "Mercedes" in prompt
    assert "Top-Beguenstigte" in prompt
    assert "Top-Behoerden" in prompt
    # Pflicht: 200-Worte-Limit-Hinweis im Prompt
    assert "200 Worte" in prompt or "max" in prompt.lower()


# ── stream_summary ───────────────────────────────────────────────────────────


def test_stream_summary_no_hits_returns_static_text():
    """0 Treffer -> kein LLM-Aufruf, statischer Text."""
    from services.state_aid_llm import stream_summary, compute_stats

    async def collect():
        parts = []
        async for tok in stream_summary("Frage", [], compute_stats([])):
            parts.append(tok)
        return "".join(parts)

    text = asyncio.run(collect())
    assert "Keine Treffer" in text
    assert "Pruefer" in text  # Disclaimer-Hinweis


def test_stream_summary_with_hits_uses_llm(monkeypatch):
    """Mit Treffern wird der LLM-Stream-Mock genutzt."""
    from services import state_aid_llm

    monkeypatch.setattr(
        state_aid_llm, "llm_stream",
        _make_llm_mock("Insgesamt zwei Vorhaben mit 800.000,00 EUR. Disclaimer."),
    )

    hits = [_hit("BMW", 500_000), _hit("Mercedes", 300_000)]
    stats = state_aid_llm.compute_stats(hits)

    async def collect():
        parts = []
        async for tok in state_aid_llm.stream_summary("Frage", hits, stats):
            parts.append(tok)
        return "".join(parts)

    text = asyncio.run(collect())
    # Der Mock streamt unsere Vorgabe Token-fuer-Token.
    assert "Insgesamt zwei Vorhaben" in text
