"""
Unit-Tests fuer services/state_aid_service.py — Normalisierung,
Betrag-Parsing, SA-Referenz-Erkennung, NUTS-Lookup, Country-Codes.

Reine Unit-Tests, kein TAM-Request, keine DB-Verbindung noetig.
Lauf: pytest backend/tests/test_state_aid_normalize.py -q
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

# Backend-Verzeichnis in den Pfad legen, damit `services.*` importierbar ist
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ── parse_amount: GBER + EU-Formate ───────────────────────────────────────────


def test_parse_amount_simple_us_format():
    from services.state_aid_service import parse_amount
    assert parse_amount("1,200,000") == Decimal("1200000")


def test_parse_amount_simple_de_format():
    from services.state_aid_service import parse_amount
    assert parse_amount("1.200.000,00") == Decimal("1200000.00")


def test_parse_amount_with_eur_prefix():
    from services.state_aid_service import parse_amount
    assert parse_amount("EUR 250.000,50") == Decimal("250000.50")


def test_parse_amount_with_currency_symbol():
    from services.state_aid_service import parse_amount
    assert parse_amount("€ 12 345,67") == Decimal("12345.67")


def test_parse_amount_nbsp_whitespace():
    from services.state_aid_service import parse_amount
    # Geschuetztes Leerzeichen (NBSP) als Tausendertrenner
    assert parse_amount("1 200 000") == Decimal("1200000")


def test_parse_amount_gber_range_takes_upper_bound():
    from services.state_aid_service import parse_amount
    # GBER-Spannen: oberer Grenzwert wird konservativ uebernommen
    assert parse_amount("500,001 to 1,000,000") == Decimal("1000000")


def test_parse_amount_less_than():
    from services.state_aid_service import parse_amount
    assert parse_amount("less than 100,000") == Decimal("100000")
    assert parse_amount("< 50,000") == Decimal("50000")


def test_parse_amount_more_than():
    from services.state_aid_service import parse_amount
    assert parse_amount("more than 30 000 000") == Decimal("30000000")
    assert parse_amount("> 5,000") == Decimal("5000")


def test_parse_amount_dash_means_none():
    from services.state_aid_service import parse_amount
    assert parse_amount("-") is None
    assert parse_amount("—") is None
    assert parse_amount("") is None
    assert parse_amount(None) is None


def test_parse_amount_decimal_separator_heuristic():
    from services.state_aid_service import parse_amount
    # Komma-mit-genau-2-Nachkomma → Dezimaltrenner
    assert parse_amount("123,45") == Decimal("123.45")
    # Komma-mit-mehreren-Stellen ohne Punkt → Tausender
    assert parse_amount("123,456") == Decimal("123456")


# ── detect_sa_reference ──────────────────────────────────────────────────────


def test_detect_sa_reference_basic():
    from services.state_aid_service import detect_sa_reference
    norm, url = detect_sa_reference("Beihilfe SA.12345 Maßnahme")
    assert norm == "SA.12345"
    assert url and "SA.12345" in url


def test_detect_sa_reference_with_year_suffix():
    from services.state_aid_service import detect_sa_reference
    norm, url = detect_sa_reference("siehe Verfahren SA.54321/2023")
    assert norm == "SA.54321/2023"
    assert url and "SA.54321/2023" in url


def test_detect_sa_reference_alt_separators():
    from services.state_aid_service import detect_sa_reference
    norm, _ = detect_sa_reference("ref: SA 99001")
    assert norm == "SA.99001"
    norm2, _ = detect_sa_reference("SA-78901")
    assert norm2 == "SA.78901"


def test_detect_sa_reference_no_match():
    from services.state_aid_service import detect_sa_reference
    assert detect_sa_reference("Keine Referenz hier") == (None, None)
    assert detect_sa_reference("") == (None, None)
    assert detect_sa_reference(None) == (None, None)


def test_detect_sa_reference_does_not_match_random_sa():
    from services.state_aid_service import detect_sa_reference
    # 3-stellige Zahl reicht laut Regex nicht (>=4 Stellen)
    assert detect_sa_reference("SA.12") == (None, None)
    assert detect_sa_reference("Saarland") == (None, None)


# ── normalize_company_name ────────────────────────────────────────────────────


def test_normalize_company_name_strips_legal_form():
    from services.state_aid_service import normalize_company_name
    assert normalize_company_name("Müller GmbH") == "mueller"


def test_normalize_company_name_handles_co_kg():
    from services.state_aid_service import normalize_company_name
    out = normalize_company_name("Müller GmbH & Co. KG")
    # 'und' aus '&' bleibt drin, GmbH/Co/KG raus
    assert "mueller" in out
    assert "gmbh" not in out
    assert "kg" not in out


def test_normalize_company_name_drops_filler_optional():
    from services.state_aid_service import normalize_company_name
    base = normalize_company_name("ACME Holding Deutschland GmbH")
    assert base == "acme holding deutschland"
    stripped = normalize_company_name("ACME Holding Deutschland GmbH", drop_filler=True)
    # filler 'holding' und 'deutschland' weg
    assert stripped == "acme"


def test_normalize_company_name_empty():
    from services.state_aid_service import normalize_company_name
    assert normalize_company_name("") == ""
    assert normalize_company_name(None) == ""


# ── derive_nuts_code ──────────────────────────────────────────────────────────


def test_derive_nuts_code_de_bundeslaender():
    from services.state_aid_service import derive_nuts_code
    code, level = derive_nuts_code(region_label="Hessen", country_iso2="DE")
    assert code == "DE7"
    assert level == 1
    code2, _ = derive_nuts_code(region_label="Nordrhein-Westfalen", country_iso2="DE")
    assert code2 == "DEA"
    code3, _ = derive_nuts_code(region_label="Bayern", country_iso2="DE")
    assert code3 == "DE2"


def test_derive_nuts_code_at_bundeslaender():
    from services.state_aid_service import derive_nuts_code
    # Wien ist gleichzeitig Bundesland (NUTS-2 AT13) und Politischer Bezirk
    # (NUTS-3 AT130). Phase-3-Hardening loest auf NUTS-3 auf.
    code, level = derive_nuts_code(region_label="Wien", country_iso2="AT")
    assert code in ("AT13", "AT130")
    assert level in (2, 3)
    code2, _ = derive_nuts_code(region_label="Oberösterreich", country_iso2="AT")
    assert code2 == "AT31"
    code3, _ = derive_nuts_code(region_label="Steiermark", country_iso2="AT")
    assert code3 == "AT22"


def test_derive_nuts_code_fallback_to_country():
    from services.state_aid_service import derive_nuts_code
    # Ohne Region → Land-Level
    code, level = derive_nuts_code(region_label=None, country_iso2="DE")
    assert code == "DE"
    assert level == 0


def test_derive_nuts_code_unknown_region_falls_back_to_country():
    from services.state_aid_service import derive_nuts_code
    code, level = derive_nuts_code(region_label="Atlantis", country_iso2="DE")
    assert code == "DE"
    assert level == 0


def test_derive_nuts_code_empty_inputs():
    from services.state_aid_service import derive_nuts_code
    code, level = derive_nuts_code(region_label=None, country_iso2=None)
    assert code is None and level is None


# ── normalize_country_code ────────────────────────────────────────────────────


def test_normalize_country_code_iso3():
    from services.state_aid_service import normalize_country_code
    iso2, name = normalize_country_code("DEU")
    assert iso2 == "DE"
    assert name and "eutsch" in name.lower()


def test_normalize_country_code_iso2():
    from services.state_aid_service import normalize_country_code
    iso2, name = normalize_country_code("AT")
    assert iso2 == "AT"
    assert name


def test_normalize_country_code_full_name():
    from services.state_aid_service import normalize_country_code
    iso2, name = normalize_country_code("Deutschland")
    assert iso2 == "DE"
    assert name == "Deutschland"


def test_normalize_country_code_empty():
    from services.state_aid_service import normalize_country_code
    assert normalize_country_code("") == (None, None)
    assert normalize_country_code(None) == (None, None)


def test_normalize_country_code_unknown_returns_original():
    from services.state_aid_service import normalize_country_code
    iso2, name = normalize_country_code("Atlantis")
    assert iso2 is None
    assert name == "Atlantis"
