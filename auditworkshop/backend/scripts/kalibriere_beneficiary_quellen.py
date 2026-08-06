#!/usr/bin/env python3
"""
Kalibriert Blatt, Kopfzeile und Spaltenzuordnung je Transparenzliste.

Jedes Bundesland liefert seine Liste der Vorhaben in einem eigenen Format:
Vorspann über mehreren Zeilen, zweisprachige oder mehrzeilige Überschriften,
teils englische Spaltennamen, teils ein zweites Blatt mit Erläuterungen. Ohne
gepflegte Angaben findet die Auto-Erkennung die Namensspalte nicht und der
Import bricht ab.

Statt die Kopfzeile zu raten, probiert dieses Skript sie aus: Für jedes Blatt
und jede Kopfzeile 0–14 lässt es dieselbe Spaltenerkennung laufen, die auch
der Harvester nutzt (``_detect_canonical_columns``), und zählt, wie viele
Zeilen dabei einen nicht leeren Begünstigtennamen ergeben. Gewonnen hat die
Kombination mit den meisten gültigen Zeilen.

Findet die Auto-Erkennung keine Namensspalte, sucht das Skript sie über eine
Liste bekannter Bezeichnungen (deutsch und englisch) und schreibt ein
explizites ``field_mapping``.

Aufruf (im Backend-Container):
    python3 scripts/kalibriere_beneficiary_quellen.py --dry-run
    python3 scripts/kalibriere_beneficiary_quellen.py --apply
    python3 scripts/kalibriere_beneficiary_quellen.py --apply --nur sachsen_efre_2021_2027
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import unicodedata
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
import pandas as pd  # noqa: E402

from database import SessionLocal  # noqa: E402
from models.beneficiary_sources_config import BeneficiarySourceConfig  # noqa: E402
from services.beneficiary_harvester import _detect_canonical_columns  # noqa: E402

REGISTRY = Path(__file__).resolve().parent.parent / "data" / "transparenzlisten_urls.json"
HTTP_HEADERS = {"User-Agent": "Auditworkshop-EFRE-Demo/1.0 (Workshop)"}
MAX_HEADER_ROW = 14
FONDS_TOKENS = ("efre", "esf", "jtf", "amif", "isf")

# Bekannte Bezeichnungen der Pflichtspalten, in der Reihenfolge ihrer
# Aussagekraft. Wird nur gebraucht, wenn die Auto-Erkennung nichts findet.
BEKANNTE_SPALTEN: dict[str, tuple[str, ...]] = {
    "name": (
        "name des begünstigten", "name des beguenstigten", "zuwendungsempfänger",
        "zuwendungsempfaenger", "begünstigter", "beneficiary name", "beneficiary",
        "name of beneficiary", "name of the beneficiary",
    ),
    "projekt": (
        "bezeichnung des vorhabens", "projekttitel", "operation name",
        "name of the operation", "bezeichnung", "projektbezeichnung",
    ),
    "beschreibung": (
        "zweck", "projektkurzbeschreibung", "zusammenfassung", "purpose",
        "projektbeschreibung", "beschreibung",
    ),
    "aktenzeichen": (
        "projektnummer", "code des vorhabens", "vorhabens-id", "operation id",
        "identifikationsnummer", "aktenzeichen", "unique operation id", "id",
    ),
    "kosten": (
        "gesamtkosten", "förderfähige gesamtkosten", "total cost",
        "gesamtbetrag", "total eligible",
    ),
    "plz": ("plz", "postleitzahl", "post code", "postcode", "postal code"),
    "ort": ("durchführungsort", "investitionsort", "ort", "location", "standort"),
    "beginn": ("beginn", "start date", "projektbeginn", "start"),
    "ende": ("ende", "abschluss", "end date", "projektende"),
}


def norm(value: str | None) -> str:
    s = (value or "").lower().strip()
    for a, b in (("ä", "a"), ("ö", "o"), ("ü", "u"), ("ß", "ss")):
        s = s.replace(a, b)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return s.replace("ue", "u").replace("oe", "o").replace("ae", "a").replace("-", "").replace(" ", "")


def split_key(source_key: str) -> tuple[str, str]:
    parts = source_key.split("_")
    for i, part in enumerate(parts):
        if part in FONDS_TOKENS:
            return norm("_".join(parts[:i])), part
    return norm(source_key), ""


def lade_registry() -> dict[tuple[str, str], dict]:
    eintraege = json.loads(REGISTRY.read_text(encoding="utf-8"))["sources"]
    by_key: dict[tuple[str, str], dict] = {}
    for e in eintraege:
        by_key.setdefault((norm(e.get("bundesland")), (e.get("fonds") or "").lower()), e)
    return by_key


def suche_spalte(headers: list[str], alias: str) -> str | None:
    """Findet eine Spalte über bekannte Bezeichnungen (Teilstring-Vergleich)."""
    for begriff in BEKANNTE_SPALTEN.get(alias, ()):
        b = norm(begriff)
        treffer = [h for h in headers if b in norm(h)]
        if treffer:
            return min(treffer, key=len)
    return None


def bewerte(df: pd.DataFrame) -> tuple[int, int, dict[str, str], list[str]]:
    """Bewertet eine Kopfzeilen-Variante.

    Liefert (Zahl erkannter Spaltenrollen, verschiedene Namen, Mapping,
    Überschriften).

    Massgeblich ist die Zahl der erkannten Rollen — bei der richtigen
    Kopfzeile trifft die Mustererkennung Name, Vorhaben, Kosten, Datum und
    Ort; eine verschobene Zeile trifft fast nichts. Die Zahl gefüllter oder
    verschiedener Namen taugt dafür nicht: Da nur die ersten Zeilen gelesen
    werden, verschiebt eine tiefere Kopfzeile bloss das Lesefenster und
    gewinnt zufällig.
    """
    headers = [str(c) for c in df.columns]
    mapping = _detect_canonical_columns(headers, None)
    if "name" not in mapping:
        gefunden = suche_spalte(headers, "name")
        if not gefunden:
            return 0, 0, mapping, headers
        mapping = dict(mapping)
        mapping["name"] = gefunden
    spalte = mapping["name"]
    if spalte not in df.columns:
        return 0, 0, mapping, headers
    verschieden = {
        str(v).strip() for v in df[spalte]
        if v is not None and not (isinstance(v, float) and pd.isna(v))
        and str(v).strip() not in ("", "nan", "None")
    }
    # Eine Kopfzeile, unter der nur ein einziger Name steht, ist keine.
    if len(verschieden) < 2:
        return 0, len(verschieden), mapping, headers
    return len(mapping), len(verschieden), mapping, headers


def kalibriere(content: bytes, ist_csv: bool) -> dict | None:
    """Probiert Blätter und Kopfzeilen durch und liefert die beste Variante.

    Gewinner ist die Variante mit den meisten erkannten Spaltenrollen; bei
    Gleichstand die mit der kleinsten Kopfzeile, denn der Vorspann steht
    immer oben.
    """
    beste: dict | None = None

    def merke(blatt, kopf, rollen, namen, mapping, headers):
        nonlocal beste
        if not rollen:
            return
        if beste is None or rollen > beste["rollen"]:
            beste = {"blatt": blatt, "kopfzeile": kopf, "rollen": rollen,
                     "namen": namen, "mapping": mapping, "headers": headers}

    if ist_csv:
        for kopf in range(0, 6):
            try:
                df = pd.read_csv(io.BytesIO(content), header=kopf, sep=None,
                                 engine="python", nrows=400)
            except Exception:
                continue
            merke(None, kopf, *bewerte(df))
        return beste

    try:
        xl = pd.ExcelFile(io.BytesIO(content), engine="openpyxl")
    except Exception as exc:
        print(f"    Excel nicht lesbar: {exc}")
        return None

    for blatt in xl.sheet_names:
        for kopf in range(0, MAX_HEADER_ROW + 1):
            try:
                df = pd.read_excel(xl, sheet_name=blatt, header=kopf, nrows=400)
            except Exception:
                continue
            if df.empty or len(df.columns) < 3:
                continue
            merke(blatt, kopf, *bewerte(df))

    # Gewählte Variante über die GANZE Datei nachzählen — die Stichprobe der
    # ersten 400 Zeilen sagt nichts über den Gesamtumfang.
    if beste:
        try:
            df = pd.read_excel(xl, sheet_name=beste["blatt"], header=beste["kopfzeile"])
            spalte = beste["mapping"]["name"]
            beste["zeilen_gesamt"] = int(
                df[spalte].astype(str).str.strip().replace(
                    {"": None, "nan": None, "None": None}).notna().sum()
            )
        except Exception:
            beste["zeilen_gesamt"] = None
    return beste


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="Ergebnis speichern")
    ap.add_argument("--dry-run", action="store_true", help="nur anzeigen (Default)")
    ap.add_argument("--nur", nargs="*", default=None, help="nur diese source_keys")
    args = ap.parse_args()

    registry = lade_registry()
    db = SessionLocal()
    try:
        quellen = list(
            db.query(BeneficiarySourceConfig).order_by(BeneficiarySourceConfig.source_key)
        )
    finally:
        db.close()

    ergebnisse: dict[str, dict] = {}
    for cfg in quellen:
        key = cfg.source_key
        if args.nur and key not in args.nur:
            continue
        eintrag = registry.get(split_key(key))
        url = (eintrag or {}).get("url")
        if not url:
            continue

        print(f"\n{key}")
        try:
            with httpx.Client(timeout=90, follow_redirects=True,
                              headers=HTTP_HEADERS) as client:
                content = client.get(url).content
        except Exception as exc:
            print(f"    Download fehlgeschlagen: {str(exc)[:70]}")
            continue

        ist_xlsx = content[:4] == b"PK\x03\x04"
        if not ist_xlsx and b"<html" in content[:2000].lower():
            print("    Server liefert eine HTML-Seite statt einer Datei")
            continue

        beste = kalibriere(content, ist_csv=not ist_xlsx)
        if not beste:
            print("    Keine Kombination mit erkennbarer Namensspalte gefunden")
            continue

        # Bewusst nur die Namensspalte explizit setzen, und auch nur dann, wenn
        # die Mustererkennung sie nicht selbst findet. Alle übrigen Rollen
        # bleiben ihr überlassen: eine geratene Kosten- oder Datumsspalte wäre
        # stiller Datenschaden, eine fehlende bloß eine sichtbare Lücke.
        auto = _detect_canonical_columns(beste["headers"], None)
        explizit = {}
        if auto.get("name") != beste["mapping"].get("name"):
            explizit["name"] = beste["mapping"]["name"]

        print(f"    Blatt={beste['blatt']!r} Kopfzeile={beste['kopfzeile']} "
              f"Rollen={beste['rollen']} Zeilen={beste.get('zeilen_gesamt')}")
        if explizit:
            for a, h in sorted(explizit.items()):
                print(f"      {a:<14} → {str(h)[:58]!r}")
        # Schutz vor stillem Datenverlust: Wenn die gewählte Kopfzeile deutlich
        # weniger Zeilen ergibt als bereits im Bestand liegen, ist sie mit hoher
        # Wahrscheinlichkeit falsch. Snapshot-Import würde den Bestand dann
        # durch ein Rumpf-Ergebnis ersetzen.
        zeilen = beste.get("zeilen_gesamt")
        bestand = cfg.record_count or 0
        if zeilen is not None and bestand and zeilen < bestand * 0.5:
            print(f"    ÜBERSPRUNGEN — nur {zeilen} Zeilen gegenüber {bestand} "
                  f"im Bestand. Kopfzeile vermutlich falsch.")
            continue

        ergebnisse[key] = {
            "blatt": beste["blatt"], "kopfzeile": beste["kopfzeile"],
            "mapping": explizit, "zeilen": beste.get("zeilen_gesamt"),
            "typ": "xlsx_url" if ist_xlsx else "csv_url", "url": url,
        }

    print(f"\n{'='*70}\nKalibriert: {len(ergebnisse)} Quellen")
    if not args.apply:
        print("Probelauf — nichts gespeichert. Mit --apply ausführen.")
        return 0

    db = SessionLocal()
    try:
        for key, r in ergebnisse.items():
            cfg = (
                db.query(BeneficiarySourceConfig)
                .filter(BeneficiarySourceConfig.source_key == key)
                .first()
            )
            if not cfg:
                continue
            cfg.source_url = r["url"]
            cfg.source_type = r["typ"]
            cfg.update_frequency_days = 30
            cfg.header_row = r["kopfzeile"]
            cfg.sheet_name = r["blatt"]
            cfg.field_mapping = r["mapping"] or None
        db.commit()
    finally:
        db.close()
    print(f"{len(ergebnisse)} Quellen gespeichert und freigeschaltet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
