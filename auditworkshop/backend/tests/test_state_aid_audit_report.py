"""
Tests fuer den Cross-Register-Pruefbericht (services/state_aid_audit_report.py
+ services/state_aid_audit_pdf.py).

Schwerpunkt: pure helper + reine Logik (Aggregation, Cross-Reference-Erkennung,
PDF-Bytes-Validitaet). Datenbank-Queries werden mit synthetischen In-Memory-
Strukturen ersetzt — keine echte DB notwendig.

Wichtig: KEINE Risiko-Score-Erwartungen — gibt es nicht. Reine Fakten.

Lauf: pytest backend/tests/test_state_aid_audit_report.py -q
"""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

import pytest

# Backend-Verzeichnis in den Pfad legen, damit `services.*` importierbar ist
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ── Aggregations-Helfer ───────────────────────────────────────────────────────


def test_aggregate_top_summiert_und_zaehlt_korrekt():
    from services.state_aid_audit_report import _aggregate_top
    items = [
        {"granting_authority": "BMWK", "aid_amount_eur": 1000.0},
        {"granting_authority": "BMWK", "aid_amount_eur": 500.0},
        {"granting_authority": "BAFA", "aid_amount_eur": 2000.0},
        {"granting_authority": None, "aid_amount_eur": 100.0},  # ignoriert
    ]
    result = _aggregate_top(items, "granting_authority", limit=10)
    assert len(result) == 2
    bmwk = next(r for r in result if r["key"] == "BMWK")
    assert bmwk["count"] == 2
    assert bmwk["total_eur"] == 1500.0
    bafa = next(r for r in result if r["key"] == "BAFA")
    assert bafa["count"] == 1
    assert bafa["total_eur"] == 2000.0
    # Sortierung: BAFA hoeher (2000 > 1500)
    assert result[0]["key"] == "BAFA"


def test_aggregate_by_year_korrekt():
    from services.state_aid_audit_report import _aggregate_by_year
    items = [
        {"granting_date": "2020-01-15", "aid_amount_eur": 100.0},
        {"granting_date": "2020-06-01", "aid_amount_eur": 200.0},
        {"granting_date": "2021-03-10", "aid_amount_eur": 300.0},
        {"granting_date": None, "aid_amount_eur": 999.0},  # ignoriert
    ]
    result = _aggregate_by_year(items)
    assert len(result) == 2
    y2020 = next(r for r in result if r["year"] == 2020)
    assert y2020["count"] == 2
    assert y2020["total_eur"] == 300.0
    y2021 = next(r for r in result if r["year"] == 2021)
    assert y2021["count"] == 1
    # aufsteigend nach Jahr
    assert [r["year"] for r in result] == [2020, 2021]


def test_aggregate_by_nuts1_kuerzt_auf_drei_zeichen():
    from services.state_aid_audit_report import _aggregate_by_nuts1
    items = [
        {"nuts_code": "DE21", "aid_amount_eur": 100.0},   # → DE2
        {"nuts_code": "DE212", "aid_amount_eur": 200.0},  # → DE2
        {"nuts_code": "DEA", "aid_amount_eur": 300.0},    # → DEA
        {"nuts_code": "DE2", "aid_amount_eur": 400.0},    # → DE2
        {"nuts_code": None, "aid_amount_eur": 999.0},     # ignoriert
    ]
    result = _aggregate_by_nuts1(items)
    by_code = {r["nuts_code"]: r for r in result}
    assert "DE2" in by_code
    assert by_code["DE2"]["count"] == 3
    assert by_code["DE2"]["total_eur"] == 700.0
    assert "DEA" in by_code
    assert by_code["DEA"]["count"] == 1


# ── Cross-Reference-Logik ─────────────────────────────────────────────────────


