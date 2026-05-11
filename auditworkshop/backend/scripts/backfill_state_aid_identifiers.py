#!/usr/bin/env python3
"""
flowworkshop · scripts/backfill_state_aid_identifiers.py

Liest bestehende TAM-Award-Detailseiten nach und korrigiert die nationale
Kennung in workshop_state_aid_awards.

Aufruf:
    docker exec auditworkshop-backend python scripts/backfill_state_aid_identifiers.py --query "Franz Hof"
    docker exec auditworkshop-backend python scripts/backfill_state_aid_identifiers.py --record-id TM-12511862
    docker exec auditworkshop-backend python scripts/backfill_state_aid_identifiers.py --dry --limit 50
    docker exec auditworkshop-backend python scripts/backfill_state_aid_identifiers.py --concurrency 10

Performance-Modus (Default seit 2026-05-11):
- ``--concurrency 10`` parallelisiert die TAM-Detail-Requests per
  ``httpx.AsyncClient`` + ``asyncio.Semaphore``. Damit erreicht ein
  einzelner Worker ~15-25 Records/s statt ~1-2 Records/s sequenziell.
- Records, deren Detailseite **keine** nationale Kennung liefert, werden
  per ``raw_payload['scraped_at_no_id']`` markiert und beim naechsten
  Lauf uebersprungen (Negative-Cache, kein Schema-Migration noetig).
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as _dt
import logging
import sys
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
    parser.add_argument(
        "--sleep", type=float, default=0.0,
        help=(
            "Pause zwischen TAM-Requests pro Slot. Mit --concurrency>1 i.d.R. "
            "0 (Semaphore drosselt). Bei 429-Antworten hochsetzen."
        ),
    )
    parser.add_argument(
        "--commit-every", type=int, default=50,
        help=(
            "Zwischencommit-Batch-Groesse. Default 50 (war 10). Mit Async-Mode "
            "kommen mehr Updates pro Sekunde rein, ein groesserer Batch "
            "reduziert DB-Roundtrips."
        ),
    )
    parser.add_argument(
        "--worker-mod", type=int, default=1,
        help="Sharding-Modul fuer parallele Worker. Default 1 (kein Sharding).",
    )
    parser.add_argument(
        "--worker-id", type=int, default=0,
        help=(
            "Sharding-Index 0..worker-mod-1. Beispiel: 4 parallele Worker -> "
            "--worker-mod 4 --worker-id 0/1/2/3."
        ),
    )
    parser.add_argument(
        "--concurrency", type=int, default=10,
        help=(
            "Parallele HTTP-Requests pro Worker. Default 10 (war 1, "
            "sequenziell). EU-KOM TAM vertraegt 10 parallele Verbindungen "
            "pro IP ohne Throttle. Bei 429-Antworten reduzieren."
        ),
    )
    parser.add_argument(
        "--skip-negative-cache", action="store_true",
        help=(
            "Auch Records prüfen, die bereits einmal ohne national_id "
            "zurueckkamen (raw_payload.scraped_at_no_id gesetzt). Default: "
            "diese ueberspringen."
        ),
    )
    return parser


def _select_rows(db, args):
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
        q = q.filter(StateAidAward.beneficiary_identifier.in_(IDENTIFIER_TYPE_LABELS))
    if not args.skip_negative_cache and not args.record_id:
        # JSONB-Filter: ueberspringen, wenn schon einmal als "keine
        # nationale Kennung" gescraped. Nutzt B-Tree-Index-freie
        # Volltabellen-Suche; bei grossen Tabellen ggf. partiellen
        # Index auf raw_payload anlegen.
        from sqlalchemy import text as _sql_text
        q = q.filter(
            _sql_text(
                "COALESCE(raw_payload->>'scraped_at_no_id', '') = ''",
            ),
        )
    if args.worker_mod > 1:
        from sqlalchemy import or_ as _or
        hex_chars = "0123456789abcdef"
        chunk_size = max(1, 16 // args.worker_mod)
        start = args.worker_id * chunk_size
        end = start + chunk_size if args.worker_id < args.worker_mod - 1 else 16
        allowed = hex_chars[start:end]
        log.info(
            "Sharding aktiv: worker %d/%d (Hex-Praefixe %s)",
            args.worker_id, args.worker_mod, allowed,
        )
        q = q.filter(_or(*[StateAidAward.id.like(f"{c}%") for c in allowed]))

    return q.order_by(StateAidAward.id).limit(args.limit).all()


async def _fetch_one(award, client: httpx.AsyncClient, sem: asyncio.Semaphore, sleep_s: float):
    """Holt eine Detailseite. Gibt (status, award, national_id, national_id_type) zurueck."""
    url = _detail_url_with_lang(award.source_url or "")
    if not url:
        return ("no_url", award, None, None)
    async with sem:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            log.warning("%s: Detailabruf fehlgeschlagen: %s", award.source_record_id, exc)
            return ("error", award, None, None)
        text = resp.text
        if sleep_s > 0:
            await asyncio.sleep(sleep_s)
    # parse_award_detail ist pure CPU, ausserhalb Semaphore lassen
    try:
        detail = parse_award_detail(text)
    except Exception as exc:  # noqa: BLE001
        log.warning("%s: parse_award_detail fehlgeschlagen: %s", award.source_record_id, exc)
        return ("error", award, None, None)
    return (
        "ok",
        award,
        (detail.get("national_id") or "").strip(),
        (detail.get("national_id_type") or "").strip(),
    )


def _apply_result(award, national_id: str, national_id_type: str, args) -> str:
    """Wendet ein Fetch-Ergebnis auf das Award an. Gibt 'changed', 'unchanged' oder 'marked' zurueck."""
    raw_payload = dict(award.raw_payload or {})
    if not national_id:
        # Negative-Cache: einmal markieren und nie wieder anfragen
        raw_payload["scraped_at_no_id"] = _dt.datetime.utcnow().isoformat(timespec="seconds")
        award.raw_payload = raw_payload
        log.info("%s: keine nationale Kennung auf Detailseite (negative-cache)", award.source_record_id)
        return "marked"
    old_identifier = award.beneficiary_identifier
    old_payload_id = raw_payload.get("national_id")
    old_payload_type = raw_payload.get("national_id_type")
    needs_update = (
        old_identifier != national_id
        or old_payload_id != national_id
        or old_payload_type != national_id_type
    )
    if not needs_update:
        return "unchanged"
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
        # negative-cache-Marker entfernen, falls vorhanden (Record ist jetzt gut)
        raw_payload.pop("scraped_at_no_id", None)
        award.raw_payload = raw_payload
        award.beneficiary_identifier = national_id
    return "changed"


async def _run_async(rows, args, db) -> tuple[int, int, int, int, str | None]:
    sem = asyncio.Semaphore(args.concurrency)
    limits = httpx.Limits(
        max_connections=args.concurrency * 2,
        max_keepalive_connections=args.concurrency,
    )
    async with httpx.AsyncClient(
        timeout=HARVEST_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": DEFAULT_USER_AGENT, "Accept-Language": "de-DE,de;q=0.9"},
        limits=limits,
    ) as client:
        changed = unchanged = failed = marked = 0
        last_id: str | None = None
        batch = max(args.commit_every, 1)
        for start in range(0, len(rows), batch):
            slice_ = rows[start:start + batch]
            results = await asyncio.gather(
                *[_fetch_one(a, client, sem, args.sleep) for a in slice_],
            )
            for status, award, national_id, national_id_type in results:
                last_id = award.id
                if status == "error":
                    failed += 1
                    continue
                if status == "no_url":
                    unchanged += 1
                    continue
                outcome = _apply_result(award, national_id or "", national_id_type or "", args)
                if outcome == "changed":
                    changed += 1
                elif outcome == "marked":
                    marked += 1
                else:
                    unchanged += 1
            if not args.dry:
                db.commit()
            if (start // batch) % 10 == 0 and (changed + unchanged + marked + failed) > 0:
                log.info(
                    "Fortschritt: %d/%d (changed=%d unchanged=%d marked=%d failed=%d)",
                    start + len(slice_), len(rows), changed, unchanged, marked, failed,
                )
        return changed, unchanged, failed, marked, last_id


def main() -> int:
    args = build_parser().parse_args()
    db = SessionLocal()
    try:
        rows = _select_rows(db, args)
        log.info(
            "Kandidaten: %d (dry=%s, concurrency=%d)",
            len(rows), args.dry, args.concurrency,
        )
        if not rows:
            return 0
        changed, unchanged, failed, marked, last_id = asyncio.run(_run_async(rows, args, db))
        if not args.dry:
            db.commit()
        log.info(
            "Fertig: %d aktualisiert, %d unveraendert, %d negative-cache, %d fehlgeschlagen",
            changed, unchanged, marked, failed,
        )
        if last_id:
            log.info("Resume-Cursor fuer naechsten Batch: --after-id %s", last_id)
        # Exit-Code: 0 wenn weniger als 5 % Fehler, sonst 1
        total = changed + unchanged + failed + marked
        if total == 0:
            return 0
        return 0 if failed / max(total, 1) < 0.05 else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
