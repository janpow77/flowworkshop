#!/usr/bin/env python3
"""
flowworkshop · scripts/backfill_sanctions_entries.py

Phase 6c — Erst-Befuellung der Tabelle ``workshop_sanctions_entries`` aus
den bereits vorhandenen 5 OpenSanctions-CSVs:

    /app/data/sanctions/eu_fsf_targets.csv
    /app/data/sanctions/un_sc_targets.csv
    /app/data/sanctions/us_ofac_sdn_targets.csv
    /app/data/sanctions/gb_hmt_sanctions_targets.csv
    /app/data/sanctions/ch_seco_targets.csv

Aufruf im Container:

    # Standard: alle 5 Sources, idempotent (ON CONFLICT DO NOTHING):
    python scripts/backfill_sanctions_entries.py

    # Trockenlauf — zaehlt nur, schreibt nichts:
    python scripts/backfill_sanctions_entries.py --dry

    # Nur eine einzelne Source nachladen:
    python scripts/backfill_sanctions_entries.py --source-key eu_fsf

Liefert ein JSON-Ergebnis mit pro Source:
  - records_inserted  (neu eingefuegte Zeilen)
  - records_skipped   (bereits vorhanden, ueber DO NOTHING ausgelassen)
  - records_failed    (Zeilen ohne id/name)

Idempotent: ein zweiter Lauf muss ``records_inserted == 0`` ergeben.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
from pathlib import Path

# Pfad zum Backend-Verzeichnis (analog zu harvest_state_aid.py)
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402

from database import SessionLocal  # noqa: E402
from models.sanctions_entries import SanctionsEntry  # noqa: E402
from services.sanctions_service import (  # noqa: E402
    DEFAULT_SANCTIONS_SOURCES,
    SanctionsSource,
    normalize_name,
)


log = logging.getLogger("backfill_sanctions_entries")


# ── Konstanten ────────────────────────────────────────────────────────────────


CHUNK_SIZE = 1000


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Backfill der Tabelle workshop_sanctions_entries aus den bereits "
            "vorhandenen OpenSanctions-CSVs (idempotent ueber ON CONFLICT DO NOTHING)."
        ),
    )
    p.add_argument(
        "--dry", action="store_true",
        help=(
            "Trockenlauf — zaehlt CSV-Zeilen pro Source, schreibt aber nichts "
            "in die DB."
        ),
    )
    p.add_argument(
        "--source-key", default=None,
        help=(
            "Wenn gesetzt: nur diese Source backfilllen (z.B. 'eu_fsf'). "
            "Default: alle in DEFAULT_SANCTIONS_SOURCES."
        ),
    )
    p.add_argument(
        "--verbose", action="store_true",
        help="DEBUG-Logging.",
    )
    return p


# ── Pure Helpers ──────────────────────────────────────────────────────────────


def _row_to_payload(source_key: str, row: dict) -> dict | None:
    """Wandelt eine OpenSanctions-CSV-Zeile in einen DB-Insert-Wertesatz um.

    Liefert None, wenn Pflichtfelder (``id``, ``name``) fehlen — solche
    Zeilen werden im Aufrufer als ``records_failed`` gezaehlt.
    """
    entry_id = (row.get("id") or "").strip()
    name = row.get("name") or ""
    if not entry_id or not name:
        return None
    aliases_raw = row.get("aliases") or ""
    aliases_list = [a.strip() for a in aliases_raw.split(";") if a.strip()]
    return {
        "source_key": source_key,
        "entry_id": entry_id,
        "schema": row.get("schema") or "",
        "name": name,
        "name_normalized": normalize_name(name),
        "aliases": aliases_list or None,
        "birth_date": (row.get("birth_date") or "") or None,
        "countries": (row.get("countries") or "") or None,
        "addresses": (row.get("addresses") or "") or None,
        "identifiers": (row.get("identifiers") or "") or None,
        "sanctions_program": (row.get("sanctions") or "") or None,
        "program_ids": (row.get("program_ids") or "") or None,
        "first_seen": (row.get("first_seen") or "") or None,
        "last_seen": (row.get("last_seen") or "") or None,
        "raw_payload": dict(row),
        "refresh_run_id": None,
    }


# ── Main-Backfill pro Source ──────────────────────────────────────────────────


def backfill_source(
    source: SanctionsSource,
    *,
    dry: bool = False,
) -> dict:
    """Liest die CSV und schiebt die Zeilen idempotent in die DB.

    Bei ``dry=True`` wird nichts geschrieben — die Funktion zaehlt nur.
    """
    csv_path = source.csv_path
    if not os.path.exists(csv_path):
        return {
            "source_key": source.key,
            "status": "skipped",
            "reason": f"CSV fehlt: {csv_path}",
            "records_seen": 0,
            "records_inserted": 0,
            "records_skipped": 0,
            "records_failed": 0,
            "csv_path": csv_path,
        }

    seen = 0
    inserted = 0
    skipped = 0
    failed = 0
    batch: list[dict] = []

    db = None if dry else SessionLocal()

    def _flush() -> tuple[int, int]:
        """Liefert (inserted, skipped) — skipped = Zeilen, die per
        ON CONFLICT DO NOTHING ausgelassen wurden.
        """
        if not batch or db is None:
            return 0, 0
        attempted = len(batch)
        stmt = pg_insert(SanctionsEntry).values(batch).on_conflict_do_nothing(
            index_elements=["source_key", "entry_id"],
        )
        result = db.execute(stmt)
        ins = int(result.rowcount or 0)
        sk = max(0, attempted - ins)
        db.commit()
        return ins, sk

    try:
        with open(csv_path, encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                seen += 1
                payload = _row_to_payload(source.key, row)
                if payload is None:
                    failed += 1
                    continue
                if dry:
                    inserted += 1  # would insert, no DB call
                    continue
                batch.append(payload)
                if len(batch) >= CHUNK_SIZE:
                    ins, sk = _flush()
                    inserted += ins
                    skipped += sk
                    batch.clear()
        if batch and not dry:
            ins, sk = _flush()
            inserted += ins
            skipped += sk
            batch.clear()
    finally:
        if db is not None:
            db.close()

    return {
        "source_key": source.key,
        "status": "ok",
        "records_seen": seen,
        "records_inserted": inserted,
        "records_skipped": skipped,
        "records_failed": failed,
        "csv_path": csv_path,
        "dry": dry,
    }


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s  %(name)s  %(message)s",
    )

    # Source-Liste filtern
    sources: list[SanctionsSource] = list(DEFAULT_SANCTIONS_SOURCES)
    if args.source_key:
        sources = [s for s in sources if s.key == args.source_key]
        if not sources:
            log.error(
                "Unbekannter --source-key '%s'. Verfuegbar: %s",
                args.source_key,
                ", ".join(s.key for s in DEFAULT_SANCTIONS_SOURCES),
            )
            print(json.dumps({
                "status": "error",
                "error": "unknown source_key",
                "available": [s.key for s in DEFAULT_SANCTIONS_SOURCES],
            }, indent=2))
            return 2

    summary: dict = {
        "status": "ok",
        "dry": args.dry,
        "sources_total": len(sources),
        "sources": [],
        "totals": {
            "records_seen": 0,
            "records_inserted": 0,
            "records_skipped": 0,
            "records_failed": 0,
        },
    }
    for source in sources:
        log.info(
            "Backfill source=%s csv=%s dry=%s",
            source.key, source.csv_path, args.dry,
        )
        try:
            result = backfill_source(source, dry=args.dry)
        except Exception as exc:  # noqa: BLE001
            log.exception("Backfill source=%s fehlgeschlagen", source.key)
            result = {
                "source_key": source.key,
                "status": "failed",
                "error": str(exc)[:500],
                "records_seen": 0,
                "records_inserted": 0,
                "records_skipped": 0,
                "records_failed": 0,
            }
        summary["sources"].append(result)
        for k in ("records_seen", "records_inserted", "records_skipped", "records_failed"):
            summary["totals"][k] += int(result.get(k) or 0)

    failed = [s for s in summary["sources"] if s.get("status") == "failed"]
    if failed and len(failed) == len(summary["sources"]):
        summary["status"] = "failed"
    elif failed:
        summary["status"] = "partial"

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["status"] in ("ok",) else 1


if __name__ == "__main__":
    sys.exit(main())
