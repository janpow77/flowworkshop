#!/usr/bin/env python3
"""
Sucht auf den Portalseiten der Länder nach dem aktuellen Link zur
„Liste der Vorhaben" und prüft ihn.

Warum das nötig ist: die Länder veröffentlichen ihre Listen unter
versionierten Dateinamen (``…Liste_der_Vorhaben_31-12-2024.xlsx``). Mit
jeder neuen Veröffentlichung wechselt der Name, der bisherige Direktlink
läuft ins Leere. Die Portalseite bleibt dagegen stabil — dort steht immer
der aktuelle Link.

Vorgehen je Quelle:
  1. Portalseite laden
  2. alle Verweise auf XLSX/XLS/CSV einsammeln (auch relative)
  3. nach Stichworten bewerten („Liste der Vorhaben", „Begünstigte", …)
  4. Kandidaten der Reihe nach abrufen und am Inhalt prüfen: eine XLSX ist
     ein ZIP-Archiv und beginnt mit ``PK\\x03\\x04``
  5. den ersten Treffer melden, der wirklich eine Datei liefert

Das Skript schreibt nichts von selbst. Mit ``--schreiben`` aktualisiert es
die Registry ``data/transparenzlisten_urls.json``.

Aufruf:
    python3 scripts/finde_transparenzlisten_links.py
    python3 scripts/finde_transparenzlisten_links.py --nur "Bremen ESF"
    python3 scripts/finde_transparenzlisten_links.py --schreiben
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

REGISTRY = Path(__file__).resolve().parent.parent / "data" / "transparenzlisten_urls.json"

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
STICHWORTE = (
    ("liste der vorhaben", 10),
    ("liste_der_vorhaben", 10),
    ("list of operations", 8),
    ("vorhabensliste", 8),
    ("liste-der-vorhaben", 10),
    ("begünstigt", 4),
    ("beguenstigt", 4),
    ("beneficiar", 4),
    ("vorhaben", 3),
    ("projektliste", 3),
    ("operations", 2),
)

# Mindestpunktzahl, damit ein Fund uebernommen wird. Ohne sie rutschen
# thematisch benachbarte Dateien durch — auf der hessischen Portalseite etwa
# der "Zeitplan der geplanten Aufrufe", der zwar eine XLSX ist, aber keine
# Liste der Vorhaben.
MINDEST_PUNKTE = 8

# Diese Begriffe sprechen gegen einen Treffer (Begleitmaterial statt Liste).
GEGENWORTE = ("erläuterung", "erlaeuterung", "hinweis", "muster", "vorlage",
              "formular", "antrag", "merkblatt", "leitfaden")


class _LinkSammler(HTMLParser):
    """Sammelt href-Ziele samt sichtbarem Linktext."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._aktuell: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self._aktuell = href
            self._text = []

    def handle_data(self, data):
        if self._aktuell is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._aktuell is not None:
            self.links.append((self._aktuell, " ".join(self._text).strip()))
            self._aktuell = None
            self._text = []


def bewerte_kandidat(url: str, linktext: str) -> int:
    """Punktzahl aus Adresse und Linktext."""
    heu = f"{unquote(url)} {linktext}".lower()
    punkte = 0
    for wort, gewicht in STICHWORTE:
        if wort in heu:
            punkte += gewicht
    for wort in GEGENWORTE:
        if wort in heu:
            punkte -= 6
    # Ein Jahr im Namen deutet auf eine datierte Liste hin.
    if re.search(r"20(2[3-9]|3[0-9])", heu):
        punkte += 2
    if heu.strip().endswith(".xlsx"):
        punkte += 1
    return punkte


def hole(url: str, client: httpx.Client, nur_kopf: bool = False) -> httpx.Response | None:
    try:
        if nur_kopf:
            return client.get(url, headers={**HTTP_HEADERS, "Range": "bytes=0-2047"})
        return client.get(url)
    except Exception:
        return None


