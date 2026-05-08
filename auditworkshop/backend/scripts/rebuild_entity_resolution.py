#!/usr/bin/env python3
"""
flowworkshop · scripts/rebuild_entity_resolution.py

Phase 6d — CLI-Wrapper fuer ``services.entity_resolution.rebuild_entities_*``.

Aufruf im Container:

    # Standard: alle 3 Module, schreibt Entities + Matches
    python scripts/rebuild_entity_resolution.py --module all

    # Nur State-Aid (haeufigster Fall — 170k+ Awards)
    python scripts/rebuild_entity_resolution.py --module state_aid

    # Trockenlauf (zaehlt nur, schreibt nichts):
    python scripts/rebuild_entity_resolution.py --module all --dry

    # Nur ein Subset zum schnellen Pruefen:
    python scripts/rebuild_entity_resolution.py --module state_aid --limit 5000

Liefert ein JSON-Ergebnis mit pro Modul:
  - records_seen
  - matches_created
  - entities_created
  - records_skipped_existing  (Match war schon vorhanden)
  - low_confidence_skipped    (Score < 75)
  - records_failed            (kein Name oder andere Exception)

Idempotent: ein zweiter Lauf mit denselben Daten muss
``matches_created == 0`` ergeben.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Backend-Verzeichnis in den Pfad legen
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import SessionLocal  # noqa: E402
from services.entity_resolution import (  # noqa: E402
    rebuild_entities_from_beneficiaries,
    rebuild_entities_from_sanctions,
    rebuild_entities_from_state_aid,
)


log = logging.getLogger("rebuild_entity_resolution")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Rebuild der Entity-Resolution-Tabelle (workshop_company_entities + "
            "workshop_entity_matches). Idempotent."
        ),
    )
    p.add_argument(
        "--module",
        choices=["state_aid", "beneficiary", "sanctions", "all"],
        default="all",
        help="Welches Modul rebuildet werden soll (Default: all).",
    )
    p.add_argument(
        "--dry", action="store_true",
        help="Trockenlauf — zaehlt, aber schreibt keine Matches/Entities.",
    )
    p.add_argument(
        "--limit", type=int, default=None,
        help="Optional: max. Records pro Modul (fuer schnelle Tests).",
    )
    p.add_argument(
        "--batch", type=int, default=1000,
        help="DB-Batch-Groesse (Default: 1000).",
    )
    p.add_argument(
        "--verbose", action="store_true",
        help="DEBUG-Logging.",
    )
    return p


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s  %(name)s  %(message)s",
    )

    summary: dict = {
        "module": args.module,
        "dry": args.dry,
        "limit": args.limit,
        "batch": args.batch,
        "results": {},
    }

    db = SessionLocal()
    try:
        if args.module in ("state_aid", "all"):
            log.info("Rebuild state_aid (dry=%s, limit=%s)", args.dry, args.limit)
            try:
                summary["results"]["state_aid"] = rebuild_entities_from_state_aid(
                    db, batch=int(args.batch), dry=args.dry, limit=args.limit,
                )
            except Exception as exc:  # noqa: BLE001
                log.exception("state_aid Rebuild fehlgeschlagen")
                summary["results"]["state_aid"] = {
                    "status": "failed",
                    "error": str(exc)[:500],
                }

        if args.module in ("beneficiary", "all"):
            log.info(
                "Rebuild beneficiary (dry=%s, limit=%s)",
                args.dry, args.limit,
            )
            try:
                summary["results"]["beneficiary"] = (
                    rebuild_entities_from_beneficiaries(
                        db, batch=int(args.batch),
                        dry=args.dry, limit=args.limit,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                log.exception("beneficiary Rebuild fehlgeschlagen")
                summary["results"]["beneficiary"] = {
                    "status": "failed",
                    "error": str(exc)[:500],
                }

        if args.module in ("sanctions", "all"):
            log.info(
                "Rebuild sanctions (dry=%s, limit=%s)",
                args.dry, args.limit,
            )
            try:
                summary["results"]["sanctions"] = rebuild_entities_from_sanctions(
                    db, batch=int(args.batch), dry=args.dry, limit=args.limit,
                )
            except Exception as exc:  # noqa: BLE001
                log.exception("sanctions Rebuild fehlgeschlagen")
                summary["results"]["sanctions"] = {
                    "status": "failed",
                    "error": str(exc)[:500],
                }
    finally:
        db.close()

    # Totals
    totals = {
        "records_seen": 0,
        "records_skipped_existing": 0,
        "records_failed": 0,
        "matches_created": 0,
        "entities_created": 0,
        "low_confidence_skipped": 0,
    }
    for _key, mod_result in summary["results"].items():
        if isinstance(mod_result, dict):
            for k in totals:
                totals[k] += int(mod_result.get(k) or 0)
    summary["totals"] = totals

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    failed_modules = [
        k for k, v in summary["results"].items()
        if isinstance(v, dict) and v.get("status") == "failed"
    ]
    if failed_modules:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
