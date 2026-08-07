"""
Tests für das Auslesen einer „Liste der Vorhaben" aus einem PDF.

Das Saarland veröffentlicht seine Liste ausschließlich als PDF. Die Datei
enthält echten Text — Texterkennung ist dafür nicht nötig und bleibt
gescannten Dokumenten vorbehalten.

Lauf: pytest backend/tests/test_pdf_vorhabenliste.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ── Zellen und Kopfzeilen ────────────────────────────────────────────────────


def test_zeilenumbruch_in_der_zelle_wird_geglaettet():
    """In PDF-Tabellen bricht langer Text mitten in der Zelle um. Das ist
    Layout, keine Bedeutung."""
    from services.pdf_vorhabenliste import _saeubere

    assert _saeubere("Gesamtkosten des\nVorhabens") == "Gesamtkosten des Vorhabens"
    assert _saeubere(None) == ""
    assert _saeubere("  viel   Luft  ") == "viel Luft"


def test_kopfzeile_wird_an_der_beguenstigtenspalte_erkannt():
    from services.pdf_vorhabenliste import _ist_kopfzeile

    assert _ist_kopfzeile(["Vorhaben-ID", "Name des Begünstigten", "Beginn"])
    assert _ist_kopfzeile(["ID", "Beneficiary name", "Start"])
    assert not _ist_kopfzeile(["EFRE-0000439", "anyhelpnow GmbH", "01.11.2023"])


# ── Scan-Erkennung ───────────────────────────────────────────────────────────


def _pdf_mit_text(text: str, zeilen: int = 1) -> bytes:
    """Baut ein PDF mit echtem Text.

    Bewusst mehrere kurze Zeilen statt einer langen: eine Zeile, die über
    den Seitenrand hinausläuft, wird beim Auslesen abgeschnitten.
    """
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    seite = doc.new_page()
    for i in range(zeilen):
        if text:
            seite.insert_text((72, 72 + i * 14), text)
    return doc.tobytes()


def test_textpdf_gilt_nicht_als_scan():
    from services.pdf_vorhabenliste import ist_gescannt

    inhalt = _pdf_mit_text("Name des Beguenstigten der Foerderung", zeilen=20)
    assert ist_gescannt(inhalt) is False


def test_pdf_ohne_text_gilt_als_scan():
    from services.pdf_vorhabenliste import ist_gescannt

    assert ist_gescannt(_pdf_mit_text("")) is True


def test_scan_ohne_texterkennung_wird_klar_abgelehnt(monkeypatch):
    """Ein stillschweigend per Texterkennung gelesener Förderbetrag hat in
    einem Prüfdatenbestand nichts verloren — der Lauf sagt deutlich, was
    fehlt."""
    from services import pdf_vorhabenliste as m

    monkeypatch.setattr(m, "PDF_OCR_AKTIV", False)
    with pytest.raises(ValueError) as fehler:
        m.lies_vorhabenliste(_pdf_mit_text(""))
    text = str(fehler.value)
    assert "Scan" in text and "BENEFICIARY_PDF_OCR" in text


# ── Zusammenbau der Tabelle ──────────────────────────────────────────────────


def test_zeilen_werden_auf_die_kopfbreite_gebracht(monkeypatch):
    """PDF-Tabellen liefern gelegentlich zu kurze oder zu lange Zeilen."""
    from services import pdf_vorhabenliste as m

    monkeypatch.setattr(m, "ist_gescannt", lambda _inhalt: False)
    monkeypatch.setattr(m, "lies_tabelle", lambda _inhalt: [
        ["Vorhaben-ID", "Name des Begünstigten", "Ort"],
        ["EFRE-1", "Muster GmbH", "66111 Saarbrücken"],
        ["EFRE-2", "Zu kurz"],
        ["EFRE-3", "Zu lang", "66450 Bexbach", "überzählig"],
    ])
    df = m.lies_vorhabenliste(b"egal")
    assert list(df.columns) == ["Vorhaben-ID", "Name des Begünstigten", "Ort"]
    assert len(df) == 3
    assert df.iloc[1]["Ort"] == ""
    assert df.iloc[2]["Ort"] == "66450 Bexbach"


def test_fehlende_kopfzeile_bricht_verstaendlich_ab(monkeypatch):
    """Ohne erkennbare Begünstigtenspalte wird nicht geraten, sondern die
    Ursache benannt."""
    from services import pdf_vorhabenliste as m

    def _ohne_kopf(_inhalt):
        raise ValueError(
            "Im PDF wurde keine Kopfzeile mit einer Begünstigtenspalte gefunden."
        )

    monkeypatch.setattr(m, "ist_gescannt", lambda _inhalt: False)
    monkeypatch.setattr(m, "lies_tabelle", _ohne_kopf)
    with pytest.raises(ValueError, match="Kopfzeile"):
        m.lies_vorhabenliste(b"egal")
