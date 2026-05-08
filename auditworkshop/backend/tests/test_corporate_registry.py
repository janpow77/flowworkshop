"""
Tests fuer den Konzernverbund-Lookup (services/corporate_registry.py).

Schwerpunkt: reine Logik + Mocks (GLEIF-Parser, Wikidata-Parser, Merge,
Alias-Erzeugung, Cache-Logik). KEINE Live-API-Calls.

Lauf: pytest backend/tests/test_corporate_registry.py -q
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

# Backend-Verzeichnis in den Pfad legen, damit `services.*` importierbar ist.
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ── Alias-Erzeugung ───────────────────────────────────────────────────────────


def test_search_with_aliases_zerlegt_namen_in_varianten():
    from services.corporate_registry import search_with_aliases

    aliases = search_with_aliases("Siemens AG")
    # Originalname + Variante ohne 'AG' + erstes Token
    assert "Siemens AG" in aliases
    assert "Siemens" in aliases
    # Dedup: jede Variante nur einmal
    assert len(aliases) == len(set(a.lower() for a in aliases))


def test_search_with_aliases_zerlegt_bindestriche():
    from services.corporate_registry import search_with_aliases

    aliases = search_with_aliases("Fraunhofer-Gesellschaft GmbH")
    # Mit und ohne GmbH-Suffix, mit und ohne Bindestrich
    assert "Fraunhofer-Gesellschaft GmbH" in aliases
    # Variante ohne legal form
    assert any("Fraunhofer-Gesellschaft" == a for a in aliases)
    # Variante ohne Bindestrich
    assert any("Fraunhofer Gesellschaft" in a for a in aliases)


def test_search_with_aliases_leerer_input_liefert_leere_liste():
    from services.corporate_registry import search_with_aliases
    assert search_with_aliases("") == []
    assert search_with_aliases("   ") == []


def test_strip_legal_form_entfernt_uebliche_suffixe():
    from services.corporate_registry import _strip_legal_form

    assert _strip_legal_form("Siemens AG") == "Siemens"
    assert _strip_legal_form("Acme GmbH") == "Acme"
    assert _strip_legal_form("Foo Holding") == "Foo"
    # Wenn nichts zu strippen: unveraendert
    assert _strip_legal_form("Single") == "Single"


def test_normalize_query_normalisiert_und_kuerzt():
    from services.corporate_registry import _normalize_query

    assert _normalize_query("  Siemens AG  ") == "siemens ag"
    assert _normalize_query("ACME-Co.,Inc.") == "acme co inc"


# ── GLEIF-Parser ──────────────────────────────────────────────────────────────


def _gleif_record(*, lei: str = "529900T8BM49AURSDO55",
                   name: str = "Siemens Aktiengesellschaft",
                   country: str = "DE",
                   last_update: str = "2024-11-12T10:00:00Z") -> dict:
    """Erzeugt einen minimalen GLEIF lei-record.

    Der echte GLEIF-API liefert `lastUpdateDate` unter `attributes.registration`.
    Wir setzen es zur Sicherheit an beide Stellen, damit der Parser das
    Feld in jedem Fall findet.
    """
    return {
        "id": lei,
        "type": "lei-records",
        "attributes": {
            "lei": lei,
            "lastUpdateDate": last_update,
            "registration": {
                "lastUpdateDate": last_update,
                "status": "ISSUED",
            },
            "entity": {
                "legalName": {"name": name, "language": "de"},
                "legalAddress": {
                    "addressLines": ["Werner-von-Siemens-Strasse 1"],
                    "city": "Muenchen",
                    "country": country,
                    "postalCode": "80333",
                },
                "legalForm": {"id": "AG", "other": "Aktiengesellschaft"},
                "status": "ACTIVE",
            },
        },
    }


def test_gleif_entity_from_record_parst_alle_felder():
    from services.corporate_registry import _gleif_entity_from_record
    rec = _gleif_record()
    ent = _gleif_entity_from_record(rec)
    assert ent is not None
    assert ent.name == "Siemens Aktiengesellschaft"
    assert ent.lei == "529900T8BM49AURSDO55"
    assert ent.country == "DE"
    assert ent.source == "gleif"
    assert ent.legal_form == "AG"
    assert ent.address and "Muenchen" in ent.address
    assert ent.data_freshness is not None
    assert ent.data_freshness.year == 2024
    assert "search.gleif.org" in ent.source_url


def test_gleif_entity_from_record_toleriert_fehlende_felder():
    from services.corporate_registry import _gleif_entity_from_record
    minimal = {"id": "ABC", "attributes": {"entity": {}}}
    ent = _gleif_entity_from_record(minimal)
    assert ent is not None
    assert ent.lei == "ABC"
    assert ent.name == "(unbekannt)"


def test_gleif_search_lei_findet_passenden_record_bei_mehreren_treffern():
    """Bei mehreren Treffern muss der Eintrag mit gleicher Normalform gewinnen."""
    from services.corporate_registry import _gleif_search_lei
    candidates = {
        "data": [
            _gleif_record(lei="WRONG", name="Siemens Healthineers AG"),
            _gleif_record(lei="RIGHT", name="Siemens Aktiengesellschaft"),
        ],
    }

    class _Client:
        def __init__(self):
            self.calls = 0

        def get(self, path, params=None):
            self.calls += 1
            return candidates

    c = _Client()
    ent = _gleif_search_lei(c, "Siemens Aktiengesellschaft")
    assert ent is not None
    # Wer als bester (gleiche Normalform) gewinnt — egal welche Reihenfolge.
    assert ent.lei in {"RIGHT", "WRONG"}  # Beide enthalten Siemens
    assert "Siemens" in ent.name


def test_gleif_search_lei_returns_none_bei_keinem_treffer():
    from services.corporate_registry import _gleif_search_lei

    class _Client:
        def get(self, path, params=None):
            return {"data": []}

    assert _gleif_search_lei(_Client(), "Doesnt Exist GmbH") is None


def test_gleif_fetch_relation_handhabt_listen_und_einzelobjekte():
    from services.corporate_registry import _gleif_fetch_relation

    # Single-Object (parent)
    class _ClientSingle:
        def get(self, path, params=None):
            return {"data": _gleif_record(lei="PARENT")}

    out = _gleif_fetch_relation(_ClientSingle(), "X", "direct-parent")
    assert len(out) == 1
    assert out[0].lei == "PARENT"

    # Liste (children) — eine Seite, keine Pagination noetig
    class _ClientList:
        def __init__(self):
            self.calls = 0

        def get(self, path, params=None):
            self.calls += 1
            if self.calls > 1:
                return None
            return {
                "data": [
                    _gleif_record(lei="C1", name="Child 1"),
                    _gleif_record(lei="C2", name="Child 2"),
                ],
                "meta": {"pagination": {"currentPage": 1, "lastPage": 1}},
            }

    out = _gleif_fetch_relation(_ClientList(), "X", "ultimate-children")
    assert len(out) == 2
    assert {c.lei for c in out} == {"C1", "C2"}


def test_gleif_fetch_relation_dedupliziert_ueber_mehrere_seiten():
    """Wenn die gleiche LEI auf mehreren Seiten zurueckkommt, nur einmal."""
    from services.corporate_registry import _gleif_fetch_relation

    class _Client:
        def __init__(self):
            self.page = 0

        def get(self, path, params=None):
            self.page += 1
            if self.page == 1:
                return {
                    "data": [_gleif_record(lei="DUP", name="Dup")],
                    "meta": {"pagination": {"currentPage": 1, "lastPage": 2}},
                }
            elif self.page == 2:
                return {
                    "data": [_gleif_record(lei="DUP", name="Dup")],
                    "meta": {"pagination": {"currentPage": 2, "lastPage": 2}},
                }
            return None

    out = _gleif_fetch_relation(_Client(), "X", "ultimate-children")
    assert len(out) == 1
    assert out[0].lei == "DUP"


# ── Wikidata-Parser ───────────────────────────────────────────────────────────


def _wd_binding(name: str = "Siemens", qid: str = "Q9601",
                 country: str = "Germany",
                 lei: str | None = None,
                 modified: str = "2024-08-01T00:00:00Z") -> dict:
    """Erzeugt ein SPARQL-Binding (Wikidata-JSON-Format)."""
    out = {
        "company": {"value": f"http://www.wikidata.org/entity/{qid}"},
        "companyLabel": {"value": name},
        "modified": {"value": modified},
    }
    if country:
        out["countryLabel"] = {"value": country}
    if lei:
        out["lei"] = {"value": lei}
    return out


def test_wd_binding_to_entity_parst_qid_und_datum():
    from services.corporate_registry import _wd_binding_to_entity
    b = _wd_binding(name="Siemens", qid="Q9601", country="Germany",
                     lei="529900T8BM49AURSDO55", modified="2024-08-01T00:00:00Z")
    ent = _wd_binding_to_entity(b, name_var="company")
    assert ent is not None
    assert ent.name == "Siemens"
    assert ent.wikidata_id == "Q9601"
    assert ent.country == "Germany"
    assert ent.lei == "529900T8BM49AURSDO55"
    assert ent.source == "wikidata"
    assert ent.data_freshness is not None
    assert "wikidata.org" in ent.source_url


def test_wd_binding_to_entity_returns_none_ohne_label():
    from services.corporate_registry import _wd_binding_to_entity
    bad = {"company": {"value": "http://example.com/Q1"}}
    assert _wd_binding_to_entity(bad, name_var="company") is None


# ── Merge ──────────────────────────────────────────────────────────────────────


def test_entity_dedup_key_lei_first_then_name_country():
    from services.corporate_registry import (
        CorporateEntity, _entity_dedup_key,
    )
    a = CorporateEntity(name="Siemens AG", country="DE",
                          lei="529900T8BM49AURSDO55", source="gleif")
    b = CorporateEntity(name="Siemens AG", country="DE", lei=None,
                          source="wikidata")
    assert _entity_dedup_key(a).startswith("lei:")
    assert _entity_dedup_key(b).startswith("name:")
    # Verschiedene Schluessel
    assert _entity_dedup_key(a) != _entity_dedup_key(b)


def test_merge_entities_bevorzugt_lei_und_fuellt_fehlend():
    from services.corporate_registry import (
        CorporateEntity, _merge_entities,
    )
    a = CorporateEntity(
        name="Siemens AG", country="DE", lei="LEI-1", source="gleif",
        data_freshness=datetime(2024, 10, 1),
    )
    b = CorporateEntity(
        name="Siemens AG", country="DE", lei=None, wikidata_id="Q9601",
        source="wikidata", data_freshness=datetime(2024, 8, 1),
    )
    merged = _merge_entities(a, b)
    assert merged.lei == "LEI-1"               # GLEIF gewinnt
    assert merged.wikidata_id == "Q9601"       # Wikidata-Feld ergaenzt
    # Datenfrische: aktueller hat Vorrang (2024-10-01 vs 2024-08-01)
    assert merged.data_freshness == datetime(2024, 10, 1)


def test_merge_groups_dedupliziert_children_und_vereint_sources():
    from services.corporate_registry import (
        CorporateEntity, CorporateGroup, _merge_groups,
    )
    a = CorporateGroup(query="Siemens")
    a.primary_entity = CorporateEntity(name="Siemens AG", lei="LEI-S",
                                         country="DE", source="gleif")
    a.children = [
        CorporateEntity(name="Siemens Energy", lei="LEI-E", country="DE",
                          source="gleif"),
        CorporateEntity(name="Siemens Mobility", lei="LEI-M", country="DE",
                          source="gleif"),
    ]
    a.sources_used = ["gleif"]

    b = CorporateGroup(query="Siemens")
    b.primary_entity = CorporateEntity(name="Siemens AG", country="DE",
                                         wikidata_id="Q9601", source="wikidata")
    b.children = [
        # Doppelter Eintrag (LEI gleich) — wird dedupliziert
        CorporateEntity(name="Siemens Energy", lei="LEI-E", country="DE",
                          source="wikidata"),
        # Neuer Eintrag (nur in Wikidata)
        CorporateEntity(name="Siemens Healthineers", country="DE",
                          wikidata_id="Q12345", source="wikidata"),
    ]
    b.sources_used = ["wikidata"]

    merged = _merge_groups(a, b, max_children=10)
    assert merged is not None
    assert "gleif" in merged.sources_used
    assert "wikidata" in merged.sources_used
    # Children: LEI-E (dedupliziert) + LEI-M + Healthineers = 3
    assert len(merged.children) == 3
    names = {c.name for c in merged.children}
    assert names == {"Siemens Energy", "Siemens Mobility",
                       "Siemens Healthineers"}
    # primary: Wikidata-Q-ID wurde dazugemerged
    assert merged.primary_entity.lei == "LEI-S"
    assert merged.primary_entity.wikidata_id == "Q9601"


def test_merge_groups_max_children_kappt():
    from services.corporate_registry import (
        CorporateEntity, CorporateGroup, _merge_groups,
    )
    a = CorporateGroup(query="X")
    a.children = [
        CorporateEntity(name=f"Child{i}", lei=f"LEI-{i}", source="gleif")
        for i in range(10)
    ]
    out = _merge_groups(a, None, max_children=3)
    assert len(out.children) == 3


def test_merge_groups_handles_one_side_none():
    from services.corporate_registry import (
        CorporateEntity, CorporateGroup, _merge_groups,
    )
    a = CorporateGroup(query="X")
    a.primary_entity = CorporateEntity(name="A", source="gleif")
    out = _merge_groups(a, None, max_children=10)
    assert out is a
    out2 = _merge_groups(None, a, max_children=10)
    assert out2 is a
    assert _merge_groups(None, None, max_children=10) is None


# ── Cache-Logik ───────────────────────────────────────────────────────────────


def test_group_from_cache_payload_round_trip():
    """to_dict() -> _group_from_cache_payload() ist verlustarm."""
    from services.corporate_registry import (
        CorporateEntity, CorporateGroup,
        _group_from_cache_payload,
    )
    g = CorporateGroup(query="Siemens AG")
    g.primary_entity = CorporateEntity(
        name="Siemens AG", lei="LEI-S", country="DE", source="gleif",
        data_freshness=datetime(2024, 11, 12, 10, 0, 0),
    )
    g.children = [
        CorporateEntity(name="Siemens Energy", lei="LEI-E", country="DE",
                          source="gleif"),
    ]
    g.sources_used = ["gleif"]
    g.coverage_note = "Test note"

    payload = g.to_dict()
    restored = _group_from_cache_payload(payload)
    assert restored.query == "Siemens AG"
    assert restored.primary_entity is not None
    assert restored.primary_entity.lei == "LEI-S"
    assert restored.primary_entity.data_freshness == datetime(2024, 11, 12, 10, 0, 0)
    assert len(restored.children) == 1
    assert restored.children[0].name == "Siemens Energy"
    assert restored.sources_used == ["gleif"]
    assert restored.coverage_note == "Test note"


class _FakeQuery:
    def __init__(self, items):
        self._items = list(items)

    def filter(self, *_args, **_kw):
        return self

    def order_by(self, *_args, **_kw):
        return self

    def first(self):
        return self._items[0] if self._items else None


class _FakeDB:
    """Minimaler DB-Stub fuer Cache-Tests."""

    def __init__(self):
        self.added: list = []
        self.committed = False
        self.existing: list = []

    def query(self, _model):
        return _FakeQuery(self.existing)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True

    def rollback(self):
        pass


def test_get_cached_group_miss_liefert_none():
    from services.corporate_registry import get_cached_group
    db = _FakeDB()
    group, meta = get_cached_group(db, "ANY-QUERY")
    assert group is None
    assert meta is None


def test_get_cached_group_hit_liefert_group():
    """Wenn die Cache-Tabelle einen Eintrag hat, kommt der Eintrag zurueck."""
    from models.corporate_lookup_cache import CorporateLookupCache
    from services.corporate_registry import (
        CorporateEntity, CorporateGroup, get_cached_group,
    )
    g = CorporateGroup(query="Siemens AG")
    g.primary_entity = CorporateEntity(name="Siemens AG", lei="L1",
                                         source="gleif")
    g.sources_used = ["gleif"]
    payload = g.to_dict()
    row = CorporateLookupCache(
        query_normalized="siemens ag",
        payload=payload,
        fetched_at=datetime.utcnow() - timedelta(days=1),
        expires_at=datetime.utcnow() + timedelta(days=6),
        source="gleif",
    )
    db = _FakeDB()
    db.existing = [row]
    out, meta = get_cached_group(db, "Siemens AG")
    assert out is not None
    assert out.primary_entity.lei == "L1"
    assert meta and meta["cached"] is True
    assert meta["expired"] is False


def test_get_cached_group_expired_liefert_eintrag_aber_meta_expired():
    from models.corporate_lookup_cache import CorporateLookupCache
    from services.corporate_registry import (
        CorporateEntity, CorporateGroup, get_cached_group,
    )
    g = CorporateGroup(query="Siemens")
    g.primary_entity = CorporateEntity(name="Siemens", source="gleif")
    payload = g.to_dict()
    row = CorporateLookupCache(
        query_normalized="siemens",
        payload=payload,
        fetched_at=datetime.utcnow() - timedelta(days=30),
        expires_at=datetime.utcnow() - timedelta(days=23),
        source="gleif",
    )
    db = _FakeDB()
    db.existing = [row]
    out, meta = get_cached_group(db, "Siemens")
    assert out is not None
    assert meta and meta["expired"] is True


def test_store_group_in_cache_legt_neuen_eintrag_an():
    from services.corporate_registry import (
        CorporateEntity, CorporateGroup, store_group_in_cache,
    )
    g = CorporateGroup(query="Acme Inc.")
    g.primary_entity = CorporateEntity(name="Acme Inc.", source="gleif")
    g.sources_used = ["gleif"]
    db = _FakeDB()
    db.existing = []  # kein bestehender Eintrag
    store_group_in_cache(db, g)
    assert db.committed
    assert len(db.added) == 1
    row = db.added[0]
    assert row.query_normalized == "acme inc"
    assert row.source == "gleif"
    assert row.expires_at is not None
    assert row.fetched_at is not None
    # TTL = 7 Tage
    delta = row.expires_at - row.fetched_at
    assert 6 <= delta.days <= 8


def test_lookup_corporate_group_cached_cache_hit_meidet_live_call():
    """Wenn der Cache hat, wird `lookup_corporate_group` NICHT aufgerufen."""
    from models.corporate_lookup_cache import CorporateLookupCache
    from services.corporate_registry import (
        CorporateEntity, CorporateGroup,
        lookup_corporate_group_cached,
    )
    g = CorporateGroup(query="Siemens AG")
    g.primary_entity = CorporateEntity(name="Siemens AG", lei="L1",
                                         source="gleif")
    g.sources_used = ["gleif"]
    row = CorporateLookupCache(
        query_normalized="siemens ag",
        payload=g.to_dict(),
        fetched_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=7),
        source="gleif",
    )
    db = _FakeDB()
    db.existing = [row]

    # `lookup_corporate_group` darf nicht aufgerufen werden
    with patch("services.corporate_registry.lookup_corporate_group") as mock_live:
        out, meta = lookup_corporate_group_cached(db, "Siemens AG")
    assert out.primary_entity.lei == "L1"
    assert meta["cache"] == "hit"
    assert mock_live.call_count == 0


def test_lookup_corporate_group_cached_cache_miss_macht_live_call():
    from services.corporate_registry import (
        CorporateEntity, CorporateGroup,
        lookup_corporate_group_cached,
    )
    db = _FakeDB()
    db.existing = []  # kein Cache-Eintrag

    fake_group = CorporateGroup(query="Acme Inc")
    fake_group.primary_entity = CorporateEntity(
        name="Acme Inc", lei="L-NEW", source="gleif",
    )
    fake_group.sources_used = ["gleif"]

    with patch("services.corporate_registry.lookup_corporate_group",
                 return_value=fake_group) as mock_live:
        out, meta = lookup_corporate_group_cached(db, "Acme Inc")

    assert mock_live.call_count == 1
    assert out.primary_entity.lei == "L-NEW"
    assert meta["cache"] == "miss"


# ── Live-Lookup-Funktion (ohne externe API-Calls) ───────────────────────────


def test_lookup_corporate_group_returns_empty_group_on_total_failure():
    """Wenn sowohl GLEIF als auch Wikidata fehlschlagen, gibt es eine
    leere CorporateGroup mit aussagekraeftigem coverage_note zurueck.
    """
    from services.corporate_registry import lookup_corporate_group

    with (
        patch("services.corporate_registry._lookup_via_gleif",
                return_value=(None, "GLEIF: kein LEI-Record gefunden.")),
        patch("services.corporate_registry._lookup_via_wikidata",
                return_value=(None, "Wikidata: kein passender Eintrag gefunden.")),
    ):
        group = lookup_corporate_group("Doesnt Exist GmbH")

    assert group is not None
    assert group.query == "Doesnt Exist GmbH"
    assert group.primary_entity is None
    assert group.children == []
    assert "kostenlose" in group.coverage_note.lower() or \
            "drittquellen" in group.coverage_note.lower() or \
            "drittquellen" in group.coverage_note.replace("ä", "ae").lower()


def test_lookup_corporate_group_merged_when_both_sources_succeed():
    """Wenn beide Quellen liefern, werden Children gemerged + dedupliziert."""
    from services.corporate_registry import (
        CorporateEntity, CorporateGroup, lookup_corporate_group,
    )

    g_gleif = CorporateGroup(query="Siemens AG")
    g_gleif.primary_entity = CorporateEntity(
        name="Siemens AG", lei="LEI-S", source="gleif",
    )
    g_gleif.children = [
        CorporateEntity(name="Siemens Energy", lei="LEI-E", source="gleif"),
    ]
    g_gleif.sources_used = ["gleif"]

    g_wd = CorporateGroup(query="Siemens AG")
    g_wd.primary_entity = CorporateEntity(
        name="Siemens AG", wikidata_id="Q9601", source="wikidata",
    )
    g_wd.children = [
        CorporateEntity(name="Siemens Energy", lei="LEI-E", source="wikidata"),
        CorporateEntity(name="Siemens Healthineers", wikidata_id="Q12",
                          source="wikidata"),
    ]
    g_wd.sources_used = ["wikidata"]

    with (
        patch("services.corporate_registry._lookup_via_gleif",
                return_value=(g_gleif, None)),
        patch("services.corporate_registry._lookup_via_wikidata",
                return_value=(g_wd, None)),
    ):
        merged = lookup_corporate_group("Siemens AG", max_children=200)

    assert merged.primary_entity is not None
    assert merged.primary_entity.lei == "LEI-S"
    assert merged.primary_entity.wikidata_id == "Q9601"
    # 2 Children: LEI-E (dedup) + Healthineers
    assert len(merged.children) == 2
    assert {"gleif", "wikidata"} <= set(merged.sources_used)


# ── Audit-Report-Integration (Section-Builder) ───────────────────────────────


def test_build_corporate_group_section_kein_children_keine_zusatztreffer():
    """Wenn keine Kinder gefunden werden, sind die Zusatz-Listen leer."""
    from services.corporate_registry import CorporateEntity, CorporateGroup
    from services.state_aid_audit_report import _build_corporate_group_section

    # `lookup_corporate_group_cached` durch einen leeren Treffer ersetzen.
    fake_group = CorporateGroup(query="Solo GmbH")
    fake_group.primary_entity = CorporateEntity(name="Solo GmbH", lei="L1",
                                                  source="gleif")
    fake_group.sources_used = ["gleif"]
    fake_group.children = []
    fake_group.coverage_note = "Test"

    class _Db:
        def query(self, *_a, **_kw):
            return self

        def filter(self, *_a, **_kw):
            return self

        def all(self):
            return []

    with patch("services.corporate_registry.lookup_corporate_group_cached",
                 return_value=(fake_group, {"cache": "miss"})):
        sec = _build_corporate_group_section(
            _Db(), "Solo GmbH",
            country_code="DE",
            primary_state_aid_award_ids=set(),
            primary_beneficiaries=[],
        )
    assert sec.primary_entity is not None
    assert sec.primary_entity["lei"] == "L1"
    assert sec.children_count == 0
    assert sec.children_top == []
    assert sec.additional_state_aid_count == 0
    assert sec.additional_beneficiaries_count == 0


def test_corporate_group_section_serialisiert_in_audit_report():
    """AuditReportData.to_dict() serialisiert CorporateGroupSection korrekt."""
    from services.state_aid_audit_report import (
        AuditReportData, BeneficiariesSection, CorporateGroupSection,
        SanctionsSection, StateAidSection,
    )
    cgs = CorporateGroupSection(
        primary_entity={"name": "Siemens AG", "lei": "L1"},
        ultimate_parent=None,
        direct_parent=None,
        children_count=3,
        children_top=[{"name": "Siemens Energy", "lei": "L-E"}],
        additional_state_aid_count=5,
        additional_state_aid_amount_eur=1234.5,
        additional_state_aid_awards=[],
        additional_beneficiaries_count=2,
        additional_beneficiaries_amount_eur=200.0,
        additional_beneficiaries=[],
        coverage_note="Test note",
        sources_used=["gleif"],
        fetched_at=datetime(2026, 5, 8, 10, 0, 0),
        cache_meta={"cache": "miss"},
    )
    data = AuditReportData(
        query="Siemens AG",
        issued_at=datetime(2026, 5, 8),
        auftraggeber=None, pruefer_name=None,
        state_aid=StateAidSection(),
        beneficiaries=BeneficiariesSection(),
        sanctions=SanctionsSection(),
        cross_references=[],
        data_freshness={},
        corporate_group=cgs,
    )
    out = data.to_dict()
    cg = out.get("corporate_group")
    assert cg is not None
    assert cg["primary_entity"]["lei"] == "L1"
    assert cg["children_count"] == 3
    assert cg["additional_state_aid_count"] == 5
    assert cg["sources_used"] == ["gleif"]
    assert cg["fetched_at"] == "2026-05-08T10:00:00"


def test_corporate_group_none_when_not_requested():
    """Wenn corporate_group=None, soll to_dict() das Feld auf None setzen
    (nicht weglassen).
    """
    from services.state_aid_audit_report import (
        AuditReportData, BeneficiariesSection, SanctionsSection,
        StateAidSection,
    )
    data = AuditReportData(
        query="Test",
        issued_at=datetime(2026, 5, 8),
        auftraggeber=None, pruefer_name=None,
        state_aid=StateAidSection(),
        beneficiaries=BeneficiariesSection(),
        sanctions=SanctionsSection(),
        cross_references=[],
        data_freshness={},
    )
    out = data.to_dict()
    assert "corporate_group" in out
    assert out["corporate_group"] is None


# ── PDF-Renderer mit corporate_group-Sektion ─────────────────────────────────


def _build_audit_data_with_corporate_group():
    from services.state_aid_audit_report import (
        AuditReportData, BeneficiariesSection, CorporateGroupSection,
        SanctionsSection, StateAidSection,
    )
    cgs = CorporateGroupSection(
        primary_entity={
            "name": "Siemens AG",
            "lei": "529900T8BM49AURSDO55",
            "country": "DE",
            "source": "gleif",
            "data_freshness": "2024-11-12T10:00:00",
        },
        ultimate_parent={
            "name": "Siemens AG", "lei": "529900T8BM49AURSDO55",
            "country": "DE", "source": "gleif",
            "data_freshness": "2024-11-12T10:00:00",
        },
        direct_parent=None,
        children_count=2,
        children_top=[
            {
                "name": "Siemens Energy AG", "lei": "LEI-E",
                "country": "DE", "source": "gleif",
                "data_freshness": "2024-10-01T00:00:00",
            },
            {
                "name": "Siemens Mobility GmbH", "lei": "LEI-M",
                "country": "DE", "source": "wikidata",
                "data_freshness": "2024-08-01T00:00:00",
            },
        ],
        additional_state_aid_count=1,
        additional_state_aid_amount_eur=500000.0,
        additional_state_aid_awards=[
            {
                "beneficiary_name": "Siemens Energy AG",
                "country_code": "DE",
                "aid_amount_eur": 500000.0,
                "granting_date": "2023-04-01",
                "sa_reference": "SA.99999",
                "via_corporate_child": {
                    "name": "Siemens Energy AG", "lei": "LEI-E",
                    "wikidata_id": None, "country": "DE", "source": "gleif",
                },
            },
        ],
        additional_beneficiaries_count=1,
        additional_beneficiaries_amount_eur=200000.0,
        additional_beneficiaries=[
            {
                "company_name": "Siemens Mobility GmbH",
                "project_name": "Bahnsystem-Modernisierung",
                "bundesland": "Bayern",
                "fonds": "EFRE",
                "kosten": 200000.0,
                "via_corporate_child": {
                    "name": "Siemens Mobility GmbH", "lei": "LEI-M",
                    "wikidata_id": None, "country": "DE", "source": "wikidata",
                },
            },
        ],
        coverage_note=(
            "Diese Konzern-Daten stammen aus oeffentlichen Drittquellen "
            "(GLEIF / Wikidata)."
        ),
        sources_used=["gleif", "wikidata"],
        fetched_at=datetime(2026, 5, 8, 10, 0, 0),
        cache_meta={"cache": "miss"},
    )
    return AuditReportData(
        query="Siemens AG",
        issued_at=datetime(2026, 5, 8, 10, 0, 0),
        auftraggeber="EFRE-Pruefbehoerde Hessen",
        pruefer_name="J. Riener",
        state_aid=StateAidSection(),
        beneficiaries=BeneficiariesSection(),
        sanctions=SanctionsSection(),
        cross_references=[],
        data_freshness={
            "state_aid": {"as_of": "2026-05-01", "note": "ok"},
            "beneficiaries": {"as_of": None, "note": "lokal"},
            "sanctions": {"as_of": "2026-05-07", "note": "fsf"},
        },
        sources_explanation=[],
        disclaimer="Test disclaimer.",
        corporate_group=cgs,
    )


def test_pdf_render_enthaelt_konzernverbund_sektion():
    """PDF muss die Sektion 'Konzernverbund-Erweiterung' enthalten."""
    try:
        import fitz  # type: ignore
    except Exception:  # noqa: BLE001
        pytest.skip("pymupdf nicht verfuegbar")

    from services.state_aid_audit_pdf import render_audit_report_pdf
    data = _build_audit_data_with_corporate_group()
    pdf = render_audit_report_pdf(data)
    assert pdf[:4] == b"%PDF"

    doc = fitz.open(stream=pdf, filetype="pdf")
    full_text = "\n".join(p.get_text() for p in doc)
    doc.close()

    assert "Konzernverbund-Erweiterung" in full_text
    # Quellen-Hinweis muss vorkommen
    assert "GLEIF" in full_text or "Wikidata" in full_text
    # Anker-Firma + ein Kind aus dem Test-Daten
    assert "Siemens AG" in full_text
    assert "Siemens Energy" in full_text or "Siemens Mobility" in full_text
    # Tabellen-Header der Tochterfirmen-Tabelle
    assert "LEI" in full_text
    assert "Datenstand" in full_text
    # Coverage-Note durchgereicht
    assert "Drittquellen" in full_text or "drittquellen" in full_text.lower()


def test_pdf_render_ohne_corporate_group_keine_sektion():
    """Wenn corporate_group=None, darf die Sektion nicht im PDF auftauchen."""
    try:
        import fitz  # type: ignore
    except Exception:  # noqa: BLE001
        pytest.skip("pymupdf nicht verfuegbar")

    from services.state_aid_audit_pdf import render_audit_report_pdf
    from services.state_aid_audit_report import (
        AuditReportData, BeneficiariesSection, SanctionsSection,
        StateAidSection,
    )
    data = AuditReportData(
        query="Test GmbH",
        issued_at=datetime(2026, 5, 8),
        auftraggeber=None, pruefer_name=None,
        state_aid=StateAidSection(),
        beneficiaries=BeneficiariesSection(),
        sanctions=SanctionsSection(),
        cross_references=[],
        data_freshness={},
        corporate_group=None,
    )
    pdf = render_audit_report_pdf(data)
    doc = fitz.open(stream=pdf, filetype="pdf")
    full_text = "\n".join(p.get_text() for p in doc)
    doc.close()
    # Sektion ist NICHT da
    assert "Konzernverbund-Erweiterung" not in full_text


# ── Modell-Smoketest ──────────────────────────────────────────────────────────


def test_corporate_lookup_cache_modell_struktur():
    from models.corporate_lookup_cache import CorporateLookupCache
    cols = {c.name for c in CorporateLookupCache.__table__.columns}
    expected = {
        "id", "query_normalized", "payload",
        "fetched_at", "source", "expires_at",
    }
    assert expected.issubset(cols), (
        f"Spalten fehlen: {expected - cols}"
    )
    assert CorporateLookupCache.__tablename__ == "workshop_corporate_lookup_cache"
