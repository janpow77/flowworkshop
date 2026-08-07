"""
Tests für die Auflösung des aktuellen Listen-Links von der Portalseite.

Alle Fälle sind echten Landesportalen nachgebildet — sie stehen im Test
jeweils im Docstring.

Lauf: pytest backend/tests/test_transparenzlisten_links.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ── Bewertung ────────────────────────────────────────────────────────────────


def test_vorhabensliste_schlaegt_begleitmaterial():
    """Auf der hessischen Seite lag neben der Liste der „Zeitplan der
    geplanten Aufrufe" — ebenfalls eine XLSX, aber die falsche Datei."""
    from services.transparenzlisten_links import bewerte_kandidat

    liste = bewerte_kandidat(
        "https://x.de/liste_der_vorhaben_2021-2027.xlsx", "Liste der Vorhaben")
    zeitplan = bewerte_kandidat(
        "https://x.de/zeitplan_der_geplanten_aufrufe.xlsx", "Zeitplan")
    assert liste > zeitplan


def test_laufende_periode_schlaegt_alte():
    """Baden-Württemberg und Hessen führen 2014-2020 und 2021-2027 auf
    derselben Seite."""
    from services.transparenzlisten_links import bewerte_kandidat

    neu = bewerte_kandidat(
        "https://x.de/2021-2027/Liste der Vorhaben_30-04-2026.xlsx", "Liste der Vorhaben")
    alt = bewerte_kandidat(
        "https://x.de/2014-2020/Liste der Vorhaben_31-03-2024.xlsx", "Liste der Vorhaben")
    assert neu > alt


def test_eigener_fonds_schlaegt_fremden():
    """Niedersachsen listet die EFRE- und die ESF+-Datei untereinander,
    beide heissen „Liste der Vorhaben"."""
    from services.transparenzlisten_links import bewerte_kandidat

    esf = bewerte_kandidat(
        "https://x.de/download/230555/Liste_der_Vorhaben_ESF_Stand_31.01.2026.xlsx",
        "Liste der Vorhaben ESF+", fonds="ESF")
    efre = bewerte_kandidat(
        "https://x.de/download/230554/Liste_der_Vorhaben_EFRE_Stand_31.01.2026.xlsx",
        "Liste der Vorhaben EFRE", fonds="ESF")
    assert esf > efre


def test_kontext_traegt_die_bezeichnung():
    """Mecklenburg-Vorpommern nennt den Link nur „Download (XLSX, 0,28 MB)";
    die Bezeichnung steht in der Überschrift darüber."""
    from services.transparenzlisten_links import MINDEST_PUNKTE, bewerte_kandidat

    ohne = bewerte_kandidat(
        "https://x.de/serviceassistent/download?id=1689382", "Download (XLSX, 0,28 MB)")
    mit = bewerte_kandidat(
        "https://x.de/serviceassistent/download?id=1689382",
        "Download (XLSX, 0,28 MB)",
        fonds="ESF",
        kontext="ESF Plus - Liste der Vorhaben Stand: 31.03.2026")
    assert ohne < MINDEST_PUNKTE <= mit


# ── Inhaltserkennung ─────────────────────────────────────────────────────────


def test_xlsx_wird_am_zip_kopf_erkannt():
    """Mehrere Portale liefern XLSX als octet-stream oder zip aus — der
    Content-Type taugt nicht als Kriterium."""
    from services.transparenzlisten_links import ist_tabellendatei

    ok, art = ist_tabellendatei(b"PK\x03\x04rest", "https://x.de/download?id=7")
    assert ok and art == "XLSX"


def test_fehlerseite_gilt_nicht_als_datei():
    """Der häufigste Fall eines gewanderten Links: HTTP 200 mit einer
    HTML-Fehlerseite im Rumpf."""
    from services.transparenzlisten_links import ist_tabellendatei

    ok, art = ist_tabellendatei(b"<!DOCTYPE html><html><body>404", "https://x.de/a.xlsx")
    assert not ok and "HTML" in art


def test_csv_wird_ueber_die_endung_erkannt():
    from services.transparenzlisten_links import ist_tabellendatei

    ok, art = ist_tabellendatei(b"Name;Ort\nMuster;Kassel", "https://x.de/liste.csv")
    assert ok and art == "CSV"


# ── Linksammler ──────────────────────────────────────────────────────────────


def test_sammler_liefert_text_und_kontext():
    from services.transparenzlisten_links import _LinkSammler

    sammler = _LinkSammler()
    sammler.feed(
        "<h3>ESF Plus - Liste der Vorhaben</h3>"
        "<a href='/download?id=7'>Download (XLSX)</a>"
    )
    href, text, kontext = sammler.links[0]
    assert href == "/download?id=7"
    assert text == "Download (XLSX)"
    assert "Liste der Vorhaben" in kontext
