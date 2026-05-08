"""
Unit-Tests fuer NUTS-3-Aufloesung (DE + AT) im State-Aid-Service.

Reine Unit-Tests, kein TAM-Request, keine HTTP-Anfragen. Tests laufen direkt
gegen `services.state_aid_service` und benoetigen die JSON-Lookup-Dateien
unter `/app/data/nuts_*.json`. Im Container und in der Quellbaum-Struktur
existieren diese.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Backend-Verzeichnis in den Pfad legen, damit `services.*` importierbar ist
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ── DE NUTS-3-Aufloesung ─────────────────────────────────────────────────────


def test_derive_nuts_code_de_muenchen_to_de212():
    """München (Stadt) → NUTS-3 DE212, Level 3."""
    from services.state_aid_service import derive_nuts_code, load_nuts3_de_lookup
    if not load_nuts3_de_lookup():
        import pytest
        pytest.skip("nuts_de.json nicht verfuegbar (Lookup leer).")
    code, level = derive_nuts_code(region_label="München", country_iso2="DE")
    assert code == "DE212", f"Erwartet DE212, bekommen {code}"
    assert level == 3


def test_derive_nuts_code_de_bonn_to_dea22():
    """Bonn (Stadt) → NUTS-3 DEA22, Level 3."""
    from services.state_aid_service import derive_nuts_code, load_nuts3_de_lookup
    if not load_nuts3_de_lookup():
        import pytest
        pytest.skip("nuts_de.json nicht verfuegbar (Lookup leer).")
    code, level = derive_nuts_code(region_label="Bonn", country_iso2="DE")
    assert code == "DEA22", f"Erwartet DEA22, bekommen {code}"
    assert level == 3


def test_derive_nuts_code_de_kreis_with_suffix():
    """'München, Kreisfreie Stadt' → DE212 (Komma-Variante via Strip-Suffix)."""
    from services.state_aid_service import derive_nuts_code, load_nuts3_de_lookup
    if not load_nuts3_de_lookup():
        import pytest
        pytest.skip("nuts_de.json nicht verfuegbar.")
    code, level = derive_nuts_code(
        region_label="München, Kreisfreie Stadt", country_iso2="DE"
    )
    assert code == "DE212"
    assert level == 3


def test_derive_nuts_code_de_bundesland_still_level1():
    """'Bayern' bleibt NUTS-1 (Level 1) — Stufen-Reihenfolge respektiert."""
    from services.state_aid_service import derive_nuts_code
    code, level = derive_nuts_code(region_label="Bayern", country_iso2="DE")
    assert code == "DE2"
    assert level == 1


# ── AT NUTS-3-Aufloesung ─────────────────────────────────────────────────────


def test_derive_nuts_code_at_wien_to_at130():
    """Wien → AT130 (NUTS-3 Wien); priorisiert vor AT13 NUTS-2."""
    from services.state_aid_service import derive_nuts_code, load_nuts3_at_lookup
    if not load_nuts3_at_lookup():
        import pytest
        pytest.skip("nuts_at.json nicht verfuegbar.")
    code, level = derive_nuts_code(region_label="Wien", country_iso2="AT")
    assert code == "AT130"
    assert level == 3


def test_derive_nuts_code_at_salzburg_und_umgebung():
    """'Salzburg und Umgebung' → AT323 (NUTS-3)."""
    from services.state_aid_service import derive_nuts_code, load_nuts3_at_lookup
    if not load_nuts3_at_lookup():
        import pytest
        pytest.skip("nuts_at.json nicht verfuegbar.")
    code, level = derive_nuts_code(
        region_label="Salzburg und Umgebung", country_iso2="AT"
    )
    assert code == "AT323"
    assert level == 3


def test_derive_nuts_code_at_oststeiermark_to_at224():
    """'Oststeiermark' (typischer TAM-Bezeichner) → AT224."""
    from services.state_aid_service import derive_nuts_code, load_nuts3_at_lookup
    if not load_nuts3_at_lookup():
        import pytest
        pytest.skip("nuts_at.json nicht verfuegbar.")
    code, level = derive_nuts_code(region_label="Oststeiermark", country_iso2="AT")
    assert code == "AT224"
    assert level == 3


def test_derive_nuts_code_at_linz_wels():
    """'Linz-Wels' → AT312 (NUTS-3)."""
    from services.state_aid_service import derive_nuts_code, load_nuts3_at_lookup
    if not load_nuts3_at_lookup():
        import pytest
        pytest.skip("nuts_at.json nicht verfuegbar.")
    code, level = derive_nuts_code(region_label="Linz-Wels", country_iso2="AT")
    assert code == "AT312"
    assert level == 3


def test_derive_nuts_code_at_wiener_umland_nordteil():
    """'Wiener Umland/Nordteil' (mit Slash) → AT126."""
    from services.state_aid_service import derive_nuts_code, load_nuts3_at_lookup
    if not load_nuts3_at_lookup():
        import pytest
        pytest.skip("nuts_at.json nicht verfuegbar.")
    code, level = derive_nuts_code(
        region_label="Wiener Umland/Nordteil", country_iso2="AT"
    )
    assert code == "AT126"
    assert level == 3


def test_derive_nuts_code_at_bundesland_nuts2_match():
    """'Tirol' (Bundesland-Begriff, kein NUTS-3-Bezirk) bleibt AT33 NUTS-2."""
    from services.state_aid_service import derive_nuts_code
    code, level = derive_nuts_code(region_label="Tirol", country_iso2="AT")
    # 'Tirol' ist kein NUTS-3-Name, sondern Bundesland → AT33 Level 2
    assert code == "AT33"
    assert level == 2


def test_derive_nuts_code_at_steiermark_bundesland():
    """'Steiermark' (Bundesland) bleibt AT22 Level 2 (kein NUTS-3-Konflikt)."""
    from services.state_aid_service import derive_nuts_code
    code, level = derive_nuts_code(region_label="Steiermark", country_iso2="AT")
    assert code == "AT22"
    assert level == 2


# ── Lookup-Dictionary-Inhalt ─────────────────────────────────────────────────


def test_load_nuts3_at_lookup_contains_35_codes():
    """Es muessen alle 35 AT-NUTS-3-Codes registriert sein."""
    from services.state_aid_service import load_nuts3_at_lookup
    lookup = load_nuts3_at_lookup()
    if not lookup:
        import pytest
        pytest.skip("nuts_at.json nicht verfuegbar.")
    distinct_codes = {v for v in lookup.values() if len(v) == 5 and v.startswith("AT")}
    assert len(distinct_codes) == 35, (
        f"Erwartet 35 NUTS-3-Codes fuer AT, gefunden {len(distinct_codes)}: {sorted(distinct_codes)}"
    )


def test_load_nuts3_de_lookup_contains_401_codes():
    """Es muessen alle 401 DE-NUTS-3-Kreise registriert sein."""
    from services.state_aid_service import load_nuts3_de_lookup
    lookup = load_nuts3_de_lookup()
    if not lookup:
        import pytest
        pytest.skip("nuts_de.json nicht verfuegbar.")
    distinct_codes = {v for v in lookup.values() if len(v) == 5 and v.startswith("DE")}
    assert len(distinct_codes) == 401, (
        f"Erwartet 401 NUTS-3-Codes fuer DE, gefunden {len(distinct_codes)}"
    )


# ── Prefix-Verhalten der Suche ───────────────────────────────────────────────


def test_router_prefix_match_filter_de2_matches_de212():
    """`_apply_award_filters` mit nuts_code='DE2' baut LIKE 'DE2%' und matcht
    sowohl DE2, DE21 als auch DE212.

    Wir testen das ohne echte DB ueber den Query-Builder + die SQL-Kompilation.
    SQLAlchemy escaped das einzelne `%` beim Bind-Render zu `%%`, weil das
    Statement von DBAPIs als Format-String gelesen werden kann — der
    Wildcard-Wirkung im Postgres-LIKE ist davon nicht betroffen.
    """
    from sqlalchemy.dialects import postgresql
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from models.state_aid import StateAidAward
    from routers.state_aid import _apply_award_filters

    # In-Memory-Engine reicht — wir kompilieren nur das Statement
    engine = create_engine("sqlite:///:memory:")
    session = sessionmaker(bind=engine)()
    try:
        q = session.query(StateAidAward)
        q = _apply_award_filters(q, nuts_code="DE2")
        compiled = str(
            q.statement.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
        # Beide Schreibweisen akzeptieren — abhaengig vom paramstyle des
        # Dialekts wird `%` ggf. zu `%%` doppelt-escaped.
        assert (
            "nuts_code LIKE 'DE2%'" in compiled
            or "nuts_code LIKE 'DE2%%'" in compiled
        ), f"Erwartet LIKE-Prefix-Match auf DE2%, bekommen:\n{compiled}"
    finally:
        session.close()


def test_centroid_for_at_nuts3_falls_back_to_nuts2():
    """`centroid_for('AT322')` muss einen Wert liefern (entweder AT322
    direkt aus nuts_at.json oder per Trim auf AT32)."""
    from services.state_aid_service import centroid_for
    result = centroid_for("AT322")
    assert result is not None
    lat, lon, label = result
    assert isinstance(lat, float) and isinstance(lon, float)
    assert label  # nicht-leer


def test_centroid_for_de_nuts3_munich():
    """DE212 muss aus nuts_de.json eine Stadt-Koordinate liefern."""
    from services.state_aid_service import centroid_for
    result = centroid_for("DE212")
    assert result is not None
    lat, lon, _ = result
    # München liegt grob bei 48.13, 11.58
    assert 47.5 < lat < 48.5
    assert 11.0 < lon < 12.0
