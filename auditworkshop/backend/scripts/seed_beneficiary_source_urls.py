#!/usr/bin/env python3
"""
Verknuepft die Begünstigten-Quellenkonfiguration mit den Download-URLs aus
``data/transparenzlisten_urls.json``.

Hintergrund: die 35 Eintraege in ``workshop_beneficiary_sources_config``
sind als Nebenprodukt manueller Uploads entstanden und standen deshalb auf
``source_type='manual_upload'`` ohne ``source_url``. Der naechtliche
Auto-Harvest ueberspringt solche Quellen (siehe ``_is_source_auto_capable``
in ``services/scheduler.py``) — die Transparenzlisten wurden dadurch
monatelang nicht mehr aktualisiert.

Dieses Skript setzt fuer jede zuordenbare Quelle ``source_type``,
``source_url`` und ``update_frequency_days``. Es ist idempotent und
schreibt ausschliesslich diese drei Spalten — Datensaetze, Mappings und
Qualitaetsangaben bleiben unangetastet.

Aufruf:
    python3 scripts/seed_beneficiary_source_urls.py --dry-run
    python3 scripts/seed_beneficiary_source_urls.py --apply

Der Dateityp wird aus der Dateiendung abgeleitet; mit ``--type-override
<source_key>=<csv_url|xlsx_url>`` laesst er sich pro Quelle korrigieren
(noetig fuer Quellen, deren URL keine sprechende Endung hat).
"""
from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import SessionLocal  # noqa: E402
from models.beneficiary_sources_config import BeneficiarySourceConfig  # noqa: E402

REGISTRY_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "transparenzlisten_urls.json"
)

# Fonds-Kuerzel, die in einem source_key vorkommen koennen. Der Teil davor
# ist das Bundesland: "mecklenburg-vorpommern_efre_2021_2027" -> "efre".
FONDS_TOKENS = ("efre", "esf", "jtf", "amif", "isf")

DEFAULT_FREQUENCY_DAYS = 30


def normalize(value: str | None) -> str:
    """Bundesland-Namen vergleichbar machen.

    Die Registry schreibt ASCII-transkribiert ("Baden-Wuerttemberg"), die
    Datenbank echte Umlaute ("baden-württemberg"). Beide Formen werden auf
    denselben Schluessel reduziert.
    """
    s = (value or "").lower().strip()
    s = s.replace("ä", "a").replace("ö", "o").replace("ü", "u").replace("ß", "ss")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.replace("ue", "u").replace("oe", "o").replace("ae", "a")
    for ch in " -_.":
        s = s.replace(ch, "")
    return s


def split_source_key(source_key: str) -> tuple[str, str]:
    """``sachsen-anhalt_esf_2021_2027`` -> ``("sachsenanhalt", "esf")``."""
    parts = source_key.split("_")
    for i, part in enumerate(parts):
        if part in FONDS_TOKENS:
            return normalize("_".join(parts[:i])), part
    return normalize(source_key), ""


def guess_source_type(url: str) -> str:
    """Dateityp aus der URL ableiten — XLSX ist der Regelfall."""
    path = url.split("?", 1)[0].lower()
    if path.endswith(".csv"):
        return "csv_url"
    return "xlsx_url"


def build_plan(overrides: dict[str, str]) -> tuple[list[dict], list[str]]:
    """Ordnet DB-Quellen den Registry-Eintraegen zu.

    Liefert (Aenderungsplan, nicht zuordenbare source_keys).
    """
    registry = load_registry()
    by_land_fonds: dict[tuple[str, str], dict] = {}
    for entry in registry:
        key = (normalize(entry.get("bundesland")), (entry.get("fonds") or "").lower())
        by_land_fonds.setdefault(key, entry)

    plan: list[dict] = []
    unmatched: list[str] = []
    db = SessionLocal()
    try:
        for cfg in db.query(BeneficiarySourceConfig).order_by(
            BeneficiarySourceConfig.source_key.asc()
        ):
            entry = by_land_fonds.get(split_source_key(cfg.source_key))
            url = (entry or {}).get("url")
            if not url:
                unmatched.append(cfg.source_key)
                continue
            source_type = overrides.get(cfg.source_key) or guess_source_type(url)
            plan.append({
                "source_key": cfg.source_key,
                "url": url,
                "source_type": source_type,
                "registry_status": entry.get("status"),
                "alt_type": cfg.source_type,
                "alt_url": cfg.source_url,
                "unveraendert": (
                    cfg.source_url == url
                    and cfg.source_type == source_type
                    and cfg.update_frequency_days == DEFAULT_FREQUENCY_DAYS
                ),
            })
    finally:
        db.close()
    return plan, unmatched


