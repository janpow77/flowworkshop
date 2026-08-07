"""
flowworkshop · services/transparenzlisten_links.py

Ermittelt den aktuellen Download-Link einer „Liste der Vorhaben" von der
Portalseite eines Landes.

Hintergrund: die Länder veröffentlichen ihre Listen unter versionierten
Dateinamen (``…Liste_der_Vorhaben_31-12-2024.xlsx``). Mit jeder neuen
Veröffentlichung wechselt der Dateiname und der hinterlegte Direktlink läuft
ins Leere — Bremen EFRE war am 05.07.2026 erreichbar und am 06.08. tot. Die
Portalseite bleibt dagegen stabil; dort steht immer der aktuelle Verweis.

Dieses Modul wird an zwei Stellen genutzt:
  - ``scripts/finde_transparenzlisten_links.py`` — Pflege der Registry
  - ``services/scheduler.py`` — Selbstheilung im nächtlichen Harvest, wenn
    der hinterlegte Direktlink nicht mehr trägt
"""
from __future__ import annotations

import logging
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import unquote, urljoin

log = logging.getLogger(__name__)

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Auditworkshop-EFRE-Demo/1.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9",
}

DATEI_ENDUNGEN = (".xlsx", ".xls", ".xlsm", ".csv")

# Je höher die Punktzahl, desto wahrscheinlicher die gesuchte Liste.
STICHWORTE: tuple[tuple[str, int], ...] = (
    ("liste der vorhaben", 10),
    ("liste_der_vorhaben", 10),
    ("liste-der-vorhaben", 10),
    ("list of operations", 8),
    ("vorhabensliste", 8),
    ("vorhabenliste", 8),
    ("begünstigt", 4),
    ("beguenstigt", 4),
    ("beneficiar", 4),
    ("vorhaben", 3),
    ("projektliste", 3),
    ("operations", 2),
)

# Die laufende Foerderperiode. Mehrere Laender fuehren die alte Liste
# (2014-2020, Art. 115 VO 1303/2013) auf derselben Seite — Baden-Wuerttemberg
# und Hessen etwa direkt untereinander. Ohne diese Gewichtung landet leicht
# die falsche Periode im Import.
PERIODE_POSITIV = ("2021-2027", "2021_2027", "20212027", "21-27", "fp_21", "2021 bis 2027")
PERIODE_NEGATIV = ("2014-2020", "2014_2020", "20142020", "14-20", "1303/2013")

# Begleitmaterial statt Liste.
GEGENWORTE = (
    "erläuterung", "erlaeuterung", "hinweis", "muster", "vorlage",
    "formular", "antrag", "merkblatt", "leitfaden", "zeitplan", "aufruf",
)

# Mindestpunktzahl für eine Übernahme. Ohne sie rutschen thematisch
# benachbarte Dateien durch — auf der hessischen Portalseite etwa der
# „Zeitplan der geplanten Aufrufe", der zwar eine XLSX ist, aber keine
# Liste der Vorhaben.
MINDEST_PUNKTE = 8

# ZIP-Signatur (XLSX) bzw. OLE2-Signatur (altes XLS).
_ZIP_KOPF = b"PK\x03\x04"
_OLE2_KOPF = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


# So viele Zeichen Fliesstext vor einem Link fliessen in die Bewertung ein.
KONTEXT_ZEICHEN = 160


