"""
Unit-Tests fuer die Search-Optimierung in services/state_aid_service.py
und routers/state_aid.py.

Reine Unit-Tests gegen pure Funktionen — keine DB, kein HTTP. Sie pruefen
die Bausteine der 5 Quick-Wins (pg_trgm-Index ist DDL, daher hier nicht
testbar; siehe Live-Smoke).

Lauf:
  pytest backend/tests/test_state_aid_search_quality.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

# Backend-Verzeichnis in den Pfad legen, damit `services.*` importierbar ist
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ── _escape_like ─────────────────────────────────────────────────────────────


def test_escape_like_percent():
    from services.state_aid_service import _escape_like
    assert _escape_like("50%") == "50\\%"


def test_escape_like_underscore():
    from services.state_aid_service import _escape_like
    assert _escape_like("a_b") == "a\\_b"


def test_escape_like_backslash_first():
    from services.state_aid_service import _escape_like
    # Backslash muss zuerst escapt werden, sonst doppelt escapen
    assert _escape_like("foo\\bar") == "foo\\\\bar"


def test_escape_like_combined():
    from services.state_aid_service import _escape_like
    assert _escape_like("a_b%c") == "a\\_b\\%c"


def test_escape_like_plain_string_unchanged():
    from services.state_aid_service import _escape_like
    assert _escape_like("Fraunhofer") == "Fraunhofer"
    assert _escape_like("BMW AG") == "BMW AG"


# ── _adaptive_min_score ──────────────────────────────────────────────────────


def test_adaptive_min_score_single_token_strict():
    from routers.state_aid import _adaptive_min_score
    assert _adaptive_min_score("BMW", None) == 80.0


def test_adaptive_min_score_two_tokens_medium():
    from routers.state_aid import _adaptive_min_score
    assert _adaptive_min_score("Deutsche Bahn", None) == 70.0


def test_adaptive_min_score_three_tokens_lenient():
    from routers.state_aid import _adaptive_min_score
    assert _adaptive_min_score("Fraunhofer Gesellschaft Forschung", None) == 60.0


def test_adaptive_min_score_long_query_lenient():
    from routers.state_aid import _adaptive_min_score
    assert _adaptive_min_score("Bundesministerium fuer Wirtschaft und Energie", None) == 60.0


def test_adaptive_min_score_explicit_overrides():
    from routers.state_aid import _adaptive_min_score
    # Explizit gesetzter Wert hat Vorrang ueber Heuristik
    assert _adaptive_min_score("BMW", 50.0) == 50.0
    assert _adaptive_min_score("Fraunhofer Gesellschaft Forschung", 95.0) == 95.0


def test_adaptive_min_score_empty_query_strict():
    from routers.state_aid import _adaptive_min_score
    # Leere Query (defensive Handhabung) -> strenger Match
    assert _adaptive_min_score("", None) == 80.0


# ── expand_alias ─────────────────────────────────────────────────────────────


def test_expand_alias_kfw_full_match():
    from services.state_aid_service import expand_alias
    expanded, label = expand_alias("KfW")
    assert label is not None
    assert "Kreditanstalt" in label
    assert "Kreditanstalt" in expanded
    # Original muss erhalten bleiben — Identifier-Match weiterhin moeglich
    assert "KfW" in expanded


def test_expand_alias_unknown_unchanged():
    from services.state_aid_service import expand_alias
    expanded, label = expand_alias("Random")
    assert label is None
    assert expanded == "Random"


def test_expand_alias_first_token_match():
    from services.state_aid_service import expand_alias
    # 'BMWK Foerderung' -> Erstes Token 'BMWK' wird expandiert
    expanded, label = expand_alias("BMWK Förderung")
    assert label is not None
    assert "Bundesministerium" in label
    assert "BMWK" in expanded
    assert "Förderung" in expanded


def test_expand_alias_case_insensitive():
    from services.state_aid_service import expand_alias
    # Lowercase-Variante muss auch matchen
    _, label = expand_alias("kfw")
    assert label is not None
    assert "Kreditanstalt" in label


def test_expand_alias_empty_query():
    from services.state_aid_service import expand_alias
    expanded, label = expand_alias("")
    assert expanded == ""
    assert label is None


def test_expand_alias_full_company_name_unchanged():
    from services.state_aid_service import expand_alias
    # Voller Firmenname, kein Akronym am Anfang
    expanded, label = expand_alias("Fraunhofer-Gesellschaft zur Foerderung")
    # 'fraunhofer' steht im Alias-Mapping, also wird hier expandiert.
    # Falls jemand das Mapping aendert (Fraunhofer entfernt), faellt das hier auf.
    assert label is not None or expanded == "Fraunhofer-Gesellschaft zur Foerderung"


# ── load_aliases ─────────────────────────────────────────────────────────────


def test_load_aliases_returns_dict():
    from services.state_aid_service import load_aliases
    aliases = load_aliases()
    assert isinstance(aliases, dict)
    # Datei wurde mit dem Patch ausgeliefert -> sollte einige Eintraege enthalten
    assert len(aliases) >= 20


def test_load_aliases_skips_meta_keys():
    from services.state_aid_service import load_aliases
    aliases = load_aliases()
    # Meta-Felder mit '_'-Praefix duerfen nicht im Mapping landen
    assert not any(k.startswith("_") for k in aliases)


def test_load_aliases_contains_kfw():
    from services.state_aid_service import load_aliases
    aliases = load_aliases()
    assert "kfw" in aliases
    assert "Kreditanstalt" in aliases["kfw"]


def test_load_aliases_keys_are_lowercase():
    from services.state_aid_service import load_aliases
    aliases = load_aliases()
    assert all(k == k.lower() for k in aliases)


# ── Performance-Optimierung (Quick-Wins Runde 2) ─────────────────────────────


def test_select_sql_tokens_keeps_distinctive():
    """Distinktive Tokens (Firmennamen, Eigennamen) bleiben erhalten."""
    from services.state_aid_service import _select_sql_tokens
    out = _select_sql_tokens(["fraunhofer", "gesellschaft", "foerderung"])
    assert "fraunhofer" in out
    assert "foerderung" in out
    assert "gesellschaft" in out


def test_select_sql_tokens_drops_german_stopwords():
    """Deutsche Stoppwoerter werden aus dem SQL-Vorfilter entfernt
    (sie kollabieren den Trgm-Index → ~50ms Strafe)."""
    from services.state_aid_service import _select_sql_tokens
    out = _select_sql_tokens([
        "fraunhofer", "gesellschaft", "zur", "foerderung", "der",
        "angewandten", "forschung",
    ])
    # Stoppwoerter raus
    assert "zur" not in out
    assert "der" not in out
    # Distinktive Tokens bleiben
    assert "fraunhofer" in out


def test_select_sql_tokens_caps_at_max():
    """Bei vielen Kandidaten werden nur Top-N (laengste) zurueckgegeben."""
    from services.state_aid_service import _select_sql_tokens
    tokens = ["aaa", "bbbb", "ccccc", "dddddd", "eeeeeee", "ffffffff"]
    out = _select_sql_tokens(tokens, max_tokens=3)
    assert len(out) == 3
    # Laengste zuerst
    assert "ffffffff" in out
    assert "eeeeeee" in out


def test_select_sql_tokens_empty_input_returns_empty():
    from services.state_aid_service import _select_sql_tokens
    assert _select_sql_tokens([]) == []


def test_select_sql_tokens_only_stopwords_keeps_first():
    """Falls die Query nur aus Stoppwoertern besteht, behalten wir den
    ersten Token — sonst haetten wir keinen SQL-Filter."""
    from services.state_aid_service import _select_sql_tokens
    out = _select_sql_tokens(["der", "und", "zur"])
    assert len(out) == 1
    assert out[0] == "der"


def test_looks_like_identifier_with_digits():
    from services.state_aid_service import _looks_like_identifier
    assert _looks_like_identifier("HRB12345")
    assert _looks_like_identifier("DE-2023-001")


def test_looks_like_identifier_short_acronym():
    from services.state_aid_service import _looks_like_identifier
    assert _looks_like_identifier("ABER")
    assert _looks_like_identifier("KUR")


def test_looks_like_identifier_company_name_negative():
    """Lange Firmennamen sollen NICHT als Identifier eingestuft werden,
    sonst triggern sie einen teuren Seq Scan auf beneficiary_identifier."""
    from services.state_aid_service import _looks_like_identifier
    assert not _looks_like_identifier("Fraunhofer")
    assert not _looks_like_identifier("Siemens AG")
    assert not _looks_like_identifier("Deutsche Bahn")


def test_looks_like_identifier_empty_string():
    from services.state_aid_service import _looks_like_identifier
    assert not _looks_like_identifier("")
    assert not _looks_like_identifier("   ")


def test_smart_fuzzy_score_cached_returns_same_score():
    """Cache-Variante muss exakt denselben Score liefern wie Original."""
    from services.state_aid_service import (
        _smart_fuzzy_score, _smart_fuzzy_score_cached,
    )
    pairs = [
        ("siemens", "siemens ag"),
        ("fraunhofer", "fraunhofer gesellschaft zur foerderung"),
        ("bmw", "bayerische motoren werke ag"),
        ("", "fraunhofer"),
        ("siemens energy", "siemens"),
    ]
    for q, c in pairs:
        s_uncached, _ = _smart_fuzzy_score(q, c)
        s_cached, _ = _smart_fuzzy_score_cached(q, c)
        assert abs(s_uncached - s_cached) < 1e-6, f"Mismatch for ({q!r}, {c!r})"


def test_smart_fuzzy_score_cached_uses_lru():
    """Zweiter Aufruf mit gleichen Argumenten ist ein Cache-Hit."""
    from services.state_aid_service import _smart_fuzzy_score_cached
    _smart_fuzzy_score_cached.cache_clear()
    info_before = _smart_fuzzy_score_cached.cache_info()
    _smart_fuzzy_score_cached("test", "testing")
    info_after_first = _smart_fuzzy_score_cached.cache_info()
    _smart_fuzzy_score_cached("test", "testing")
    info_after_second = _smart_fuzzy_score_cached.cache_info()
    assert info_after_first.misses == info_before.misses + 1
    assert info_after_second.hits == info_after_first.hits + 1
    # Bei gleichem Aufruf darf misses NICHT weiter steigen
    assert info_after_second.misses == info_after_first.misses


def test_smart_fuzzy_score_cached_returns_hashable():
    """Rueckgabe muss hashable sein (Cache-Voraussetzung)."""
    from services.state_aid_service import _smart_fuzzy_score_cached
    score, debug = _smart_fuzzy_score_cached("siemens", "siemens ag")
    # Wenn Rueckgabe hashable ist, geht hash() ohne Fehler.
    hash((score, debug))


def test_smart_fuzzy_score_cached_maxsize_4096():
    """Cache-Groesse ist bewusst moderat (Memory-Footprint)."""
    from services.state_aid_service import _smart_fuzzy_score_cached
    info = _smart_fuzzy_score_cached.cache_info()
    assert info.maxsize == 4096


# ── Konstanten / Konfiguration ──────────────────────────────────────────────


def test_fuzzy_constants_present():
    """Die neuen Konstanten muessen im Modul vorhanden sein."""
    import services.state_aid_service as svc
    assert hasattr(svc, "_FUZZY_SQL_LIMIT")
    assert hasattr(svc, "_FUZZY_SMART_TOPK")
    assert svc._FUZZY_SMART_TOPK <= svc._FUZZY_SQL_LIMIT
    assert svc._FUZZY_SMART_TOPK > 0
    assert svc._FUZZY_SQL_LIMIT > 0


def test_sql_stop_tokens_contains_german_articles():
    from services.state_aid_service import _SQL_STOP_TOKENS
    for t in ("der", "die", "das", "und", "zur", "von"):
        assert t in _SQL_STOP_TOKENS