def _make_award_obj(**kwargs):
    """Minimaler StateAidAward-Surrogate fuer Tests (kein DB-Roundtrip)."""
    class _A:
        pass
    a = _A()
    defaults = {
        "id": "uuid-1",
        "beneficiary_name": "Test GmbH",
        "beneficiary_identifier": None,
        "granting_date": None,
        "aid_amount_eur": 0.0,
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


def test_cross_reference_name_match_state_aid_beneficiary():
    """Gleicher (normalisierter) Name in beiden Registern → name_match.

    Beide Namen normalisieren auf 'fraunhofer gesellschaft':
    - 'Fraunhofer-Gesellschaft GmbH' → Bindestrich + GmbH-Suffix raus
    - 'Fraunhofer Gesellschaft mbH'  → mbH-Suffix raus
    """
    from services.state_aid_audit_report import _build_cross_references
    sa_dicts = [
        {"beneficiary_name": "Fraunhofer-Gesellschaft GmbH"},
    ]
    beneficiaries = [
        {"company_name": "Fraunhofer Gesellschaft mbH", "aktenzeichen": ""},
    ]
    refs = _build_cross_references(
        query="Fraunhofer",
        sa_award_objs=[_make_award_obj(beneficiary_name="Fraunhofer-Gesellschaft GmbH")],
        sa_dicts=sa_dicts,
        beneficiaries=beneficiaries,
    )
    name_matches = [r for r in refs if r.type == "name_match_state_aid_beneficiary"]
    assert len(name_matches) >= 1
    # Evidenz vorhanden + neutral formuliert
    ev = name_matches[0].evidence
    assert "register_a" in ev and "register_b" in ev
    assert ev["register_a"]["register"] == "state_aid"
    assert ev["register_b"]["register"] == "beneficiaries"
    # Description darf KEIN Bewertungsvokabular enthalten
    desc_lower = name_matches[0].description.lower()
    for forbidden in ("risiko", "auffaellig", "verdaecht", "auffällig", "verdächt"):
        assert forbidden not in desc_lower


def test_cross_reference_kein_name_match_wenn_namen_unterschiedlich():
    from services.state_aid_audit_report import _build_cross_references
    refs = _build_cross_references(
        query="Test",
        sa_award_objs=[_make_award_obj()],
        sa_dicts=[{"beneficiary_name": "Alpha GmbH"}],
        beneficiaries=[{"company_name": "Beta AG", "aktenzeichen": ""}],
    )
    name_matches = [r for r in refs if r.type == "name_match_state_aid_beneficiary"]
    assert name_matches == []


def test_cross_reference_sa_reference_kom_case_linked():
    from services.state_aid_audit_report import _build_cross_references
    sa_dicts = [{
        "beneficiary_name": "Alpha GmbH",
        "sa_reference": "SA.12345",
        "case_url": "https://competition-cases.ec.europa.eu/cases/SA.12345",
    }]
    refs = _build_cross_references(
        query="Alpha",
        sa_award_objs=[_make_award_obj()],
        sa_dicts=sa_dicts,
        beneficiaries=[],
    )
    sa_refs = [r for r in refs if r.type == "sa_reference_kom_case_linked"]
    assert len(sa_refs) == 1
    assert sa_refs[0].evidence["sa_reference"] == "SA.12345"
    assert "competition-cases" in sa_refs[0].evidence["case_url"]


def test_cross_reference_duplicate_award_within_year_5_plus():
    """5+ Awards desselben Beneficiary innerhalb 12 Monaten → Treffer."""
    from services.state_aid_audit_report import _build_cross_references
    awards = [
        _make_award_obj(
            id=f"a{i}",
            beneficiary_name="Mehrfach GmbH",
            granting_date=date(2023, m, 1),
            aid_amount_eur=100000.0,
        )
        for i, m in enumerate([1, 3, 5, 7, 9, 11])  # 6 Awards in 2023
    ]
    refs = _build_cross_references(
        query="Mehrfach",
        sa_award_objs=awards,
        sa_dicts=[{
            "beneficiary_name": a.beneficiary_name,
            "granting_date": a.granting_date.isoformat(),
        } for a in awards],
        beneficiaries=[],
    )
    dups = [r for r in refs if r.type == "duplicate_award_within_year"]
    assert len(dups) == 1
    ev = dups[0].evidence
    assert ev["award_count"] >= 5
    assert ev["total_amount_eur"] >= 500000.0
    assert len(ev["award_ids"]) == ev["award_count"]


def test_cross_reference_keine_duplicates_bei_4_awards():
    """4 Awards reichen nicht fuer duplicate_award_within_year (Schwelle 5)."""
    from services.state_aid_audit_report import _build_cross_references
    awards = [
        _make_award_obj(
            id=f"a{i}",
            beneficiary_name="Wenige GmbH",
            granting_date=date(2023, m, 1),
            aid_amount_eur=100000.0,
        )
        for i, m in enumerate([1, 4, 7, 10])  # 4 Awards
    ]
    refs = _build_cross_references(
        query="Wenige",
        sa_award_objs=awards,
        sa_dicts=[{
            "beneficiary_name": a.beneficiary_name,
            "granting_date": a.granting_date.isoformat(),
        } for a in awards],
        beneficiaries=[],
    )
    dups = [r for r in refs if r.type == "duplicate_award_within_year"]
    assert dups == []


def test_cross_reference_identifier_match():
    """Gleicher Identifier (HRB) in State-Aid und Beneficiaries."""
    from services.state_aid_audit_report import _build_cross_references
    awards = [_make_award_obj(
        beneficiary_name="Alpha GmbH",
        beneficiary_identifier="HRB12345",
    )]
    refs = _build_cross_references(
        query="Alpha",
        sa_award_objs=awards,
        sa_dicts=[{"beneficiary_name": "Alpha GmbH"}],
        beneficiaries=[
            {"company_name": "Alpha GmbH", "aktenzeichen": "Foerd-2023/HRB12345/02"},
        ],
    )
    id_matches = [r for r in refs if r.type == "identifier_match"]
    assert len(id_matches) >= 1
    assert id_matches[0].evidence["shared_value"] == "hrb12345"


# ── Datenklassen + to_dict ────────────────────────────────────────────────────


def test_audit_report_data_to_dict_serialisiert_vollstaendig():
    from services.state_aid_audit_report import (
        AuditReportData, BeneficiariesSection, CrossReference,
        SanctionsSection, StateAidSection,
    )
    data = AuditReportData(
        query="Trumpf",
        issued_at=datetime(2026, 5, 8, 10, 0, 0),
        auftraggeber="Pruefbehoerde",
        pruefer_name="J. Riener",
        state_aid=StateAidSection(total_count=5, total_amount_eur=12345.67),
        beneficiaries=BeneficiariesSection(total_count=2),
        sanctions=SanctionsSection(total_hits=0),
        cross_references=[CrossReference(
            type="sa_reference_kom_case_linked",
            description="Test",
            evidence={"sa_reference": "SA.111"},
        )],
        data_freshness={"state_aid": {"as_of": "2026-05-01", "note": "ok"}},
    )
    out = data.to_dict()
    assert out["query"] == "Trumpf"
    # Aktenzeichen wurde Mai 2026 entfernt — darf NICHT im Dict erscheinen.
    assert "aktenzeichen" not in out
    assert out["state_aid"]["total_count"] == 5
    assert out["state_aid"]["total_amount_eur"] == 12345.67
    assert len(out["cross_references"]) == 1
    assert out["cross_references"][0]["type"] == "sa_reference_kom_case_linked"
    # Neue Felder: sources_explanation (Liste, hier leer-Default) +
    # disclaimer (String, hier leer-Default).
    assert "sources_explanation" in out
    assert isinstance(out["sources_explanation"], list)
    assert "disclaimer" in out
    assert isinstance(out["disclaimer"], str)


def test_pflichthinweis_enthaelt_pflichttextbausteine():
    from services.state_aid_audit_report import (
        AuditReportData, BeneficiariesSection, SanctionsSection,
        StateAidSection, pflichthinweis,
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
        data_freshness={
            "state_aid": {"as_of": "2026-05-01"},
            "sanctions": {"as_of": "2026-05-07T12:00:00+00:00"},
        },
    )
    txt = pflichthinweis(data)
    # Quellen erwaehnt
    assert "TAM" in txt
    assert "Beguenstigtenverzeichnis" in txt or "Begünstigtenverzeichnis" in txt
    assert "FSF" in txt or "OpenSanctions" in txt
    # Pruefer-Bewertung-Hinweis
    assert "Pruefer" in txt or "Prüfer" in txt
    assert "Vollstaendigkeit" in txt or "Vollständigkeit" in txt
    # KEIN Bewertungsvokabular
    for forbidden in ("risiko", "auffaellig", "verdaecht", "auffällig", "verdächt"):
        assert forbidden not in txt.lower()


# ── PDF-Generator ─────────────────────────────────────────────────────────────


def _build_minimal_audit_data():
    """Konstruiert ein minimales AuditReportData fuer PDF-Tests."""
    from services.state_aid_audit_report import (
        AuditReportData, BeneficiariesSection, CrossReference,
        SanctionsSection, SourceExplanation, StateAidSection,
    )
    return AuditReportData(
        query="Trumpf GmbH",
        issued_at=datetime(2026, 5, 8, 10, 0, 0),
        auftraggeber="EFRE-Pruefbehoerde Hessen",
        pruefer_name="J. Riener",
        state_aid=StateAidSection(
            total_count=2,
            total_amount_eur=1500000.0,
            awards=[
                {
                    "beneficiary_name": "Trumpf GmbH",
                    "granting_authority": "BMWK",
                    "country_code": "DE",
                    "nuts_code": "DE11",
                    "aid_amount_eur": 1000000.0,
                    "granting_date": "2023-04-01",
                    "sa_reference": "SA.50000",
                    "case_url": "https://competition-cases.ec.europa.eu/cases/SA.50000",
                },
                {
                    "beneficiary_name": "Trumpf GmbH",
                    "granting_authority": "BAFA",
                    "country_code": "DE",
                    "nuts_code": "DE21",
                    "aid_amount_eur": 500000.0,
                    "granting_date": "2024-01-15",
                    "sa_reference": None,
                    "case_url": None,
                },
            ],
            sa_references=["SA.50000"],
            case_urls=["https://competition-cases.ec.europa.eu/cases/SA.50000"],
            by_year=[
                {"year": 2023, "count": 1, "total_eur": 1000000.0},
                {"year": 2024, "count": 1, "total_eur": 500000.0},
            ],
            by_authority=[
                {"key": "BMWK", "count": 1, "total_eur": 1000000.0},
                {"key": "BAFA", "count": 1, "total_eur": 500000.0},
            ],
            by_nuts=[
                {"nuts_code": "DE1", "count": 1, "total_eur": 1000000.0},
                {"nuts_code": "DE2", "count": 1, "total_eur": 500000.0},
            ],
            by_instrument=[],
        ),
        beneficiaries=BeneficiariesSection(
            total_count=1,
            total_amount_eur=200000.0,
            matches=[{
                "company_name": "Trumpf GmbH",
                "project_name": "Lasertechnik-Innovation",
                "aktenzeichen": "EFRE-2023/0042",
                "bundesland": "Baden-Wuerttemberg",
                "fonds": "EFRE",
                "kosten": 200000.0,
                "kosten_label": "200.000,00 EUR",
                "source": "transparenzliste_hessen",
            }],
            by_bundesland=[
                {"key": "Baden-Wuerttemberg", "count": 1, "total_eur": 200000.0},
            ],
            by_fonds=[
                {"key": "EFRE", "count": 1, "total_eur": 200000.0},
            ],
        ),
        sanctions=SanctionsSection(total_hits=0, hits=[], listing_sources=[]),
        cross_references=[
            CrossReference(
                type="sa_reference_kom_case_linked",
                description="SA-Referenz 'SA.50000' verlinkt einen Beihilfen-Fall.",
                evidence={
                    "sa_reference": "SA.50000",
                    "case_url": "https://competition-cases.ec.europa.eu/cases/SA.50000",
                    "beneficiary": "Trumpf GmbH",
                },
            ),
        ],
        data_freshness={
            "state_aid": {"as_of": "2026-05-01T10:00:00", "record_count": 171257,
                           "note": "Letzter Harvest 2026-05-01"},
            "beneficiaries": {"as_of": None, "note": "Lokale Uploads"},
            "sanctions": {"as_of": "2026-05-07T12:00:00+00:00",
                            "record_count": 5400, "note": "FSF 2026-05-07"},
        },
        sources_explanation=[
            SourceExplanation(
                name="EU-State-Aid Transparency Aid Module (TAM)",
                url="https://webgate.ec.europa.eu/competition/transparency/public",
                description="Veroeffentlichungspflichtige Beihilfen nach AGVO.",
                last_data_update=datetime(2026, 5, 1, 10, 0, 0),
                record_count=171257,
            ),
            SourceExplanation(
                name="Beguenstigtenverzeichnis (Transparenzlisten)",
                url="(lokale Uploads)",
                description="Hochgeladene Transparenzlisten der Bundeslaender.",
                last_data_update=None,
                record_count=12345,
            ),
            SourceExplanation(
                name="EU Konsolidierte Finanzsanktionsliste (FSF)",
                url="https://data.opensanctions.org/datasets/latest/eu_fsf",
                description="Personen/Organisationen unter Finanzsanktionen.",
                last_data_update=datetime(2026, 5, 7, 12, 0, 0),
                record_count=5400,
            ),
        ],
        disclaimer=(
            "Diese Anwendung ist eine kostenlose Demonstrations- und "
            "Pruefhilfe. Sie wurde von einem einzelnen EFRE-Pruefer als "
            "Eigeninitiative entwickelt und stellt KEINE offizielle "
            "behoerdliche Anwendung dar. Es wird KEINERLEI GEWAEHRLEISTUNG "
            "uebernommen."
        ),
    )


def test_render_audit_report_pdf_liefert_valide_pdf_bytes():
    """PDF-Bytes muessen mit '%PDF' beginnen (Magic Bytes)."""
    try:
        import fitz  # noqa: F401
    except Exception:  # noqa: BLE001
        pytest.skip("pymupdf nicht verfuegbar")

    from services.state_aid_audit_pdf import render_audit_report_pdf
    data = _build_minimal_audit_data()
    pdf = render_audit_report_pdf(data)
    assert isinstance(pdf, bytes)
    assert pdf[:4] == b"%PDF"
    # Mindestens mehrere KB an Inhalt — sonst wuerde nichts gerendert worden sein
    assert len(pdf) > 3000


def test_render_audit_report_pdf_enthaelt_pflichthinweis():
    """Generiertes PDF muss den Pflichthinweis und Auftraggeber enthalten."""
    try:
        import fitz  # type: ignore
    except Exception:  # noqa: BLE001
        pytest.skip("pymupdf nicht verfuegbar")

    from services.state_aid_audit_pdf import render_audit_report_pdf
    data = _build_minimal_audit_data()
    pdf = render_audit_report_pdf(data)

    # Text aus PDF extrahieren und auf Pflicht-Begriffe pruefen
    doc = fitz.open(stream=pdf, filetype="pdf")
    full_text = "\n".join(page.get_text() for page in doc)
    doc.close()

    # Pflichthinweis-Bausteine
    assert "TAM" in full_text or "Transparency Aid" in full_text
    assert "FSF" in full_text or "OpenSanctions" in full_text
    # Auftraggeber im Footer (Aktenzeichen wurde Mai 2026 entfernt).
    assert "EFRE-Pruefbehoerde Hessen" in full_text
    # Aktenzeichen darf NICHT mehr vorkommen.
    assert "TEST/01" not in full_text
    # Faktischer Stil — keine Bewertungs-Begriffe
    full_lower = full_text.lower()
    for forbidden in ("risiko-score", "ampel"):
        assert forbidden not in full_lower


def test_render_audit_report_pdf_enthaelt_detail_tabellen():
    """Detail-Tabellen muessen Spaltenkoepfe Beguenstigter, Region etc. zeigen."""
    try:
        import fitz  # type: ignore
    except Exception:  # noqa: BLE001
        pytest.skip("pymupdf nicht verfuegbar")

    from services.state_aid_audit_pdf import render_audit_report_pdf
    data = _build_minimal_audit_data()
    pdf = render_audit_report_pdf(data)

    doc = fitz.open(stream=pdf, filetype="pdf")
    full_text = "\n".join(page.get_text() for page in doc)
    doc.close()

    # State-Aid-Sektion: Detail-Tabellen-Spaltenkoepfe (Code nutzt echte Umlaute)
    assert "Begünstigter" in full_text or "Beguenstigter" in full_text
    assert "Region" in full_text
    assert "Behörde" in full_text or "Behoerde" in full_text
    assert "SA-Ref" in full_text

    # Beneficiaries-Sektion: Spaltenkopf Vorhaben + Aktenzeichen-Spalte
    # (Vorhaben-Aktenzeichen aus dem Beneficiary-Record, NICHT Pruefer-Akz.)
    assert "Vorhaben" in full_text
    # Konkret: das Vorhaben-Aktenzeichen aus den Test-Daten muss erscheinen.
    assert "EFRE-2023/0042" in full_text

    # Sanctions-Sektion: bei 0 Treffern erscheint die Hinweis-Zeile
    assert "Keine Treffer für die Organisation" in full_text


def test_render_audit_report_pdf_enthaelt_sources_und_disclaimer():
    """PDF muss Quellen-Erlaeuterung + Disclaimer-Block enthalten."""
    try:
        import fitz  # type: ignore
    except Exception:  # noqa: BLE001
        pytest.skip("pymupdf nicht verfuegbar")

    from services.state_aid_audit_pdf import render_audit_report_pdf
    data = _build_minimal_audit_data()
    pdf = render_audit_report_pdf(data)

    doc = fitz.open(stream=pdf, filetype="pdf")
    full_text = "\n".join(page.get_text() for page in doc)
    doc.close()

    # Quellen-Sektion
    assert "Quellen und Datenstand" in full_text
    assert "Transparency Aid Module" in full_text
    assert "Beguenstigtenverzeichnis" in full_text or "Begünstigtenverzeichnis" in full_text
    assert "OpenSanctions" in full_text or "FSF" in full_text

    # Disclaimer-Block
    assert "Hinweise zur Anwendung" in full_text
    assert "kostenlose" in full_text or "Demonstrations" in full_text
    assert "GEWAEHRLEISTUNG" in full_text or "Gewährleistung" in full_text.lower() or \
           "gewaehrleistung" in full_text.lower()


def test_render_audit_report_pdf_keine_severity_woerter():
    """Strenger Test: kein bewertendes Vokabular im PDF-Text."""
    try:
        import fitz  # type: ignore
    except Exception:  # noqa: BLE001
        pytest.skip("pymupdf nicht verfuegbar")

    from services.state_aid_audit_pdf import render_audit_report_pdf
    data = _build_minimal_audit_data()
    pdf = render_audit_report_pdf(data)
    doc = fitz.open(stream=pdf, filetype="pdf")
    full_text = "\n".join(page.get_text() for page in doc).lower()
    doc.close()
    # Diese Begriffe duerfen nicht vorkommen — der Bericht ist neutral.
    forbidden = [
        "risiko-score", "risikobewertung",
        "verdächtig", "verdaechtig",
        "auffällig", "auffaellig",
    ]
    for word in forbidden:
        assert word not in full_text, (
            f"PDF enthaelt bewertendes Wort '{word}' — Bericht muss neutral sein."
        )


# ── AuditReportLog: Modell-Smoketest ─────────────────────────────────────────


def test_audit_report_log_modell_hat_pflichtfelder():
    """Stellt sicher, dass das Modell die im Plan geforderten Spalten hat.

    Aktenzeichen wurde Mai 2026 ganz entfernt — darf nicht mehr Teil der
    Pflicht-Spalten sein.
    """
    from models.state_aid_audit import AuditReportLog
    cols = {c.name for c in AuditReportLog.__table__.columns}
    pflicht = {
        "id", "created_at", "query", "auftraggeber",
        "pruefer_name", "pruefer_user_id", "state_aid_hits",
        "beneficiaries_hits", "sanctions_hits", "cross_references",
        "pdf_size_bytes", "pdf_sha256",
    }
    fehlend = pflicht - cols
    assert not fehlend, f"Felder fehlen am AuditReportLog: {fehlend}"
    # Aktenzeichen darf NICHT mehr vorhanden sein.
    assert "aktenzeichen" not in cols, (
        "Spalte 'aktenzeichen' wurde Mai 2026 entfernt — darf nicht mehr "
        "im Modell sein."
    )


def test_audit_report_log_tabellenname_korrekt():
    from models.state_aid_audit import AuditReportLog
    assert AuditReportLog.__tablename__ == "workshop_audit_report_log"


# ── Quellen-Erlaeuterung + Disclaimer ────────────────────────────────────────


def test_disclaimer_text_nicht_leer_und_neutral():
    """Disclaimer enthaelt Pflicht-Bausteine und kein Bewertungs-Vokabular."""
    from services.state_aid_audit_report import _build_disclaimer_text
    txt = _build_disclaimer_text()
    assert isinstance(txt, str)
    assert len(txt) > 100
    # Pflicht-Bausteine
    lower = txt.lower()
    assert "kostenlose" in lower
    assert "gewaehrleistung" in lower or "gewährleistung" in lower
    assert "demonstrations" in lower or "pruefhilfe" in lower or "prüfhilfe" in lower
    assert "datenschutz" in lower
    # KEIN Bewertungsvokabular
    for forbidden in ("risiko-score", "ampel", "verdaechtig", "verdächtig"):
        assert forbidden not in lower


def test_audit_report_data_serialisiert_sources_explanation_drei_eintraege():
    """Wenn `sources_explanation` gesetzt ist, soll to_dict() es vollstaendig
    serialisieren mit den drei erwarteten Quellen.
    """
    from services.state_aid_audit_report import (
        AuditReportData, BeneficiariesSection, SanctionsSection,
        SourceExplanation, StateAidSection,
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
        sources_explanation=[
            SourceExplanation(
                name="EU-State-Aid Transparency Aid Module (TAM)",
                url="https://webgate.ec.europa.eu/competition/transparency/public",
                description="…",
                last_data_update=datetime(2026, 5, 1),
                record_count=170000,
            ),
            SourceExplanation(
                name="Beguenstigtenverzeichnis (Transparenzlisten)",
                url="(lokal)",
                description="…",
                last_data_update=None,
                record_count=12000,
            ),
            SourceExplanation(
                name="EU Konsolidierte Finanzsanktionsliste (FSF)",
                url="https://data.opensanctions.org/datasets/latest/eu_fsf",
                description="…",
                last_data_update=datetime(2026, 5, 7),
                record_count=5400,
            ),
        ],
        disclaimer="Disclaimer-Test",
    )
    out = data.to_dict()
    assert "sources_explanation" in out
    assert len(out["sources_explanation"]) == 3
    # Erste Quelle: TAM mit ISO-Datum
    tam = out["sources_explanation"][0]
    assert "TAM" in tam["name"]
    assert tam["record_count"] == 170000
    assert tam["last_data_update"] == "2026-05-01T00:00:00"
    # Zweite Quelle: Beneficiaries ohne Datum
    ben = out["sources_explanation"][1]
    assert ben["last_data_update"] is None
    assert ben["record_count"] == 12000
    # Dritte Quelle: FSF mit Datum
    fsf = out["sources_explanation"][2]
    assert "FSF" in fsf["name"]
    assert fsf["record_count"] == 5400
    # Disclaimer ist gesetzt
    assert out["disclaimer"] == "Disclaimer-Test"
