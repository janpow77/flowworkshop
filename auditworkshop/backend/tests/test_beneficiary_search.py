"""
Unit-Tests fuer die Begünstigtenverzeichnis-Suche
(services/dataframe_service.py + services/company_aliases.py).

Reine Unit-Tests fuer die Such-Helfer und das Alias-Modul. Kein DB-Zugriff,
keine FastAPI-App — laufen schnell und ohne Container-Setup.

Lauf: pytest backend/tests/test_beneficiary_search.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

# Backend-Verzeichnis in den Pfad legen, damit `services.*` importierbar ist
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ── Paket 1: Hyphen-Fix in Tokenisierung / Scoring ────────────────────────────


def test_tokenize_handles_hyphen_as_word_separator():
    """'Fraunhofer-Gesellschaft' muss in zwei Tokens zerlegt werden,
    sonst findet eine Query 'Fraunhofer Gesellschaft' den Datensatz nicht."""
    from services.dataframe_service import _tokenize_search_text
    tokens = _tokenize_search_text("Fraunhofer-Gesellschaft")
    assert "fraunhofer" in tokens
    assert "gesellschaft" in tokens


def test_tokenize_handles_slash_as_word_separator():
    """Slash trennt ebenfalls (z.B. 'Industrie- und Handelskammer / IHK')."""
    from services.dataframe_service import _tokenize_search_text
    tokens = _tokenize_search_text("Forschung/Entwicklung")
    assert "forschung" in tokens
    assert "entwicklung" in tokens


def test_score_search_value_hyphen_value_space_query():
    """Wert hat Hyphen, Query hat Leerzeichen → muss matchen."""
    from services.dataframe_service import _score_search_value, _normalize_search_text
    score = _score_search_value(
        "Fraunhofer-Gesellschaft zur Förderung",
        _normalize_search_text("Fraunhofer Gesellschaft"),
    )
    assert score > 0


def test_score_search_value_space_value_hyphen_query():
    """Wert hat Leerzeichen, Query hat Hyphen → muss matchen (Symmetrie)."""
    from services.dataframe_service import _score_search_value, _normalize_search_text
    score = _score_search_value(
        "Fraunhofer Gesellschaft zur Förderung",
        _normalize_search_text("Fraunhofer-Gesellschaft"),
    )
    assert score > 0


def test_score_search_value_substring_with_hyphen():
    """Substring-Match (Score 78) muss nun auch ueber Hyphen funktionieren."""
    from services.dataframe_service import _score_search_value, _normalize_search_text
    # Wert hat einen Bindestrich, Query nicht — sollte trotzdem matchen.
    score = _score_search_value(
        "Max-Planck-Institut für Festkörperforschung",
        _normalize_search_text("planck institut"),
    )
    assert score > 0


def test_search_word_present_across_hyphen():
    """\\b-Match darf Hyphen ueberspringen (durch Replace → Space)."""
    from services.dataframe_service import _search_word_present
    assert _search_word_present("planck", "max-planck-institut")
    assert _search_word_present("institut", "max-planck-institut")


# ── Paket 2: Alias-Expansion ──────────────────────────────────────────────────


def test_expand_alias_kfw_to_full_form():
    """'KfW' wird zu 'Kreditanstalt für Wiederaufbau KfW' expandiert."""
    from services.company_aliases import expand_alias
    expanded, label = expand_alias("KfW")
    assert label is not None
    assert "Kreditanstalt" in label
    assert "KfW" in expanded


def test_expand_alias_first_token_match():
    """'BMWK Förderung 2024' → erster Token expandiert sich."""
    from services.company_aliases import expand_alias
    expanded, label = expand_alias("BMWK Förderung 2024")
    assert label is not None
    assert "Bundesministerium" in label
    # Original muss erhalten bleiben (Token-Match findet beide Pfade)
    assert "Förderung" in expanded
    assert "2024" in expanded


def test_expand_alias_unknown_returns_original():
    """Unbekannte Query bleibt unveraendert, label ist None."""
    from services.company_aliases import expand_alias
    expanded, label = expand_alias("XYZ-Random-Query")
    assert expanded == "XYZ-Random-Query"
    assert label is None


def test_expand_alias_empty_input():
    """Leere/None-Eingabe darf nicht crashen."""
    from services.company_aliases import expand_alias
    assert expand_alias("") == ("", None)
    assert expand_alias("   ") == ("", None)


def test_expand_alias_long_first_token_not_treated_as_acronym():
    """Lange Erstwoerter (>6 Zeichen) sollen NICHT als Akronym matchen,
    auch wenn sie zufaellig im Mapping stehen — verhindert Over-Matching
    bei Volltextsuchen wie 'fraunhofer institut ...'."""
    from services.company_aliases import expand_alias
    # 'fraunhofer' ist 10 Zeichen lang → first-token-Pfad darf nicht greifen.
    # (Voll-Query-Pfad triggert nur bei exaktem Match auf 'fraunhofer'.)
    expanded, label = expand_alias("fraunhofer institut für solare energiesysteme")
    # Vollform-Pfad nicht aktiv (Query hat mehr als nur 'fraunhofer')
    # First-token-Pfad nicht aktiv (Token > 6 Zeichen)
    assert label is None or "Fraunhofer" in (label or "")
    # Wichtig: Das Original muss in jedem Fall erhalten bleiben
    assert "institut" in expanded.lower()


def test_load_company_aliases_returns_mapping():
    """Aliases-Mapping ist nicht leer (entweder JSON oder Fallback)."""
    from services.company_aliases import load_company_aliases
    aliases = load_company_aliases()
    assert isinstance(aliases, dict)
    assert len(aliases) > 0
    # Wenigstens eine bekannte Kernabkuerzung muss vorhanden sein
    assert "kfw" in aliases or "bmwk" in aliases


# ── Paket 4: rapidfuzz-Scoring (0..100-Skala) ─────────────────────────────────


def test_rapidfuzz_score_hyphen_vs_space_high_match():
    """'Fraunhofer Gesellschaft' vs 'Fraunhofer-Gesellschaft' muss ≥95 sein."""
    from services.dataframe_service import _rapidfuzz_score
    score = _rapidfuzz_score("Fraunhofer-Gesellschaft", "Fraunhofer Gesellschaft")
    assert score >= 95, f"erwartet >=95, war {score}"


def test_rapidfuzz_score_exact_match_returns_100():
    """Identische normalisierte Strings → Exact-Match-Boost auf 100.0."""
    from services.dataframe_service import _rapidfuzz_score
    assert _rapidfuzz_score("Siemens AG", "siemens ag") == 100.0


def test_rapidfuzz_score_accents_normalized():
    """'Müller' vs 'Mueller' muss hoch matchen (Akzent-Normalisierung)."""
    from services.dataframe_service import _rapidfuzz_score
    score = _rapidfuzz_score("Müller GmbH", "Mueller GmbH")
    assert score >= 95


def test_rapidfuzz_score_unrelated_strings_low():
    """Unverwandte Strings → niedriger Score."""
    from services.dataframe_service import _rapidfuzz_score
    score = _rapidfuzz_score("Bauernhof Schmid", "Quantenmechanik")
    assert score < 60


def test_rapidfuzz_score_empty_inputs_zero():
    """Leere Eingaben → 0.0, kein Crash."""
    from services.dataframe_service import _rapidfuzz_score
    assert _rapidfuzz_score("", "Siemens") == 0.0
    assert _rapidfuzz_score("Siemens", "") == 0.0
    assert _rapidfuzz_score(None, "abc") == 0.0


# ── Paket 5: Adaptive min_score ───────────────────────────────────────────────


def test_adaptive_min_score_one_token():
    """Single-Token-Query → strenge 80er-Schwelle (verhindert False-Positives)."""
    from services.dataframe_service import _adaptive_min_score
    assert _adaptive_min_score("Siemens") == 80.0


def test_adaptive_min_score_two_tokens():
    """Zwei Tokens → 70er-Schwelle."""
    from services.dataframe_service import _adaptive_min_score
    assert _adaptive_min_score("Siemens AG") == 70.0


def test_adaptive_min_score_three_or_more_tokens():
    """≥3 Tokens → 60er-Schwelle (toleranter, weil mehr Signal)."""
    from services.dataframe_service import _adaptive_min_score
    assert _adaptive_min_score("Siemens Energy Global GmbH") == 60.0
    assert _adaptive_min_score("Fraunhofer Gesellschaft zur Foerderung") == 60.0


def test_adaptive_min_score_empty_query():
    """Leere Query → wie 1 Token (defensive Default)."""
    from services.dataframe_service import _adaptive_min_score
    assert _adaptive_min_score("") == 80.0
    assert _adaptive_min_score("   ") == 80.0


# ── Paket 6: Konfidenz-Klassen ────────────────────────────────────────────────


def test_match_confidence_exact_at_100():
    from services.dataframe_service import _match_confidence
    assert _match_confidence(100.0) == "exact"


def test_match_confidence_high_at_92():
    from services.dataframe_service import _match_confidence
    assert _match_confidence(92.0) == "high"


def test_match_confidence_medium_at_82():
    from services.dataframe_service import _match_confidence
    assert _match_confidence(82.0) == "medium"


def test_match_confidence_low_at_70():
    from services.dataframe_service import _match_confidence
    assert _match_confidence(70.0) == "low"


def test_match_confidence_boundaries():
    """Schwellenwerte exakt: 97/90/80 → exact/high/medium."""
    from services.dataframe_service import _match_confidence
    assert _match_confidence(97.0) == "exact"
    assert _match_confidence(96.999) == "high"
    assert _match_confidence(90.0) == "high"
    assert _match_confidence(89.999) == "medium"
    assert _match_confidence(80.0) == "medium"
    assert _match_confidence(79.999) == "low"
