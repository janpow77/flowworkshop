"""Multi-Source-Sanctions-Tests.

Testet `MultiSanctionsService` mit synthetischen CSV-Files, ohne Netzwerk-
oder DB-Abhaengigkeit. Drei Mini-CSV-Files in einem tmp-Verzeichnis
simulieren EU FSF, UN SC und OFAC SDN.

Werden im Container automatisch von pytest entdeckt (Pfad backend/tests/).
"""
from __future__ import annotations

import csv
import os
from pathlib import Path

import pytest

from services.sanctions_service import (
    DEFAULT_SANCTIONS_SOURCES,
    MultiSanctionsService,
    SanctionsListIndex,
    SanctionsSource,
    normalize_name,
)


# ── Test-Fixtures ────────────────────────────────────────────────────────────


_CSV_HEADERS = [
    "id", "schema", "name", "aliases", "birth_date", "countries",
    "addresses", "identifiers", "sanctions", "phones", "emails",
    "program_ids", "dataset", "first_seen", "last_seen", "last_change",
]


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_CSV_HEADERS)
        writer.writeheader()
        for row in rows:
            full = {h: "" for h in _CSV_HEADERS}
            full.update(row)
            writer.writerow(full)


@pytest.fixture
def synthetic_sources(tmp_path):
    """Erzeugt drei Mini-Sanctions-CSVs in tmp_path und liefert die zugehoerigen
    `SanctionsSource`-Objekte zurueck.
    """
    eu_csv = tmp_path / "eu_fsf.csv"
    un_csv = tmp_path / "un_sc.csv"
    ofac_csv = tmp_path / "ofac.csv"

    _write_csv(eu_csv, [
        {
            "id": "EU-001",
            "schema": "Person",
            "name": "Vladimir Vladimirovich Putin",
            "aliases": "Wladimir Putin;Путин Владимир",
            "birth_date": "1952-10-07",
            "countries": "ru",
            "sanctions": "EU UKR-2022/336",
        },
        {
            "id": "EU-002",
            "schema": "Organization",
            "name": "Acme Defense GmbH",
            "aliases": "Acme Defense Ltd",
            "countries": "de",
            "sanctions": "EU UKR-2024/100",
        },
    ])
    _write_csv(un_csv, [
        {
            "id": "UN-001",
            "schema": "Person",
            "name": "Vladimir V. Putin",
            "aliases": "Putin Vladimir Vladimirovich",
            "birth_date": "1952-10-07",
            "countries": "ru",
            "sanctions": "UN-Resolution 2231",
        },
        {
            "id": "UN-002",
            "schema": "Person",
            "name": "Kim Jong Un",
            "aliases": "Kim Jung-eun",
            "countries": "kp",
            "sanctions": "UNSC DPRK",
        },
    ])
    _write_csv(ofac_csv, [
        {
            "id": "OFAC-001",
            "schema": "Person",
            "name": "Putin, Vladimir",
            "aliases": "PUTIN, Vladimir Vladimirovich",
            "birth_date": "1952-10-07",
            "countries": "ru",
            "sanctions": "OFAC SDN — UKRAINE-EO13660",
        },
        {
            "id": "OFAC-002",
            "schema": "Organization",
            "name": "Sample Sanctioned Bank",
            "aliases": "SSB",
            "countries": "ru",
            "sanctions": "OFAC SDN — RUSSIA-EO14024",
        },
    ])

    sources = [
        SanctionsSource(
            key="eu_fsf",
            display_name="EU Konsolidierte Finanzsanktionsliste (FSF)",
            issuer="Europaeische Kommission",
            download_url="file:///dev/null",
            csv_path=str(eu_csv),
            license="CC BY 4.0",
        ),
        SanctionsSource(
            key="un_sc",
            display_name="UN Security Council Consolidated List",
            issuer="UN-Sicherheitsrat",
            download_url="file:///dev/null",
            csv_path=str(un_csv),
            license="Public Domain",
        ),
        SanctionsSource(
            key="us_ofac_sdn",
            display_name="OFAC SDN List",
            issuer="U.S. Treasury — OFAC",
            download_url="file:///dev/null",
            csv_path=str(ofac_csv),
            license="Public Domain",
        ),
    ]
    # ENV-Override durch SanctionsSource.__post_init__ vermeiden:
    # Pfade direkt nach __post_init__ wieder auf das tmp-Verzeichnis setzen.
    for s, p in zip(sources, [eu_csv, un_csv, ofac_csv]):
        s.csv_path = str(p)
    return sources