def setze_portalseiten() -> int:
    """Schreibt die Portalseite je Quelle in ``source_landing_page``.

    Der naechtliche Harvest braucht sie, um einen gestorbenen Direktlink
    selbst zu erneuern. Sie wird auch fuer manuell gepflegte Quellen
    gesetzt — falls die spaeter automatisiert werden.
    """
    registry = load_registry()
    by_land_fonds: dict[tuple[str, str], dict] = {}
    for e in registry:
        by_land_fonds.setdefault(
            (normalize(e.get("bundesland")), (e.get("fonds") or "").lower()), e,
        )
    geaendert = 0
    db = SessionLocal()
    try:
        for cfg in db.query(BeneficiarySourceConfig).all():
            eintrag = by_land_fonds.get(split_source_key(cfg.source_key))
            portal = (eintrag or {}).get("portal")
            if portal and cfg.source_landing_page != portal:
                cfg.source_landing_page = portal
                geaendert += 1
        db.commit()
    finally:
        db.close()
    return geaendert


def load_registry() -> list[dict]:
    if not REGISTRY_PATH.exists():
        sys.exit(f"FEHLER: URL-Registry nicht gefunden: {REGISTRY_PATH}")
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8")).get("sources", [])


def apply_plan(plan: list[dict]) -> int:
    geaendert = 0
    db = SessionLocal()
    try:
        for item in plan:
            if item["unveraendert"]:
                continue
            cfg = (
                db.query(BeneficiarySourceConfig)
                .filter(BeneficiarySourceConfig.source_key == item["source_key"])
                .first()
            )
            if not cfg:
                continue
            cfg.source_url = item["url"]
            cfg.source_type = item["source_type"]
            cfg.update_frequency_days = DEFAULT_FREQUENCY_DAYS
            geaendert += 1
        db.commit()
    finally:
        db.close()
    return geaendert


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="Änderungen schreiben")
    ap.add_argument("--dry-run", action="store_true", help="nur anzeigen (Default)")
    ap.add_argument(
        "--nur-portale", action="store_true",
        help="nur die Portalseiten (source_landing_page) setzen, sonst nichts",
    )
    ap.add_argument(
        "--type-override", action="append", default=[], metavar="KEY=TYP",
        help="Dateityp einer Quelle erzwingen, z. B. land_esf_2021_2027=csv_url",
    )
    args = ap.parse_args()

    overrides: dict[str, str] = {}
    for raw in args.type_override:
        if "=" not in raw:
            sys.exit(f"FEHLER: --type-override erwartet KEY=TYP, bekam: {raw}")
        key, typ = raw.split("=", 1)
        if typ not in ("csv_url", "xlsx_url"):
            sys.exit(f"FEHLER: unbekannter Typ '{typ}' (erlaubt: csv_url, xlsx_url)")
        overrides[key.strip()] = typ.strip()

    if args.nur_portale:
        n = setze_portalseiten()
        print(f"{n} Portalseiten in der Konfiguration gesetzt.")
        return 0

    plan, unmatched = build_plan(overrides)
    offen = [p for p in plan if not p["unveraendert"]]

    print(f"Zuordenbar: {len(plan)} Quellen · davon zu ändern: {len(offen)}")
    for item in sorted(plan, key=lambda p: p["source_key"]):
        marker = "  " if item["unveraendert"] else "→ "
        print(
            f"{marker}{item['source_key']:<40} {item['source_type']:<9} "
            f"[Registry-Status: {item['registry_status']}]"
        )
    if unmatched:
        print(f"\nOhne Registry-URL ({len(unmatched)}) — bleiben manual_upload:")
        for key in unmatched:
            print(f"  {key}")

    if not args.apply:
        print("\nProbelauf — nichts geschrieben. Mit --apply ausführen.")
        return 0

    geaendert = apply_plan(plan)
    print(f"\n{geaendert} Quellen aktualisiert.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
