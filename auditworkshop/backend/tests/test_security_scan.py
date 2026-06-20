"""Unit-Tests für die Webseiten-Sicherheitsprüfung (KA 6 — ISMS-Systemprüfung).

Reine Logik-Tests (Bewertung/Aggregation/Prüfkatalog) ohne Netz/DB.
"""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def test_make_finding_zieht_soll_und_bezug_aus_katalog():
    from services.security_scan.report import make_finding
    f = make_finding("TLS-01", istzustand="TLS 1.0 aktiv", bewertung="rot", empfehlung="deaktivieren")
    assert f.bezug == "TR-02102-2"
    assert "TLS 1.2" in f.sollzustand
    assert f.titel == "Unterstützte Protokollversionen"
    assert f.gruppe.startswith("Transportverschlüsselung")
    assert f.eingriffstiefe == "passiv"  # strukturell passiv


def test_finding_to_dict_enthaelt_paragraph6_felder():
    from services.security_scan.report import make_finding
    d = make_finding("HDR-01", istzustand="HSTS fehlt", bewertung="rot").to_dict()
    for key in ("pruef_id", "bezug", "sollzustand", "istzustand", "bewertung",
                "empfehlung", "rohbefund", "eingriffstiefe"):
        assert key in d, f"§6-Feld fehlt: {key}"
    assert d["bewertung_label"] == "kritische Abweichung"


def test_aggregate_schwaechste_stelle_rot():
    from services.security_scan.report import GELB, KONFORM, ROT, make_finding, aggregate
    findings = [
        make_finding("TLS-01", istzustand="ok", bewertung=KONFORM),
        make_finding("HDR-05", istzustand="fehlt", bewertung=GELB),
        make_finding("NET-01", istzustand="keine Weiterleitung", bewertung=ROT),
    ]
    agg = aggregate(findings)
    assert agg["overall"] == "kritisch"  # eine rote → Gesamt kritisch
    assert agg["counts"] == {"konform": 1, "gelb": 1, "rot": 1, "grau": 0}


def test_aggregate_nur_gelb_ist_gelb():
    from services.security_scan.report import GELB, KONFORM, make_finding, aggregate
    findings = [
        make_finding("TLS-01", istzustand="ok", bewertung=KONFORM),
        make_finding("HDR-02", istzustand="CSP fehlt", bewertung=GELB),
    ]
    assert aggregate(findings)["overall"] == "gelb"


def test_aggregate_alles_konform():
    from services.security_scan.report import KONFORM, make_finding, aggregate
    findings = [make_finding(pid, istzustand="ok", bewertung=KONFORM) for pid in ("TLS-01", "HDR-01", "COO-01")]
    assert aggregate(findings)["overall"] == "konform"


def test_grau_verschlechtert_gesamtbewertung_nicht():
    from services.security_scan.report import GRAU, KONFORM, make_finding, aggregate
    findings = [
        make_finding("TLS-01", istzustand="ok", bewertung=KONFORM),
        make_finding("NET-03", istzustand="nicht prüfbar", bewertung=GRAU),
    ]
    assert aggregate(findings)["overall"] == "konform"


def test_normalize_target_ergaenzt_https():
    from services.security_scan.engine import normalize_target
    norm, host, port = normalize_target("beispiel-behoerde.example")
    assert norm == "https://beispiel-behoerde.example"
    assert host == "beispiel-behoerde.example"
    assert port == 443