# ── Tests: Defaults + Single-Index ───────────────────────────────────────────


def test_default_sources_have_five_entries():
    """5 Default-Quellen: eu_fsf, un_sc, us_ofac_sdn, gb_hmt_sanctions, ch_seco."""
    keys = [s.key for s in DEFAULT_SANCTIONS_SOURCES]
    assert len(keys) == 5
    assert "eu_fsf" in keys
    assert "un_sc" in keys
    assert "us_ofac_sdn" in keys
    assert "gb_hmt_sanctions" in keys
    assert "ch_seco" in keys


def test_default_sources_have_required_fields():
    for s in DEFAULT_SANCTIONS_SOURCES:
        assert s.key
        assert s.display_name
        assert s.issuer
        assert s.download_url.startswith("https://data.opensanctions.org/")
        assert s.csv_path
        assert s.license


def test_normalize_name_strips_legal_suffix():
    assert normalize_name("Acme GmbH") == "acme"
    assert normalize_name("Mueller-Schmidt Ltd.") == "mueller schmidt"
    assert normalize_name("OOO Wassil") == "wassil"


def test_single_index_loads_synthetic(synthetic_sources):
    src = synthetic_sources[0]
    idx = SanctionsListIndex(src)
    idx.load()
    assert idx.is_loaded()
    stats = idx.stats()
    assert stats["source_key"] == "eu_fsf"
    assert stats["total_entries"] == 2
    assert stats["persons"] == 1
    assert stats["organizations"] == 1


def test_single_index_search_with_source_key(synthetic_sources):
    src = synthetic_sources[0]
    idx = SanctionsListIndex(src)
    idx.load()
    hits = idx.search("Putin", limit=5, min_score=70.0)
    assert len(hits) >= 1
    h = hits[0]
    # Treffer muessen Source-Key tragen
    assert h.source_key == "eu_fsf"
    assert h.source_display_name.startswith("EU Konsolidierte")


# ── Tests: MultiSanctionsService ─────────────────────────────────────────────


def test_multi_service_loads_all(synthetic_sources):
    svc = MultiSanctionsService(synthetic_sources)
    svc.load_all()
    assert svc.is_any_loaded()
    stats = svc.stats()
    # 2 + 2 + 2 = 6 Records ueber 3 Quellen
    assert stats["sources_total"] == 3
    assert stats["sources_loaded"] == 3
    assert stats["total_entries"] == 6
    per = {s["source_key"]: s for s in stats["per_source"]}
    assert per["eu_fsf"]["total_entries"] == 2
    assert per["un_sc"]["total_entries"] == 2
    assert per["us_ofac_sdn"]["total_entries"] == 2


def test_multi_service_search_aggregates(synthetic_sources):
    svc = MultiSanctionsService(synthetic_sources)
    svc.load_all()
    hits = svc.search("Putin", limit=20, min_score=70.0)
    # Drei Putin-Eintraege in EU + UN + OFAC, alle sollten matchen
    source_keys = {h.source_key for h in hits}
    assert "eu_fsf" in source_keys
    assert "un_sc" in source_keys
    assert "us_ofac_sdn" in source_keys
    # Jeder Treffer hat source_display_name
    for h in hits:
        assert h.source_display_name


def test_multi_service_search_filter_by_sources(synthetic_sources):
    svc = MultiSanctionsService(synthetic_sources)
    svc.load_all()
    # Filter: nur EU + UN — OFAC darf nicht im Ergebnis sein
    hits = svc.search(
        "Putin", limit=20, min_score=70.0,
        sources=["eu_fsf", "un_sc"],
    )
    source_keys = {h.source_key for h in hits}
    assert "eu_fsf" in source_keys
    assert "un_sc" in source_keys
    assert "us_ofac_sdn" not in source_keys