class _LinkSammler(HTMLParser):
    """Sammelt href-Ziele samt Linktext und vorangehendem Fliesstext.

    Der vorangehende Text ist noetig, weil manche Portale den Link nur
    „Download (XLSX, 0,28 MB)" nennen und die eigentliche Bezeichnung in der
    Ueberschrift darueber steht — Mecklenburg-Vorpommern etwa.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str, str]] = []
        self._aktuell: str | None = None
        self._text: list[str] = []
        self._kontext: str = ""
        self._kontext_bei_start: str = ""

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self._aktuell = href
            self._text = []
            self._kontext_bei_start = self._kontext

    def handle_data(self, data):
        if self._aktuell is not None:
            self._text.append(data)
        sauber = " ".join(data.split())
        if sauber:
            self._kontext = (self._kontext + " " + sauber)[-KONTEXT_ZEICHEN:]

    def handle_endtag(self, tag):
        if tag == "a" and self._aktuell is not None:
            self.links.append((
                self._aktuell,
                " ".join(self._text).strip(),
                self._kontext_bei_start,
            ))
            self._aktuell = None
            self._text = []


# Fonds-Kuerzel, die in Dateinamen und Linktexten vorkommen.
_FONDS_MUSTER = {
    "EFRE": r"\befre\b|\berdf\b",
    "ESF": r"\besf\b|\besf\+|\besf plus\b",
    "JTF": r"\bjtf\b",
    "AMIF": r"\bamif\b",
    "ISF": r"\bisf\b",
}


def bewerte_kandidat(url: str, linktext: str, fonds: str | None = None,
                     kontext: str = "") -> int:
    """Punktzahl aus Adresse, Linktext und umgebendem Fliesstext.

    ``fonds`` schaerft die Auswahl, wenn eine Portalseite mehrere Fonds
    fuehrt: Niedersachsen listet die EFRE- und die ESF+-Datei direkt
    untereinander, beide heissen „Liste der Vorhaben".
    """
    heu = f"{unquote(url)} {linktext} {kontext}".lower()
    punkte = 0
    for wort, gewicht in STICHWORTE:
        if wort in heu:
            punkte += gewicht
    for wort in GEGENWORTE:
        if wort in heu:
            punkte -= 6
    for wort in PERIODE_POSITIV:
        if wort in heu:
            punkte += 6
            break
    for wort in PERIODE_NEGATIV:
        if wort in heu:
            punkte -= 12
            break
    if fonds:
        ziel = fonds.strip().upper()
        for kuerzel, muster in _FONDS_MUSTER.items():
            if not re.search(muster, heu):
                continue
            if kuerzel == ziel:
                punkte += 8
            elif not (ziel == "ESF" and kuerzel == "ESF"):
                # Ein fremder Fonds im Namen spricht klar dagegen.
                punkte -= 10
    if re.search(r"20(2[3-9]|3[0-9])", heu):
        punkte += 2
    if unquote(url).lower().split("?")[0].endswith(".xlsx"):
        punkte += 1
    return punkte


def ist_tabellendatei(inhalt: bytes, url: str = "") -> tuple[bool, str]:
    """Entscheidet am Inhalt, ob eine Tabelle vorliegt.

    Bewusst nicht über den Content-Type: mehrere Landesportale liefern ihre
    XLSX als ``application/octet-stream`` oder ``application/zip`` aus.
    """
    if inhalt[:4] == _ZIP_KOPF:
        return True, "XLSX"
    if inhalt[:8] == _OLE2_KOPF:
        return True, "XLS (altes Format)"
    if b"<html" in inhalt[:2000].lower():
        return False, "HTML-Seite statt Datei"
    if url.lower().split("?")[0].endswith(".csv"):
        return True, "CSV"
    return False, "unbekanntes Format"


def _pruefe(url: str, client: Any) -> tuple[bool, str]:
    """Ruft den Kandidaten ab und prüft ihn am Inhalt."""
    for nur_kopf in (True, False):
        try:
            kopfzeilen = dict(HTTP_HEADERS)
            if nur_kopf:
                kopfzeilen["Range"] = "bytes=0-2047"
            r = client.get(url, headers=kopfzeilen)
        except Exception:
            # Manche Server (Brandenburg: sixcms/media.php) antworten auf
            # Teilabrufe gar nicht — dann die Datei vollständig holen.
            continue
        if r.status_code not in (200, 206):
            return False, f"HTTP {r.status_code}"
        return ist_tabellendatei(r.content, url)
    return False, "nicht erreichbar"


def sammle_kandidaten(portal: str, client: Any,
                      fonds: str | None = None) -> list[dict]:
    """Bewertete, geprüfte Kandidaten einer Portalseite (bester zuerst)."""
    try:
        r = client.get(portal, headers=HTTP_HEADERS)
    except Exception as exc:  # noqa: BLE001
        log.info("Portalseite %s nicht erreichbar: %s", portal, exc)
        return []
    if r.status_code != 200:
        log.info("Portalseite %s liefert HTTP %s", portal, r.status_code)
        return []

    sammler = _LinkSammler()
    try:
        sammler.feed(r.text)
    except Exception:  # noqa: BLE001 — kaputtes HTML darf nicht abbrechen
        pass

    roh: list[tuple[int, str, str]] = []
    gesehen: set[str] = set()
    for href, text, kontext in sammler.links:
        voll = urljoin(str(r.url), href)
        if voll in gesehen:
            continue
        pfad = unquote(voll.split("?")[0]).lower()
        # Nicht jede Quelle verrät den Typ in der Adresse: Mecklenburg-
        # Vorpommern liefert über einen Download-Handler ohne Endung
        # (``/serviceassistent/download?id=…``) und nennt das Format nur im
        # Linktext. Solche Verweise kommen mit in die Auswahl — geprüft wird
        # ohnehin am Inhalt.
        endung_passt = pfad.endswith(DATEI_ENDUNGEN)
        text_verraet_typ = bool(re.search(r"\b(xlsx?|csv)\b", text, re.IGNORECASE))
        handler = "download" in pfad and text_verraet_typ
        if not (endung_passt or handler):
            continue
        gesehen.add(voll)
        roh.append((bewerte_kandidat(voll, text, fonds, kontext), voll, text))

    roh.sort(key=lambda k: -k[0])
    ergebnis: list[dict] = []
    for punkte, url, text in roh[:6]:
        ok, art = _pruefe(url, client)
        ergebnis.append({"punkte": punkte, "url": url, "text": text[:60],
                         "ok": ok, "art": art})
        if ok and punkte >= MINDEST_PUNKTE:
            break
    return ergebnis


def finde_datei_link(portal: str | None, client: Any,
                     fonds: str | None = None) -> str | None:
    """Liefert den aktuellen Datei-Link der Portalseite — oder None.

    Nur Kandidaten, die tatsächlich eine Tabelle ausliefern UND die
    Mindestpunktzahl erreichen, werden zurückgegeben.
    """
    if not portal:
        return None
    for k in sammle_kandidaten(portal, client, fonds):
        if k["ok"] and k["punkte"] >= MINDEST_PUNKTE:
            return k["url"]
    return None
