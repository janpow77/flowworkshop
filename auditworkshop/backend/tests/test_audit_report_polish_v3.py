"""
Tests fuer Polish-Runde 3 des Cross-Register-Pruefberichts (Mai 2026).

Drei Erweiterungen:
- Aufgabe 1: Personen-Sanctions-Sektion
- Aufgabe 2: Address-Match Cross-Reference + location_hint
- Aufgabe 3: Coverage / Vollstaendigkeit-Sektion

Lauf: pytest backend/tests/test_audit_report_polish_v3.py -q
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

# Backend-Verzeichnis in den Pfad legen, damit `services.*` importierbar ist
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ── Helper ────────────────────────────────────────────────────────────────────


def _make_award_obj(**kwargs):
    """Minimaler StateAidAward-Surrogate (ohne DB-Roundtrip)."""
    class _A:
        pass
    a = _A()
    defaults = {
        "id": "uuid-1",
        "beneficiary_name": "Test GmbH",
        "beneficiary_identifier": None,
        "granting_date": None,
        "aid_amount_eur": 100000.0,
        "sa_reference": None,
        "case_url": None,
        "country_code": "DE",
        "country_name": "Deutschland",
        "nuts_code": None,
        "nuts_label": None,
        "aid_currency": "EUR",
        "aid_instrument": None,
        "aid_objective": None,
        "aid_measure_title": None,
        "granting_authority": None,
        "publication_date": None,
        "decision_url": None,
        "source_key": "tam_de",
        "source_url": None,
    }
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(a, k, v)
    return a


# ── Aufgabe 1: Personen-Sanctions-Sektion ───────────────────────────────────


class _FakeMultiSvc:
    """Fake fuer ``services.sanctions_service.MultiSanctionsService``.

    `search` liefert pro Person eine konfigurierbare Liste von Hits.
    """

    def __init__(self, hits_per_query: dict):
        self.hits_per_query = hits_per_query
        self._stats = {
            "sources_loaded": 5,
            "persons": 12345,
            "total_entries": 25000,
            "per_source": [],
        }

    def is_any_loaded(self) -> bool:
        return True

    def stats(self) -> dict:
        return self._stats

    def search(self, query, *, limit=10, min_score=70.0, schema=None):
        return list(self.hits_per_query.get(query, []))


def _make_sanctions_hit(name, *, source_key="us_ofac_sdn", score=92.0,
                       schema_="Person", aliases=None, birth=""):
    """Simuliert ein SanctionsHit-Objekt (Attribut-Zugriff wie das echte)."""
    return SimpleNamespace(
        id=f"hit-{name}",
        schema=schema_,
        name=name,
        matched_on=name,
        matched_field="name",
        score=score,
        confidence="high",
        aliases=aliases or [],
        birth_date=birth,
        countries="RU",
        addresses="Moscow",
        identifiers="",
        sanctions="EU regime 833/2014",
        program_ids="",
        first_seen="",
        last_seen="",
        source_key=source_key,
        source_display_name={"us_ofac_sdn": "OFAC SDN List",
                              "eu_fsf": "EU FSF",
                              "un_sc": "UN SC",
                              "gb_hmt_sanctions": "UK OFSI",
                              "ch_seco": "SECO"}.get(source_key, source_key),
    )


def test_persons_check_zwei_personen_einer_mit_treffer():
    """Zwei Personen — eine erscheint in OFAC, die andere nicht."""
    from services.state_aid_audit_report import _build_persons_check_section

    fake_svc = _FakeMultiSvc({
        "Vladimir Putin": [
            _make_sanctions_hit("Vladimir Putin", source_key="us_ofac_sdn",
                                score=98.0, aliases=["V. Putin"]),
            _make_sanctions_hit("Vladimir Putin", source_key="eu_fsf",
                                score=95.0),
        ],
        "Max Mustermann": [],
    })
    with patch(
        "services.sanctions_service.get_multi_service",
        return_value=fake_svc,
    ):
        section = _build_persons_check_section([
            {"name": "Vladimir Putin", "role": "UBO"},
            {"name": "Max Mustermann", "role": "Geschaeftsfuehrer"},
        ])

    assert section.total_persons == 2
    assert section.persons_with_match == 1
    # Putin: hat Treffer
    putin = next(
        p for p in section.persons_checked if "Putin" in p.name
    )
    assert putin.has_match is True
    assert "us_ofac_sdn" in putin.matched_sources
    assert "eu_fsf" in putin.matched_sources
    assert len(putin.hits) == 2
    # Mustermann: kein Treffer
    mm = next(
        p for p in section.persons_checked if "Mustermann" in p.name
    )
    assert mm.has_match is False
    assert mm.matched_sources == []
    assert mm.hits == []
    # Coverage-Note nicht leer
    assert "5" in section.coverage_note  # 5 Listen geprueft
    assert "Indikation" in section.coverage_note  # Personen-Match-Hinweis


def test_persons_check_score_unter_80_kein_match():
    """Treffer mit Score < 80 zaehlen nicht als Match (has_match=False),
    aber werden in `hits` aufgelistet (Indikation).
    """
    from services.state_aid_audit_report import _build_persons_check_section
    fake_svc = _FakeMultiSvc({
        "John Doe": [
            _make_sanctions_hit("John Doe", source_key="un_sc", score=72.0),
        ],
    })
    with patch(
        "services.sanctions_service.get_multi_service",
        return_value=fake_svc,
    ):
        section = _build_persons_check_section([
            {"name": "John Doe", "role": "Gesellschafter"},
        ])
    assert section.total_persons == 1
    assert section.persons_with_match == 0
    p = section.persons_checked[0]
    assert p.has_match is False
    # Hit ist trotzdem in der Liste
    assert len(p.hits) == 1


def test_persons_check_dedup_bei_doppelter_eingabe():
    """Doppelte Personen-Eintraege werden dedupliziert."""
    from services.state_aid_audit_report import _build_persons_check_section
    fake_svc = _FakeMultiSvc({})
    with patch(
        "services.sanctions_service.get_multi_service",
        return_value=fake_svc,
    ):
        section = _build_persons_check_section([
            {"name": "Anna Schmidt", "role": "UBO"},
            {"name": "Anna Schmidt", "role": "UBO"},  # Duplikat
            {"name": "Anna Schmidt", "role": "Gesellschafter"},  # andere Rolle, nicht dedupliziert
        ])
    # Anna|UBO und Anna|Gesellschafter → 2 Eintraege
    assert section.total_persons == 2


def test_persons_check_leere_liste_liefert_sektion_aber_total_0():
    """Ohne Personen wird die Sektion nicht gebaut — der Aufrufer reicht
    `persons=None` weiter, und _build_persons_check_section wird nicht
    aufgerufen. Aber wenn doch mit leerer Liste → total_persons == 0.
    """
    from services.state_aid_audit_report import _build_persons_check_section
    fake_svc = _FakeMultiSvc({})
    with patch(
        "services.sanctions_service.get_multi_service",
        return_value=fake_svc,
    ):
        section = _build_persons_check_section([])
    assert section.total_persons == 0
    assert section.persons_with_match == 0
    assert section.persons_checked == []


# ── Aufgabe 2: Address-Match Cross-Reference ─────────────────────────────────


def test_cross_reference_address_match_hessen():
    """Beneficiary mit NUTS DE7 (Hessen) + State-Aid-Award DE7 + aehnlicher
    Name → cross_reference type=address_match.
    """
    from services.state_aid_audit_report import _build_address_match_cross_refs

    award = _make_award_obj(
        id="award-1",
        beneficiary_name="Trumpf SE + Co. KG",
        nuts_code="DE71D",  # NUTS-3 in Hessen (DE7 NUTS-1)
        aid_amount_eur=500000.0,
    )
    beneficiaries = [{
        "company_name": "Trumpf GmbH",
        "nuts_code": "DE712",  # Auch DE7
        "kosten": 200000.0,
        "bundesland": "Hessen",
    }]
    refs = _build_address_match_cross_refs(
        sa_award_objs=[award],
        beneficiaries=beneficiaries,
    )
    addr = [r for r in refs if r.type == "address_match"]
    assert len(addr) == 1
    ev = addr[0].evidence
    assert ev["nuts_code"] == "DE7"
    assert ev["bundesland"] == "Hessen"
    assert ev["name_similarity_score"] >= 80.0
    assert ev["register_a"]["register"] == "state_aid"
    assert ev["register_b"]["register"] == "beneficiaries"
    # Description ist neutral, keine Bewertung
    desc_lower = addr[0].description.lower()
    for forbidden in ("risiko", "auffaellig", "verdaechtig"):
        assert forbidden not in desc_lower


def test_cross_reference_address_match_unterschiedlicher_nuts_kein_treffer():
    """Beneficiary in Bayern (DE2), Award in Hessen (DE7) → kein Adress-Match,
    auch wenn Namen identisch waeren.
    """
    from services.state_aid_audit_report import _build_address_match_cross_refs
    award = _make_award_obj(
        id="award-x",
        beneficiary_name="Mueller GmbH",
        nuts_code="DE21",  # Bayern
    )
    beneficiaries = [{
        "company_name": "Mueller GmbH",
        "nuts_code": "DE71",  # Hessen
        "kosten": 100000.0,
    }]
    refs = _build_address_match_cross_refs(
        sa_award_objs=[award],
        beneficiaries=beneficiaries,
    )
    assert [r for r in refs if r.type == "address_match"] == []


def test_cross_reference_address_match_unterschiedliche_namen_kein_treffer():
    """Gleiches NUTS, aber Score unter 80 → kein Adress-Match."""
    from services.state_aid_audit_report import _build_address_match_cross_refs
    award = _make_award_obj(
        id="award-y",
        beneficiary_name="Alpha Solar GmbH",
        nuts_code="DE712",
    )
    beneficiaries = [{
        "company_name": "Beta Industries AG",
        "nuts_code": "DE71",
        "kosten": 50000.0,
    }]
    refs = _build_address_match_cross_refs(
        sa_award_objs=[award],
        beneficiaries=beneficiaries,
    )
    assert [r for r in refs if r.type == "address_match"] == []


def test_cross_reference_address_match_ohne_nuts_kein_treffer():
    """Datensatz ohne nuts_code → wird ignoriert."""
    from services.state_aid_audit_report import _build_address_match_cross_refs
    award = _make_award_obj(
        beneficiary_name="Test GmbH",
        nuts_code=None,
    )
    beneficiaries = [{
        "company_name": "Test GmbH",
        "nuts_code": "DE7",
    }]
    refs = _build_address_match_cross_refs(
        sa_award_objs=[award],
        beneficiaries=beneficiaries,
    )
    assert refs == []


# ── Aufgabe 3: Coverage / Vollstaendigkeit ──────────────────────────────────


def test_completeness_label_grenzwerte():
    """`_completeness_label`: vollständig >= 95%, partiell 1..94, sonst unbekannt."""
    from services.state_aid_audit_report import _completeness_label
    assert _completeness_label(100.0, 1000) == "vollständig"
    assert _completeness_label(95.0, 1000) == "vollständig"
    assert _completeness_label(94.9, 1000) == "partiell"
    assert _completeness_label(50.0, 1000) == "partiell"
    assert _completeness_label(1.0, 1000) == "partiell"
    # local_count == 0 → unbekannt
    assert _completeness_label(0.0, 0) == "unbekannt"
    # percent None → unbekannt
    assert _completeness_label(None, 1000) == "unbekannt"


def test_aggregate_overall_completeness_green_yellow_red():
    """Wartungs-Ampel-Logik."""
    from services.state_aid_audit_report import (
        CoverageEntry, _aggregate_overall_completeness,
    )

    def _e(percent, local=1000, expected=1000):
        return CoverageEntry(
            source_module="state_aid",
            source_key="x", display_name="x",
            local_count=local,
            expected_count=expected,
            coverage_percent=percent,
            last_harvest_at=None,
            completeness_note="vollständig",
        )

    # Alle 100% → green
    assert _aggregate_overall_completeness([_e(100.0), _e(100.0)]) == "green"
    # Einer 90% → yellow
    assert _aggregate_overall_completeness([_e(100.0), _e(90.0)]) == "yellow"
    # Einer 30% → red
    assert _aggregate_overall_completeness([_e(100.0), _e(30.0)]) == "red"
    # local_count==0 mit expected>0 → red
    assert _aggregate_overall_completeness([
        _e(0.0, local=0, expected=100),
    ]) == "red"
    # Leere Liste → yellow (Default)
    assert _aggregate_overall_completeness([]) == "yellow"


def test_coverage_section_drei_module_konsistent():
    """Coverage-Sektion enthaelt alle drei Module mit konsistenten Werten."""
    from services.state_aid_audit_report import _build_coverage_section
    from datetime import datetime as _dt

    # Fake DB: liefert StateAidSource-Liste
    fake_state_aid_sources = [
        SimpleNamespace(
            source_key="tam_de",
            display_name="EU TAM Deutschland",
            record_count=100000,
            expected_total=120000,
            last_successful_harvest_at=_dt(2026, 5, 1),
        ),
        SimpleNamespace(
            source_key="tam_at",
            display_name="EU TAM Oesterreich",
            record_count=20000,
            expected_total=20000,
            last_successful_harvest_at=_dt(2026, 5, 5),
        ),
    ]

    class _FakeQuery:
        def __init__(self, items):
            self.items = items

        def all(self):
            return self.items

    class _FakeDB:
        def query(self, _model):
            return _FakeQuery(fake_state_aid_sources)

    # Stub Beneficiaries
    fake_ben_sources = [
        {
            "table_name": "trans_hessen", "source": "transparenzliste_hessen",
            "bundesland": "Hessen", "fonds": "EFRE", "row_count": 5000,
        },
        {
            "table_name": "trans_jtf", "source": "transparenzliste_jtf",
            "bundesland": None, "fonds": "JTF", "row_count": 1500,
        },
    ]

    # Stub Sanctions
    class _FakeMSvc:
        def stats(self):
            return {
                "sources_loaded": 2,
                "total_entries": 6000,
                "per_source": [
                    {
                        "source_key": "eu_fsf",
                        "source_display_name": "EU FSF",
                        "total_entries": 5000,
                        "source_mtime": "2026-05-01T12:00:00",
                    },
                    {
                        "source_key": "us_ofac_sdn",
                        "source_display_name": "OFAC SDN List",
                        "total_entries": 1000,
                        "source_mtime": None,
                    },
                ],
            }

    with patch(
        "services.dataframe_service.get_beneficiary_sources",
        return_value=fake_ben_sources,
    ), patch(
        "services.sanctions_service.get_multi_service",
        return_value=_FakeMSvc(),
    ):
        section = _build_coverage_section(_FakeDB())

    # Drei Module vertreten
    modules = sorted({e.source_module for e in section.entries})
    assert modules == ["beneficiary", "sanctions", "state_aid"]

    # State-Aid: tam_de Coverage = 100000/120000 ≈ 83.3%, status partiell
    de_entry = next(
        e for e in section.entries
        if e.source_module == "state_aid" and e.source_key == "tam_de"
    )
    assert de_entry.local_count == 100000
    assert de_entry.expected_count == 120000
    assert de_entry.coverage_percent is not None
    assert 80.0 <= de_entry.coverage_percent <= 90.0
    assert de_entry.completeness_note == "partiell"

    # State-Aid: tam_at lokal == erwartet → vollständig
    at_entry = next(
        e for e in section.entries
        if e.source_module == "state_aid" and e.source_key == "tam_at"
    )
    assert at_entry.coverage_percent == 100.0
    assert at_entry.completeness_note == "vollständig"

    # Beneficiaries: Hessen 5000 → vollständig (lokal == erwartet)
    ben_hessen = next(
        e for e in section.entries
        if e.source_module == "beneficiary"
        and "hessen" in (e.source_key or "").lower()
    )
    assert ben_hessen.local_count == 5000
    assert ben_hessen.completeness_note == "vollständig"

    # Sanctions: eu_fsf 5000 entries
    eu_fsf = next(
        e for e in section.entries
        if e.source_module == "sanctions" and e.source_key == "eu_fsf"
    )
    assert eu_fsf.local_count == 5000
    assert eu_fsf.completeness_note == "vollständig"
    # mtime parse
    assert eu_fsf.last_harvest_at is not None

    # overall_completeness konsistent: tam_de ist partiell → yellow
    assert section.overall_completeness == "yellow"


def test_coverage_section_empty_when_db_empty():
    """Wenn keine Quellen vorhanden sind, bleibt entries leer und overall=yellow."""
    from services.state_aid_audit_report import _build_coverage_section

    class _FakeQuery:
        def all(self):
            return []

    class _FakeDB:
        def query(self, _model):
            return _FakeQuery()

    with patch(
        "services.dataframe_service.get_beneficiary_sources",
        return_value=[],
    ), patch(
        "services.sanctions_service.get_multi_service",
        side_effect=Exception("not loaded"),
    ):
        section = _build_coverage_section(_FakeDB())
    assert section.entries == []
    assert section.overall_completeness == "yellow"


# ── PDF-Rendering: Personen + Coverage ──────────────────────────────────────


def _build_audit_data_with_polish_v3():
    """Konstruiert AuditReportData mit Personen-Sektion + Coverage-Sektion."""
    from services.state_aid_audit_report import (
        AuditReportData, BeneficiariesSection, CoverageEntry, CoverageSection,
        CrossReference, PersonCheckEntry, PersonsCheckSection, SanctionsSection,
        SourceExplanation, StateAidSection,
    )
    return AuditReportData(
        query="Trumpf GmbH",
        issued_at=datetime(2026, 5, 8, 10, 0, 0),
        auftraggeber="EFRE-Pruefbehoerde Hessen",
        pruefer_name="J. Riener",
        state_aid=StateAidSection(total_count=1, total_amount_eur=500000.0,
                                   awards=[{
                                       "beneficiary_name": "Trumpf GmbH",
                                       "granting_authority": "BAFA",
                                       "country_code": "DE",
                                       "nuts_code": "DE712",
                                       "aid_amount_eur": 500000.0,
                                       "granting_date": "2024-01-15",
                                   }]),
        beneficiaries=BeneficiariesSection(total_count=0),
        sanctions=SanctionsSection(total_hits=0, hits=[]),
        cross_references=[CrossReference(
            type="address_match",
            description=(
                "State-Aid-Award fuer 'Trumpf GmbH' und Beneficiary-Eintrag "
                "liegen beide in NUTS-Region 'DE7' (Hessen)."
            ),
            evidence={
                "nuts_code": "DE7",
                "bundesland": "Hessen",
                "name_similarity_score": 92.0,
            },
        )],
        data_freshness={
            "state_aid": {
                "as_of": "2026-05-01T10:00:00",
                "record_count": 100000,
                "note": "Letzter Harvest 2026-05-01",
            },
            "beneficiaries": {"as_of": None, "note": "Lokal"},
            "sanctions": {
                "as_of": "2026-05-07T12:00:00+00:00",
                "record_count": 6000,
                "note": "Stand 2026-05-07",
            },
        },
        sources_explanation=[
            SourceExplanation(
                name="EU-State-Aid Transparency Aid Module (TAM)",
                url="https://webgate.ec.europa.eu/competition/transparency/public",
                description="AGVO-Beihilfen.",
                last_data_update=datetime(2026, 5, 1),
                record_count=100000,
            ),
        ],
        disclaimer="Disclaimer-Text fuer Tests.",
        persons_check=PersonsCheckSection(
            persons_checked=[
                PersonCheckEntry(
                    name="Vladimir Putin",
                    role="UBO",
                    hits=[{
                        "id": "ofac-1",
                        "name": "Vladimir Putin",
                        "score": 98.0,
                        "confidence": "high",
                        "aliases": ["V. Putin"],
                        "birth_date": "1952-10-07",
                        "countries": "RU",
                        "sanctions": "EU regime 833/2014",
                        "program_ids": "RUSSIA-EO13662",
                        "source_key": "us_ofac_sdn",
                        "source_display_name": "OFAC SDN List",
                    }],
                    matched_sources=["us_ofac_sdn"],
                    has_match=True,
                ),
                PersonCheckEntry(
                    name="Max Mustermann",
                    role="Geschaeftsfuehrer",
                    hits=[],
                    matched_sources=[],
                    has_match=False,
                ),
            ],
            total_persons=2,
            persons_with_match=1,
            coverage_note=(
                "Geprueft gegen 5 Sanctions-Liste(n) mit insgesamt "
                "12.345 Personen-Eintraegen (schema='Person'). Match-Schwelle: "
                "Score >= 80. Personen-Match ohne Geburtsdatum-Abgleich ist "
                "eine Indikation, kein Beweis."
            ),
        ),
        coverage=CoverageSection(
            entries=[
                CoverageEntry(
                    source_module="state_aid",
                    source_key="tam_de",
                    display_name="EU TAM Deutschland",
                    local_count=100000,
                    expected_count=120000,
                    coverage_percent=83.3,
                    last_harvest_at=datetime(2026, 5, 1),
                    completeness_note="partiell",
                ),
                CoverageEntry(
                    source_module="beneficiary",
                    source_key="transparenzliste_hessen",
                    display_name="transparenzliste_hessen (Hessen/EFRE)",
                    local_count=5000,
                    expected_count=5000,
                    coverage_percent=100.0,
                    last_harvest_at=None,
                    completeness_note="vollständig",
                ),
                CoverageEntry(
                    source_module="sanctions",
                    source_key="eu_fsf",
                    display_name="EU FSF",
                    local_count=5000,
                    expected_count=5000,
                    coverage_percent=100.0,
                    last_harvest_at=datetime(2026, 5, 7),
                    completeness_note="vollständig",
                ),
            ],
            overall_completeness="yellow",
        ),
    )


def test_render_pdf_enthaelt_personen_und_coverage_sektionen():
    """Rendering muss die neuen Sektionen enthalten (Headlines + Inhalt)."""
    try:
        import fitz  # type: ignore
    except Exception:  # noqa: BLE001
        pytest.skip("pymupdf nicht verfuegbar")

    from services.state_aid_audit_pdf import render_audit_report_pdf
    data = _build_audit_data_with_polish_v3()
    pdf = render_audit_report_pdf(data)

    doc = fitz.open(stream=pdf, filetype="pdf")
    full_text = "\n".join(page.get_text() for page in doc)
    doc.close()

    # Personen-Sektion vorhanden
    assert "Personen-Sanktionscheck" in full_text
    assert "Putin" in full_text
    assert "Max Mustermann" in full_text
    # Score taucht auf
    assert "98" in full_text or "OFAC" in full_text
    # Coverage-Sektion vorhanden
    assert "Coverage und Datenstand" in full_text
    assert "vollständig" in full_text or "partiell" in full_text
    # Beobachtung-Hinweis (Indikation, kein Beweis)
    assert "Indikation" in full_text or "Beweis" in full_text


def test_render_pdf_keine_severity_bei_personen_und_coverage():
    """Strenger Test: weder Personen- noch Coverage-Sektion verwenden
    bewertendes Vokabular.
    """
    try:
        import fitz  # type: ignore
    except Exception:  # noqa: BLE001
        pytest.skip("pymupdf nicht verfuegbar")
    from services.state_aid_audit_pdf import render_audit_report_pdf
    data = _build_audit_data_with_polish_v3()
    pdf = render_audit_report_pdf(data)
    doc = fitz.open(stream=pdf, filetype="pdf")
    full_text = "\n".join(page.get_text() for page in doc).lower()
    doc.close()
    forbidden = [
        "risiko-score", "risikobewertung",
        "verdaechtig", "verdächtig",
        "auffaellig", "auffällig",
    ]
    for word in forbidden:
        assert word not in full_text, (
            f"PDF enthaelt bewertendes Wort '{word}' — Personen-/Coverage-"
            f"Sektion muss neutral/Wartungs-Aussage bleiben."
        )


def test_to_dict_serialisiert_persons_und_coverage():
    """Serialisierung in to_dict — Felder im JSON erscheinen."""
    data = _build_audit_data_with_polish_v3()
    out = data.to_dict()
    assert "persons_check" in out
    assert out["persons_check"] is not None
    assert out["persons_check"]["total_persons"] == 2
    assert out["persons_check"]["persons_with_match"] == 1
    assert "coverage" in out
    assert out["coverage"] is not None
    assert out["coverage"]["overall_completeness"] == "yellow"
    assert len(out["coverage"]["entries"]) == 3
    # last_harvest_at ist ISO-formatiert
    sa_entry = next(
        e for e in out["coverage"]["entries"]
        if e["source_key"] == "tam_de"
    )
    assert isinstance(sa_entry["last_harvest_at"], str)
    assert sa_entry["last_harvest_at"].startswith("2026-")


# ── PersonInput Pydantic-Validierung ────────────────────────────────────────


def test_person_input_pydantic_min_length():
    """PersonInput verlangt name min_length=2."""
    from routers.state_aid import PersonInput
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        PersonInput(name="A")  # zu kurz


def test_person_input_pydantic_role_optional():
    from routers.state_aid import PersonInput
    p = PersonInput(name="Max Mustermann")
    assert p.role is None
    p2 = PersonInput(name="Max Mustermann", role="Gesellschafter")
    assert p2.role == "Gesellschafter"


# ── parse_persons_query (URL-encoded GET) ───────────────────────────────────


def test_parse_persons_query_format_name_pipe_rolle():
    """`?persons=Name|Rolle` — Format mit Pipe."""
    from routers.state_aid import _parse_persons_query
    parsed = _parse_persons_query([
        "Max Mustermann|Geschaeftsfuehrer",
        "Jane Doe|UBO",
        "John Smith",  # ohne Rolle
    ])
    assert parsed == [
        {"name": "Max Mustermann", "role": "Geschaeftsfuehrer"},
        {"name": "Jane Doe", "role": "UBO"},
        {"name": "John Smith", "role": None},
    ]


def test_parse_persons_query_filtert_zu_kurze_namen():
    from routers.state_aid import _parse_persons_query
    parsed = _parse_persons_query([
        "A|UBO",       # zu kurz
        "",            # leer
        "Bob|CEO",
    ])
    assert parsed == [{"name": "Bob", "role": "CEO"}]


def test_parse_persons_query_max_20():
    from routers.state_aid import _parse_persons_query
    inputs = [f"Person{i:02d}|UBO" for i in range(50)]
    parsed = _parse_persons_query(inputs)
    assert len(parsed) == 20


# ── location_hint NUTS-Prefix-Mapping ────────────────────────────────────────


def test_location_hint_to_nuts_prefix_bundesland():
    from services.state_aid_service import _location_hint_to_nuts_prefix
    assert _location_hint_to_nuts_prefix("hessen") == "DE7"
    assert _location_hint_to_nuts_prefix("bayern") == "DE2"
    assert _location_hint_to_nuts_prefix("nrw") == "DEA"


def test_location_hint_to_nuts_prefix_regierungsbezirk():
    from services.state_aid_service import _location_hint_to_nuts_prefix
    assert _location_hint_to_nuts_prefix("muenchen") is None  # Stadt nicht im Mapping
    # Regierungsbezirk
    assert _location_hint_to_nuts_prefix("oberbayern") == "DE2"
    assert _location_hint_to_nuts_prefix("darmstadt") == "DE7"


def test_location_hint_to_nuts_prefix_unbekannt():
    from services.state_aid_service import _location_hint_to_nuts_prefix
    assert _location_hint_to_nuts_prefix("Lummerland") is None
    assert _location_hint_to_nuts_prefix("") is None