def test_multi_service_search_unknown_source_filter_returns_empty(synthetic_sources):
    """Filter auf unbekannte Source liefert leere Liste, kein Crash."""
    svc = MultiSanctionsService(synthetic_sources)
    svc.load_all()
    hits = svc.search("Putin", limit=20, sources=["does_not_exist"])
    assert hits == []


def test_multi_service_search_orders_by_score(synthetic_sources):
    svc = MultiSanctionsService(synthetic_sources)
    svc.load_all()
    hits = svc.search("Vladimir Putin", limit=20, min_score=60.0)
    # Top-Treffer sollte exact oder high sein
    if hits:
        scores = [h.score for h in hits]
        assert scores == sorted(scores, reverse=True)


def test_multi_service_missing_csv_does_not_crash(tmp_path):
    """Eine fehlende CSV-Datei darf den Service nicht zerlegen."""
    src = SanctionsSource(
        key="ghost",
        display_name="Nicht vorhanden",
        issuer="—",
        download_url="file:///dev/null",
        csv_path=str(tmp_path / "does_not_exist.csv"),
        license="—",
    )
    src.csv_path = str(tmp_path / "does_not_exist.csv")
    svc = MultiSanctionsService([src])
    svc.load_all()
    assert not svc.is_any_loaded()
    stats = svc.stats()
    assert stats["sources_loaded"] == 0
    assert stats["total_entries"] == 0
    # has_missing_csvs() muss True sein
    assert svc.has_missing_csvs()
    assert svc.missing_source_keys() == ["ghost"]


def test_multi_service_partial_load(synthetic_sources, tmp_path):
    """Mix aus vorhandenen und fehlenden Quellen: vorhandene werden geladen."""
    ghost = SanctionsSource(
        key="ghost",
        display_name="Ghost",
        issuer="—",
        download_url="file:///dev/null",
        csv_path=str(tmp_path / "ghost.csv"),
        license="—",
    )
    ghost.csv_path = str(tmp_path / "ghost.csv")
    svc = MultiSanctionsService(synthetic_sources + [ghost])
    svc.load_all()
    stats = svc.stats()
    assert stats["sources_total"] == 4
    assert stats["sources_loaded"] == 3
    assert stats["total_entries"] == 6
    assert svc.has_missing_csvs()
    assert "ghost" in svc.missing_source_keys()


def test_multi_service_stats_per_source_breakdown(synthetic_sources):
    svc = MultiSanctionsService(synthetic_sources)
    svc.load_all()
    stats = svc.stats()
    per_source = stats["per_source"]
    # Jeder Eintrag muss source_key, total_entries, persons, organizations haben
    for entry in per_source:
        assert "source_key" in entry
        assert "total_entries" in entry
        assert "persons" in entry
        assert "organizations" in entry
        assert "loaded" in entry


# ── Tests: Backward-Compat ───────────────────────────────────────────────────


def test_fsf_index_alias_still_works():
    """Backward-Compat: `FsfIndex` ist ein Alias auf `SanctionsListIndex`."""
    from services.sanctions_service import FsfIndex
    assert FsfIndex is SanctionsListIndex


def test_get_index_returns_eu_fsf_singleton(synthetic_sources, monkeypatch):
    """get_index() liefert den eu_fsf-Index — Backward-Compat fuer Bestandscode."""
    # Der Singleton-Test laeuft gegen die Default-Pfade; wir pruefen nur,
    # dass kein Crash auftritt und der Index das eu_fsf-Source-Objekt traegt.
    from services.sanctions_service import get_index
    idx = get_index()
    assert idx.source.key == "eu_fsf"


# ── Tests: Source-Filter gegen leere Quelle ──────────────────────────────────


def test_multi_service_search_empty_min_score_high(synthetic_sources):
    svc = MultiSanctionsService(synthetic_sources)
    svc.load_all()
    hits = svc.search("Mickey Mouse", limit=10, min_score=90.0)
    assert hits == []
