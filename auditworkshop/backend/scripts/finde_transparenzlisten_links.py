#!/usr/bin/env python3
"""
Pflegt die Direktlinks in ``data/transparenzlisten_urls.json``.

Die eigentliche Suchlogik liegt in ``services/transparenzlisten_links.py`` —
dasselbe Modul nutzt der nächtliche Harvest, um einen gestorbenen Link
selbst zu erneuern. Dieses Skript ist die Pflege-Variante für die Registry.

Aufruf:
    python3 scripts/finde_transparenzlisten_links.py
    python3 scripts/finde_transparenzlisten_links.py --nur "Bremen ESF"
    python3 scripts/finde_transparenzlisten_links.py --schreiben
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from services.transparenzlisten_links import (  # noqa: E402
    HTTP_HEADERS, MINDEST_PUNKTE, sammle_kandidaten,
)

REGISTRY = Path(__file__).resolve().parent.parent / "data" / "transparenzlisten_urls.json"


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
    with httpx.Client(timeout=90, follow_redirects=True, headers=HTTP_HEADERS,
                      verify=False) as client:
        for idx, e in enumerate(quellen):
            bezeichnung = f"{e.get('bundesland')} {e.get('fonds')}"
            if args.nur and bezeichnung not in args.nur:
                continue
            if not args.alle and (e.get("status") or "") == "ok":
                continue
            print(f"\n{bezeichnung}")
            if not e.get("portal"):
                print("    keine Portalseite hinterlegt — Recherche nötig")
                continue

            gefunden = sammle_kandidaten(e["portal"], client, e.get("fonds"))
            if not gefunden:
                print("    keine Tabellen-Verweise auf der Portalseite")
                continue
            for k in gefunden:
                marke = "✓" if k["ok"] else "·"
                print(f"    {marke} [{k['punkte']:>3}] {k['art']:<22} {k['url'][:86]}")
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
