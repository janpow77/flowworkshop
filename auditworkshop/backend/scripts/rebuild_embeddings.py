#!/usr/bin/env python3
"""
flowworkshop · scripts/rebuild_embeddings.py

Layer A — CLI-Wrapper fuer ``services.entity_embeddings.rebuild_module_embeddings``.

Aufruf im Container (Initial-Build, Hintergrund-Lauf):

    docker exec -d auditworkshop-backend \\
        python scripts/rebuild_embeddings.py --module all --batch-size 50

    # Schnelle Validierung vor dem grossen Build:
    python scripts/rebuild_embeddings.py --module state_aid --limit 100 --dry

    # Nur fehlende Embeddings nachholen (Default):
    python scripts/rebuild_embeddings.py --module beneficiary --skip-existing

    # Alle Embeddings neu berechnen (Modell-Wechsel):
    python scripts/rebuild_embeddings.py --module all --force-update

Liefert ein JSON-Ergebnis mit pro Modul:
  - processed
  - inserted
  - updated
  - skipped
  - failed

Idempotent mit ``--skip-existing`` (Default true): ein zweiter Lauf
ueberspringt alle bereits eingebetteten Records.
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
from services.entity_embeddings import (  # noqa: E402
    VALID_MODULES,
    rebuild_module_embeddings,
)


log = logging.getLogger("rebuild_embeddings")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Rebuild des Embedding-Index (workshop_entity_embeddings) "
            "ueber bge-m3-Gateway. Idempotent mit --skip-existing."
        ),
    )
    p.add_argument(
        "--module",
        choices=sorted(VALID_MODULES) + ["all"],
        default="all",
        help="Welches Modul rebuildet werden soll (Default: all).",
    )
    p.add_argument(
        "--batch-size", type=int, default=50,
        help="Embedding-Batch-Groesse pro Gateway-Call (Default: 50).",
    )
    p.add_argument(
        "--limit", type=int, default=None,
        help="Optional: max. Records pro Modul (fuer schnelle Tests).",
    )
    p.add_argument(
        "--dry", action="store_true",
        help="Trockenlauf — kein Gateway-Call, kein DB-Schreiben.",
    )
    skip_group = p.add_mutually_exclusive_group()
    skip_group.add_argument(
        "--skip-existing", dest="skip_existing", action="store_true",
        default=True,
        help="(Default) Bestehende Embeddings werden nicht neu gerechnet.",
    )
    skip_group.add_argument(
        "--force-update", dest="skip_existing", action="store_false",
        help="Alle Embeddings neu berechnen (Modell-Wechsel).",
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

    if args.module == "all":
        targets = sorted(VALID_MODULES)
    else:
        targets = [args.module]

    summary: dict = {
        "module": args.module,
        "batch_size": args.batch_size,
        "skip_existing": args.skip_existing,
        "dry": args.dry,
        "limit": args.limit,
        "results": {},
    }

    db = SessionLocal()
    try:
        for mod in targets:
            log.info(
                "Rebuild module=%s (batch_size=%d, skip_existing=%s, "
                "dry=%s, limit=%s)",
                mod, args.batch_size, args.skip_existing, args.dry,
                args.limit,
            )
            try:
                summary["results"][mod] = rebuild_module_embeddings(
                    db, mod,
                    batch_size=int(args.batch_size),
                    skip_existing=bool(args.skip_existing),
                    dry=bool(args.dry),
                    limit=args.limit,
                )
            except Exception as exc:  # noqa: BLE001
                log.exception("Rebuild fehlgeschlagen fuer module=%s", mod)
                summary["results"][mod] = {
                    "status": "failed",
                    "error": str(exc)[:500],
                }
    finally:
        db.close()

    totals = {
        "processed": 0,
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "failed": 0,
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
