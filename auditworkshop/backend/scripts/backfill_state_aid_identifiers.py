#!/usr/bin/env python3
"""
flowworkshop · scripts/backfill_state_aid_identifiers.py

Liest bestehende TAM-Award-Detailseiten nach und korrigiert die nationale
Kennung in workshop_state_aid_awards.

Aufruf:
    docker exec auditworkshop-backend python scripts/backfill_state_aid_identifiers.py --query "Franz Hof"
    docker exec auditworkshop-backend python scripts/backfill_state_aid_identifiers.py --record-id TM-12511862
    docker exec auditworkshop-backend python scripts/backfill_state_aid_identifiers.py --dry --limit 50
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from database import SessionLocal
from models.state_aid import StateAidAward
from services.state_aid_harvester import (
    DEFAULT_USER_AGENT,
    HARVEST_TIMEOUT,
    _detail_url_with_lang,
    parse_award_detail,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
log = logging.getLogger("backfill_state_aid_identifiers")

IDENTIFIER_TYPE_LABELS = [
    "USt-IdNr",
    "St-Nr",
    "IdNr",
    "UID-Nummer",
    "Handelsregisternummer",
    "Firmenbuchnummer",
    "Vereinsregisternummer",
    "LFBIS-Betriebsnummer",
    "Abgabenkontonummer",
    "Business Identity Code",
    "National VAT Number",
    "Other MS VAT Number",
    "DK VAT Number",
    "Organisationsnummer",
    "Registrikood",
    "Legal Person's Code",
    "ABER",
    "KUR",
    "FIBER",
    "Sonstige",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="TAM-Detailseiten nachlesen und nationale Kennungen korrigieren.",
    )
    parser.add_argument("--dry", action="store_true", help="Nur anzeigen, nicht schreiben.")
    parser.add_argument("--source-key", default="tam_de", help="Source-Key, default tam_de.")
    parser.add_argument("--query", help="Beguenstigtenname per ILIKE filtern.")
    parser.add_argument(
        "--record-id",
        action="append",
        default=[],
        help="Konkrete TAM-Kennung, wiederholbar, z.B. TM-12511862.",
    )
    parser.add_argument("--limit", type=int, default=500, help="Maximale Anzahl Datensaetze.")
    parser.add_argument("--after-id", help="Nur Datensaetze mit id > AFTER_ID verarbeiten.")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Alle TAM-Datensaetze mit source_url pruefen. Default: nur bekannte Kennungsart-Labels.",
    )
    parser.add_argument("--sleep", type=float, default=0.2, help="Pause zwischen TAM-Requests.")
    parser.add_argument("--commit-every", type=int, default=100, help="Zwischencommit nach N Updates.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    db = SessionLocal()
    client = httpx.Client(
        timeout=HARVEST_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": DEFAULT_USER_AGENT, "Accept-Language": "de-DE,de;q=0.9"},
    )
    try:
        q = (
            db.query(StateAidAward)
            .filter(StateAidAward.source_key == args.source_key)
            .filter(StateAidAward.source_url.isnot(None))
        )
        if args.record_id:
            q = q.filter(StateAidAward.source_record_id.in_(args.record_id))
        if args.query:
            q = q.filter(StateAidAward.beneficiary_name.ilike(f"%{args.query}%"))
        if args.after_id:
            q = q.filter(StateAidAward.id > args.after_id)
        if not args.record_id and not args.query and not args.all:
            q = q.filter(
                StateAidAward.beneficiary_identifier.in_(IDENTIFIER_TYPE_LABELS),
            )

        rows = q.order_by(StateAidAward.id).limit(args.limit).all()
        log.info("Kandidaten: %d (dry=%s)", len(rows), args.dry)

        changed = unchanged = failed = 0
        last_id = None
        for award in rows:
            last_id = award.id
            url = _detail_url_with_lang(award.source_url or "")
            if not url:
                unchanged += 1
                continue
            try:
                resp = client.get(url)
                resp.raise_for_status()
                detail = parse_award_detail(resp.text)
            except Exception as exc:  # noqa: BLE001
                failed += 1
                log.warning("%s: Detailabruf fehlgeschlagen: %s", award.source_record_id, exc)
                continue

            national_id = (detail.get("national_id") or "").strip()
            national_id_type = (detail.get("national_id_type") or "").strip()
            if not national_id:
                unchanged += 1
                log.info("%s: keine nationale Kennung auf Detailseite", award.source_record_id)
                time.sleep(args.sleep)
                continue

            raw_payload = dict(award.raw_payload or {})
            old_identifier = award.beneficiary_identifier
            old_payload_id = raw_payload.get("national_id")
            old_payload_type = raw_payload.get("national_id_type")
            needs_update = (
                old_identifier != national_id
                or old_payload_id != national_id
                or old_payload_type != national_id_type
            )
            if not needs_update:
                unchanged += 1
                time.sleep(args.sleep)
                continue

            changed += 1
            log.info(
                "%s: %r -> %r (%s)",
                award.source_record_id,
                old_identifier,
                national_id,
                national_id_type or "Art unbekannt",
            )
            if not args.dry:
                raw_payload["national_id"] = national_id
                if national_id_type:
                    raw_payload["national_id_type"] = national_id_type
                award.raw_payload = raw_payload
                award.beneficiary_identifier = national_id
                if changed % max(args.commit_every, 1) == 0:
                    db.commit()
            time.sleep(args.sleep)

        if not args.dry:
            db.commit()
        log.info("Fertig: %d aktualisiert, %d unveraendert, %d fehlgeschlagen", changed, unchanged, failed)
        if last_id:
            log.info("Resume-Cursor fuer naechsten Batch: --after-id %s", last_id)
        return 0 if failed == 0 else 1
    finally:
        client.close()
        db.close()


if __name__ == "__main__":
    sys.exit(main())
