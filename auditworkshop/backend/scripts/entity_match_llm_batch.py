#!/usr/bin/env python3
"""
flowworkshop · scripts/entity_match_llm_batch.py

CLI-Wrapper fuer den naechtlichen Layer-C-LLM-Verifikations-Batch.

Beispiele:

    # Nur Eligible-Records anzeigen, kein DB-Write, kein LLM-Call:
    python scripts/entity_match_llm_batch.py --dry --max 5

    # Vollbatch mit Default 500 Matches der letzten 48 h:
    python scripts/entity_match_llm_batch.py

    # Engerer Score-Range (z.B. nur sehr ambivalente Matches):
    python scripts/entity_match_llm_batch.py --score-min 80 --score-max 85

    # Erweitertes Lookback-Window:
    python scripts/entity_match_llm_batch.py --recent-hours 168 --max 1000

Liefert ein JSON-Result auf stdout mit Status, Confirmed/Rejected/Unknown-
Counters und der Run-ID (zum Cross-Lookup im Admin-Endpoint).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Pfad zum Backend-Verzeichnis
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import SessionLocal
from services.entity_match_llm_verifier import (
    BatchVerifyParams,
    run_batch_verification,
    select_eligible_matches,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Layer C — Naechtlicher LLM-Verifikations-Batch fuer EntityMatches "
            "mit niedriger Confidence (75-89)."
        ),
    )
    p.add_argument(
        "--max", dest="max_matches", type=int, default=500,
        help="Maximum Matches pro Lauf (default 500).",
    )
    p.add_argument(
        "--score-min", type=float, default=75.0,
        help="Untere Confidence-Schwelle (default 75).",
    )
    p.add_argument(
        "--score-max", type=float, default=89.0,
        help="Obere Confidence-Schwelle (default 89).",
    )
    p.add_argument(
        "--recent-hours", type=int, default=48,
        help="Nur Matches der letzten N Stunden (default 48).",
    )
    p.add_argument(
        "--per-call-timeout", type=float, default=30.0,
        help="Per-Call-Timeout in Sekunden (default 30).",
    )
    p.add_argument(
        "--overall-timeout", type=float, default=7200.0,
        help="Globaler Timeout in Sekunden (default 7200 = 2 h).",
    )
    p.add_argument(
        "--dry", action="store_true",
        help=(
            "Trockenlauf: zeige nur Eligible-Records, kein LLM-Call, "
            "keine DB-Writes."
        ),
    )
    p.add_argument(
        "--triggered-by", default="cli",
        help="Trigger-Label fuer den Audit-Run (default 'cli').",
    )
    p.add_argument("--verbose", action="store_true", help="DEBUG-Logging.")
    return p


def _dry_preview(params: BatchVerifyParams, limit_print: int = 10) -> dict:
    """Im Dry-Modus listen wir nur die Eligible-Records auf — ohne LLM-Call."""
    db = SessionLocal()
    try:
        matches = select_eligible_matches(db, params)
        preview = []
        for m in matches[:limit_print]:
            preview.append({
                "match_id": m.id,
                "entity_id": m.entity_id,
                "source_module": m.source_module,
                "source_record_id": m.source_record_id,
                "match_method": m.match_method,
                "match_confidence": float(m.match_confidence or 0.0),
                "created_at": (
                    m.created_at.isoformat() if m.created_at else None
                ),
                "rejected": bool(m.rejected),
                "confirmed_by_user_id": m.confirmed_by_user_id,
            })
        return {
            "status": "dry",
            "total_eligible": len(matches),
            "preview_limit": limit_print,
            "preview": preview,
            "parameters": params.to_dict(),
        }
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s  %(name)s  %(message)s",
    )
    log = logging.getLogger("entity_match_llm_batch")

    params = BatchVerifyParams(
        max_matches=int(args.max_matches),
        score_min=float(args.score_min),
        score_max=float(args.score_max),
        only_recent_hours=int(args.recent_hours),
        only_unverified=True,
        per_call_timeout_s=float(args.per_call_timeout),
        overall_timeout_s=float(args.overall_timeout),
        dry=bool(args.dry),
    )

    if args.dry:
        log.info(
            "Dry-Run: zeige bis zu %d Eligible-Matches (kein LLM, kein DB-Write).",
            params.max_matches,
        )
        payload = _dry_preview(params, limit_print=min(args.max_matches, 10))
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    log.info(
        "Entity-Match-LLM-Batch CLI: max=%d range=%.0f..%.0f recent_hours=%d",
        params.max_matches, params.score_min, params.score_max,
        params.only_recent_hours,
    )
    db = SessionLocal()
    try:
        result = run_batch_verification(
            db, params, triggered_by=str(args.triggered_by),
        )
    finally:
        db.close()

    payload = result.to_dict()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if result.status in ("ok", "partial") else 2


if __name__ == "__main__":
    sys.exit(main())
