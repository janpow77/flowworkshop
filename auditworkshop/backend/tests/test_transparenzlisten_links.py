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


# ── Umzug einer Portalseite ──────────────────────────────────────────────────


class _Antwort:
    def __init__(self, url, text="", inhalt=b"", status=200):
        self.url = url
        self.text = text
        self.content = inhalt
        self.status_code = status


class _Website:
    """Nachbau einer Behörden-Website als Landkarte URL → Antwort.

    Der Aufbau folgt dem echten Fall Thüringen: die alte Unterseite ist fort,
    die Startseite verlinkt aber weiterhin auf die neue.
    """

    def __init__(self, seiten: dict[str, _Antwort]):
        self.seiten = seiten
        self.abrufe: list[str] = []

    def get(self, url, headers=None):
        self.abrufe.append(url)
        antwort = self.seiten.get(url)
        if antwort is None:
            return _Antwort(url, "<html>404</html>", b"<html>404</html>", 404)
        return antwort


_XLSX = b"PK\x03\x04" + b"x" * 40


def _website_mit_umzug() -> _Website:
    start = (
        "<a href='/vorhaben-daten-und-fakten'>Vorhaben, Daten und Fakten</a>"
        "<a href='/impressum'>Impressum</a>"
    )
    zwischenseite = (
        "<a href='/vorhaben-daten-und-fakten/liste-der-vorhaben'>"
        "Liste der Vorhaben</a>"
    )
    listenseite = (
        "<a href='/dateien/Liste_der_Vorhaben_2021-2027.xlsx'>"
        "Liste der Vorhaben EFRE</a>"
    )
    return _Website({
        "https://amt.example.de/": _Antwort("https://amt.example.de/", start),
        "https://amt.example.de/vorhaben-daten-und-fakten": _Antwort(
            "https://amt.example.de/vorhaben-daten-und-fakten", zwischenseite),
        "https://amt.example.de/vorhaben-daten-und-fakten/liste-der-vorhaben":
            _Antwort(
                "https://amt.example.de/vorhaben-daten-und-fakten/liste-der-vorhaben",
                listenseite),
        "https://amt.example.de/dateien/Liste_der_Vorhaben_2021-2027.xlsx":
            _Antwort(
                "https://amt.example.de/dateien/Liste_der_Vorhaben_2021-2027.xlsx",
                "", _XLSX),
    })


def test_umgezogene_portalseite_wird_wiedergefunden():
    """Die alte Unterseite ist fort — von der Startseite aus führt der Weg
    trotzdem zur neuen Seite und zur Datei."""
    from services.transparenzlisten_links import finde_portalseite

    netz = _website_mit_umzug()
    ergebnis = finde_portalseite(
        "https://amt.example.de/alte/verschwundene-seite", netz, "EFRE")
    assert ergebnis is not None
    portal, datei = ergebnis
    assert portal.endswith("/liste-der-vorhaben")
    assert datei.endswith("Liste_der_Vorhaben_2021-2027.xlsx")


def test_suche_bleibt_auf_der_eigenen_domain():
    """Kein Ausflug auf fremde Server."""
    from services.transparenzlisten_links import finde_portalseite

    netz = _Website({
        "https://amt.example.de/": _Antwort(
            "https://amt.example.de/",
            "<a href='https://fremd.example.org/liste-der-vorhaben'>"
            "Liste der Vorhaben</a>"),
    })
    assert finde_portalseite("https://amt.example.de/weg", netz, "EFRE") is None
    assert all("fremd.example.org" not in u for u in netz.abrufe)


def test_suche_ist_begrenzt():
    """Eine gezielte Suche, kein Crawler: die Zahl geladener Seiten ist
    gedeckelt."""
    from services import transparenzlisten_links as m

    viele = "".join(
        f"<a href='/vorhaben-{i}'>Liste der Vorhaben {i}</a>" for i in range(60)
    )
    seiten = {"https://amt.example.de/": _Antwort("https://amt.example.de/", viele)}
    for i in range(60):
        u = f"https://amt.example.de/vorhaben-{i}"
        seiten[u] = _Antwort(u, "<p>nichts</p>")
    netz = _Website(seiten)

    assert m.finde_portalseite("https://amt.example.de/weg", netz) is None
    assert len(netz.abrufe) <= m.MAX_SEITEN * 2


def test_ohne_portalseite_keine_suche():
    from services.transparenzlisten_links import finde_portalseite

    netz = _Website({})
    assert finde_portalseite(None, netz) is None
    assert netz.abrufe == []


def test_fremder_fonds_schliesst_kandidaten_aus():
    """Auf der EFRE-Seite von Mecklenburg-Vorpommern trug die Datei genug
    Stichworte, um trotz Abzug durchzukommen. Die ESF-Quelle hätte dann
    EFRE-Vorhaben als ESF eingelesen."""
    from services.transparenzlisten_links import MINDEST_PUNKTE, bewerte_kandidat

    punkte = bewerte_kandidat(
        "https://x.de/serviceassistent/download?id=1686365",
        "Download (XLSX, 0,3 MB)",
        fonds="ESF",
        kontext="EFRE - Liste der Vorhaben Stand: 31.03.2026")
    assert punkte < MINDEST_PUNKTE


def test_ohne_fondsangabe_wird_nicht_ausgeschlossen():
    """Ist der Fonds unbekannt, darf die Erwähnung eines Fonds nicht schaden."""
    from services.transparenzlisten_links import MINDEST_PUNKTE, bewerte_kandidat

    punkte = bewerte_kandidat(
        "https://x.de/Liste_der_Vorhaben_2021-2027.xlsx", "Liste der Vorhaben EFRE")
    assert punkte >= MINDEST_PUNKTE


def test_seiten_des_falschen_fonds_werden_nicht_betreten():
    """Sonst landet die ESF-Quelle auf der EFRE-Seite desselben Hauses."""
    from services.transparenzlisten_links import _bewerte_seite

    assert _bewerte_seite("https://x.de/fonds/efre/", "EFRE", fonds="ESF") == 0
    assert _bewerte_seite("https://x.de/fonds/esf/", "ESF Plus", fonds="ESF") > 0