def pruefe_datei(url: str, client: httpx.Client) -> tuple[bool, str]:
    """Ruft den Kandidaten ab und prüft am Inhalt, ob es eine Tabelle ist."""
    r = hole(url, client, nur_kopf=True)
    if r is None:
        # Manche Server (Brandenburg: sixcms/media.php) antworten auf
        # Teilabrufe gar nicht. Dann die Datei vollstaendig holen.
        r = hole(url, client)
    if r is None:
        return False, "nicht erreichbar"
    if r.status_code not in (200, 206):
        return False, f"HTTP {r.status_code}"
    inhalt = r.content
    if inhalt[:4] == b"PK\x03\x04":
        return True, "XLSX"
    if inhalt[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return True, "XLS (altes Format)"
    if b"<html" in inhalt[:2000].lower():
        return False, "HTML-Seite statt Datei"
    if url.lower().split("?")[0].endswith(".csv"):
        return True, "CSV"
    return False, f"unbekanntes Format ({inhalt[:8]!r})"


def suche_fuer_portal(portal: str, client: httpx.Client) -> list[dict]:
    """Liefert bewertete, geprüfte Kandidaten der Portalseite."""
    r = hole(portal, client)
    if r is None or r.status_code != 200:
        code = "nicht erreichbar" if r is None else f"HTTP {r.status_code}"
        print(f"    Portalseite {code}")
        return []

    sammler = _LinkSammler()
    try:
        sammler.feed(r.text)
    except Exception:
        pass

    kandidaten: list[tuple[int, str, str]] = []
    gesehen: set[str] = set()
    for href, text in sammler.links:
        voll = urljoin(str(r.url), href)
        pfad = unquote(voll.split("?")[0]).lower()
        if not pfad.endswith(DATEI_ENDUNGEN):
            continue
        if voll in gesehen:
            continue
        gesehen.add(voll)
        kandidaten.append((bewerte_kandidat(voll, text), voll, text))

    kandidaten.sort(key=lambda k: -k[0])
    ergebnis: list[dict] = []
    for punkte, url, text in kandidaten[:6]:
        ok, art = pruefe_datei(url, client)
        ergebnis.append({"punkte": punkte, "url": url, "text": text[:60],
                         "ok": ok, "art": art})
        if ok:
            break
    return ergebnis


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--schreiben", action="store_true",
                    help="gefundene Links in die Registry übernehmen")
    ap.add_argument("--nur", nargs="*", default=None,
                    help='nur diese Quellen, z.B. "Bremen ESF"')
    ap.add_argument("--alle", action="store_true",
                    help="auch Quellen prüfen, die derzeit als ok gelten")
    args = ap.parse_args()

    daten = json.loads(REGISTRY.read_text(encoding="utf-8"))
    quellen = daten["sources"]

    treffer: dict[int, str] = {}
    with httpx.Client(timeout=60, follow_redirects=True, headers=HTTP_HEADERS,
                      verify=False) as client:
        for idx, e in enumerate(quellen):
            bezeichnung = f"{e.get('bundesland')} {e.get('fonds')}"
            if args.nur and bezeichnung not in args.nur:
                continue
            if not args.alle and (e.get("status") or "") == "ok":
                continue
            portal = e.get("portal")
            print(f"\n{bezeichnung}")
            if not portal:
                print("    keine Portalseite hinterlegt — Recherche nötig")
                continue

            gefunden = suche_fuer_portal(portal, client)
            if not gefunden:
                print("    keine Tabellen-Verweise auf der Portalseite")
                continue
            for k in gefunden:
                marke = "✓" if k["ok"] else "·"
                print(f"    {marke} [{k['punkte']:>3}] {k['art']:<22} {k['url'][:88]}")
            beste = next(
                (k for k in gefunden if k["ok"] and k["punkte"] >= MINDEST_PUNKTE),
                None,
            )
            if beste:
                treffer[idx] = beste["url"]
            else:
                schwach = next((k for k in gefunden if k["ok"]), None)
                if schwach:
                    print(f"    verworfen — Punktzahl {schwach['punkte']} unter "
                          f"{MINDEST_PUNKTE}, vermutlich nicht die Vorhabensliste")

    print(f"\n{'='*74}\nVerifizierte neue Links: {len(treffer)}")
    if not args.schreiben:
        print("Probelauf — Registry unverändert. Mit --schreiben übernehmen.")
        return 0

    for idx, url in treffer.items():
        quellen[idx]["url"] = url
        quellen[idx]["status"] = "ok"
        quellen[idx]["notes"] = "Link am 2026-08-07 von der Portalseite aktualisiert"
    daten["_updated"] = "2026-08-07"
    REGISTRY.write_text(json.dumps(daten, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(f"Registry aktualisiert: {len(treffer)} Links.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
