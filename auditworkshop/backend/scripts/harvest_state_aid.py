#!/usr/bin/env python3
"""
flowworkshop · scripts/harvest_state_aid.py

CLI-Wrapper um den TAM-Harvester (Plan §11). Wird im Container so aufgerufen:

    # Default: smart — nur neue Datensaetze, alte bleiben unveraendert.
    python scripts/harvest_state_aid.py --country DE --limit 200

    # Auto-Since wird im smart-Modus aus last_successful_harvest_at - 14 Tagen
    # abgeleitet. Ein expliziter --since ueberschreibt das Auto-Since:
    python scripts/harvest_state_aid.py --country AT --since 2024-01-01

    # Volles Re-Scan inkl. Korrekturen (ON CONFLICT DO UPDATE):
    python scripts/harvest_state_aid.py --country DE --full-refresh --limit 500

    # Hard-Reset: vor Insert alle Awards der Quelle loeschen.
    python scripts/harvest_state_aid.py --country DE --force --limit 500

    # Chunked Harvest: pro Jahr ein eigener Lauf (idempotent dank smart-Mode):
    python scripts/harvest_state_aid.py --country DE --since 2022-01-01 \
        --until 2024-12-31 --chunk-by year --limit 50000

    # Full-History: alles ab TAM-Pflicht 1.7.2014 bis heute (kann 30+ min dauern):
    python scripts/harvest_state_aid.py --country DE --full-history

    # Region- und Connectivity-Tests:
    python scripts/harvest_state_aid.py --country DE --region RegionNuts2024.DE7
    python scripts/harvest_state_aid.py --check --country DE

Default: keine Region → erfasst auch Bund-Beihilfen.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, date
from pathlib import Path

# Pfad zum Backend-Verzeichnis (analog zu ingest_knowledge.py)
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import SessionLocal
from services.state_aid_harvester import (
    HarvestParams,
    HarvestResult,
    run_harvest,
    _default_source_key,
)
from services.state_aid_service import ISO3_TO_ISO2


# ── Konstanten ────────────────────────────────────────────────────────────────

# TAM-Pflicht zur Veroeffentlichung von Awards beginnt am 1.7.2014 (Art. 9 GBER,
# VO 651/2014). Davor sind im Register keine Daten zu erwarten.
TAM_FULL_HISTORY_START = date(2014, 7, 1)

# Pause zwischen Jahres-Chunks: TAM gegenueber freundlich, parallel Logging.
CHUNK_SLEEP_SECONDS = 2.0


# ── ISO-Mapping ───────────────────────────────────────────────────────────────

# umgekehrte Tabelle ISO-2 → ISO-3 (TAM erwartet ISO-3 Code)
ISO2_TO_ISO3 = {iso2: iso3 for iso3, iso2 in ISO3_TO_ISO2.items()}


def _normalize_country_arg(value: str) -> str:
    """Eingabe (ISO-2 oder ISO-3) auf ISO-3 normalisieren — TAM erwartet ISO-3."""
    raw = (value or "").strip().upper()
    if not raw:
        raise argparse.ArgumentTypeError("Leerer Country-Code.")
    if len(raw) == 3 and raw in ISO3_TO_ISO2:
        return raw
    if len(raw) == 2 and raw in ISO2_TO_ISO3:
        return ISO2_TO_ISO3[raw]
    if len(raw) == 2 and raw == "EL":  # Sonderfall Griechenland
        return "GRC"
    raise argparse.ArgumentTypeError(
        f"Unbekannter Country-Code '{value}'. Erwartet ISO-2 (DE/AT) oder ISO-3 (DEU/AUT)."
    )


def _parse_iso_date(value: str) -> date:
    """argparse-Type fuer YYYY-MM-DD."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Ungueltiges Datum '{value}', erwartet YYYY-MM-DD.") from exc


# ── Pure Helper: Jahres-Buckets ──────────────────────────────────────────────


def build_year_chunks(since: date, until: date) -> list[tuple[date, date]]:
    """Zerlegt einen Zeitraum in Jahres-Chunks (inklusive Grenz-Jahre).

    Pure Helper — testbar ohne TAM/DB. Pro Jahr wird ein Tupel (start, end)
    erzeugt, wobei start/end auf das gegebene Fenster geclippt werden:

      build_year_chunks(2022-06-01, 2024-03-01) -> [
          (2022-06-01, 2022-12-31),
          (2023-01-01, 2023-12-31),
          (2024-01-01, 2024-03-01),
      ]

    Wenn ``since == until`` oder beide im selben Jahr liegen, gibt es genau
    einen Chunk mit den Originalgrenzen.
    """
    if since > until:
        raise ValueError(f"since ({since}) muss <= until ({until}) sein.")

    chunks: list[tuple[date, date]] = []
    for year in range(since.year, until.year + 1):
        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)
        chunk_start = max(since, year_start)
        chunk_end = min(until, year_end)
        chunks.append((chunk_start, chunk_end))
    return chunks


# ── CLI ───────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="EU-Beihilfe-Transparenzregister (TAM) harvesten.",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Nur Quelle anpingen + erste Seite parsen, keine DB-Schreibs.",
    )
    parser.add_argument(
        "--country", default="DE", type=str,
        help="Country-Code ISO-2 oder ISO-3 (default DE).",
    )
    parser.add_argument(
        "--region", action="append", default=[],
        help="NUTS-Region-Filter (wiederholbar), z.B. RegionNuts2024.DE7. "
             "Default: keine Region → erfasst auch Bund-Beihilfen.",
    )
    parser.add_argument(
        "--source", default=None,
        help="Source-Key (default tam_de bzw. tam_at).",
    )
    parser.add_argument("--since", type=_parse_iso_date, default=None,
                        help="Granting-Datum ab (YYYY-MM-DD).")
    parser.add_argument("--until", type=_parse_iso_date, default=None,
                        help="Granting-Datum bis (YYYY-MM-DD).")
    parser.add_argument(
        "--limit", type=int, default=500,
        help="Maximum Awards pro Lauf (default 500, Workshop-tauglich).",
    )
    parser.add_argument(
        "--page-size", type=int, default=100,
        help="TAM-Seitengroesse (default 100, max 100).",
    )
    parser.add_argument(
        "--chunk-by", choices=["year", "none"], default="none",
        help=(
            "Zerlegung des Zeitraums in Jahres-Buckets. Default 'none' "
            "(ein einziger Lauf). 'year' iteriert pro Jahr von --since bis "
            "--until und ruft run_harvest mehrfach auf. Idempotent dank "
            "smart-Mode. Zwischen den Jahren 2 s Pause."
        ),
    )
    parser.add_argument(
        "--full-history", action="store_true",
        help=(
            "Komplette Historie ab 1.7.2014 (TAM-Pflicht laut Art. 9 GBER). "
            "Setzt implizit --since 2014-07-01, --until heute, "
            "--chunk-by year und --limit 100000 (sofern nicht anders "
            "uebergeben). ACHTUNG: Lange Laufzeit (kann 30+ min dauern), "
            "TAM ist rate-limited."
        ),
    )
    # Drei Modi (mutually exclusive). Default: smart.
    mode_group = parser.add_mutually_exclusive_group(required=False)
    mode_group.add_argument(
        "--smart", dest="mode", action="store_const", const="smart",
        help=(
            "Default-Modus: nur neue Datensaetze einfuegen, alte bleiben "
            "unveraendert. Auto-Since 14 Tage vor letztem erfolgreichen "
            "Lauf, sofern --since nicht explizit gesetzt ist."
        ),
    )
    mode_group.add_argument(
        "--full-refresh", dest="mode", action="store_const", const="full-refresh",
        help=(
            "Voller Re-Scan: bei Konflikt UPDATE — uebernimmt nachtraegliche "
            "Korrekturen aus TAM. Bestehende Datensaetze werden ueberschrieben."
        ),
    )
    mode_group.add_argument(
        "--force", dest="mode", action="store_const", const="force",
        help=(
            "Hard-Reset: vor dem Lauf alle Awards der Source loeschen, danach "
            "Insert. Geloeschte Anzahl wird im Run-Log vermerkt."
        ),
    )
    parser.add_argument("--verbose", action="store_true", help="DEBUG-Logging.")
    parser.set_defaults(mode="smart")
    return parser


def _result_to_dict(result: HarvestResult, *, mode: str, country_iso3: str,
                    source_key: str, check_only: bool,
                    since: date | None, until: date | None) -> dict:
    """HarvestResult -> JSON-faehiges Dict (gleiches Format wie Single-Run)."""
    return {
        "run_id": result.run_id,
        "status": result.status,
        "mode": mode,
        "records_seen": result.records_seen,
        "records_inserted": result.records_inserted,
        "records_updated": result.records_updated,
        "records_skipped": result.records_skipped,
        "records_failed": result.records_failed,
        "pages_fetched": result.pages_fetched,
        "error": result.error,
        "country_iso3": country_iso3,
        "source_key": source_key,
        "since": since.isoformat() if since else None,
        "until": until.isoformat() if until else None,
        "check_only": check_only,
    }


def _run_chunked(args, log: logging.Logger,
                 country_iso3: str, source_key: str,
                 page_size: int, mode: str) -> dict:
    """Fuehrt einen Chunked-Harvest pro Jahr aus.

    Pro Chunk wird ein eigener ``run_harvest`` aufgerufen. Fehler in einem
    Chunk fuehren NICHT zum Abbruch — der Fehler wird geloggt und der
    naechste Chunk gestartet. Im Aggregat-Status wird "partial" zurueck-
    gegeben, wenn mindestens ein Chunk fehlschlaegt.
    """
    chunks = build_year_chunks(args.since, args.until)
    log.info(
        "Chunked Harvest: %d Jahres-Buckets von %s bis %s (limit/Chunk=%d).",
        len(chunks), args.since, args.until, args.limit,
    )

    chunk_results: list[dict] = []
    totals = {
        "records_seen": 0,
        "records_inserted": 0,
        "records_updated": 0,
        "records_skipped": 0,
        "records_failed": 0,
        "pages_fetched": 0,
        "chunks_total": len(chunks),
        "chunks_ok": 0,
        "chunks_partial": 0,
        "chunks_failed": 0,
    }

    for idx, (chunk_since, chunk_until) in enumerate(chunks):
        # Pause zwischen Chunks (nicht vor dem ersten).
        if idx > 0:
            log.info("Schlaft %.1fs zwischen Jahres-Chunks ...", CHUNK_SLEEP_SECONDS)
            time.sleep(CHUNK_SLEEP_SECONDS)

        params = HarvestParams(
            country_iso3=country_iso3,
            region_codes=list(args.region or []),
            since=chunk_since,
            until=chunk_until,
            limit=max(1, int(args.limit)),
            page_size=page_size,
            triggered_by="cli",
            source_key=source_key,
            mode=mode,
        )
        log.info(
            "Chunk %d/%d (%s): country=%s mode=%s since=%s until=%s",
            idx + 1, len(chunks), chunk_since.year,
            country_iso3, mode, chunk_since, chunk_until,
        )

        db = SessionLocal()
        try:
            try:
                result: HarvestResult = run_harvest(
                    db, params, check_only=args.check,
                )
            except Exception as exc:  # noqa: BLE001
                # Chunk-Fehler — weitermachen mit naechstem Jahr.
                log.exception(
                    "Chunk %s fehlgeschlagen — fahre mit naechstem Jahr fort.",
                    chunk_since.year,
                )
                chunk_results.append({
                    "chunk_year": chunk_since.year,
                    "since": chunk_since.isoformat(),
                    "until": chunk_until.isoformat(),
                    "status": "failed",
                    "error": str(exc),
                    "records_seen": 0,
                    "records_inserted": 0,
                    "records_skipped": 0,
                    "records_failed": 0,
                })
                totals["chunks_failed"] += 1
                continue
        finally:
            db.close()

        log.info(
            "Chunk %s %s: seen=%d inserted=%d skipped=%d failed=%d",
            chunk_since.year,
            ("OK" if result.status == "ok" else result.status.upper()),
            result.records_seen, result.records_inserted,
            result.records_skipped, result.records_failed,
        )

        chunk_dict = _result_to_dict(
            result, mode=mode, country_iso3=country_iso3,
            source_key=source_key, check_only=bool(args.check),
            since=chunk_since, until=chunk_until,
        )
        chunk_dict["chunk_year"] = chunk_since.year
        chunk_results.append(chunk_dict)

        totals["records_seen"] += result.records_seen
        totals["records_inserted"] += result.records_inserted
        totals["records_updated"] += result.records_updated
        totals["records_skipped"] += result.records_skipped
        totals["records_failed"] += result.records_failed
        totals["pages_fetched"] += result.pages_fetched
        if result.status == "ok":
            totals["chunks_ok"] += 1
        elif result.status == "partial":
            totals["chunks_partial"] += 1
        elif result.status == "failed":
            totals["chunks_failed"] += 1
        # check_only zaehlt als 'ok' fuer den Status-Aggregator.
        elif result.status == "check_only":
            totals["chunks_ok"] += 1

    # Aggregat-Status:
    #   alle ok           -> ok
    #   keiner ok         -> failed
    #   sonst (gemischt)  -> partial
    if totals["chunks_failed"] == 0 and totals["chunks_partial"] == 0:
        agg_status = "ok"
    elif totals["chunks_ok"] == 0 and totals["chunks_partial"] == 0:
        agg_status = "failed"
    else:
        agg_status = "partial"

    return {
        "status": agg_status,
        "mode": mode,
        "country_iso3": country_iso3,
        "source_key": source_key,
        "since": args.since.isoformat(),
        "until": args.until.isoformat(),
        "chunk_by": "year",
        "check_only": bool(args.check),
        "chunks": chunk_results,
        "totals": totals,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s  %(name)s  %(message)s",
    )
    log = logging.getLogger("harvest_state_aid")

    # ── --full-history: implizite Defaults setzen ──
    if args.full_history:
        if args.since is None:
            args.since = TAM_FULL_HISTORY_START
        if args.until is None:
            args.until = date.today()
        if args.chunk_by == "none":
            args.chunk_by = "year"
        # Limit hochziehen — Default 500 wuerde keine Vollhistorie schaffen.
        # Nur anpassen, wenn Aufrufer beim Default geblieben ist.
        if args.limit == 500:
            args.limit = 100000
        log.warning(
            "Full-History aktiv: %s bis %s, chunk-by=year, limit=%d/Chunk. "
            "Kann 30+ min dauern (TAM rate-limited ~0.6s/Request).",
            args.since, args.until, args.limit,
        )

    country_iso3 = _normalize_country_arg(args.country)
    page_size = max(1, min(int(args.page_size), 100))
    source_key = args.source or _default_source_key(country_iso3)
    mode = args.mode or "smart"

    # ── Chunked-Modus? ──
    use_chunks = (
        args.chunk_by == "year"
        and args.since is not None
        and args.until is not None
        and args.since < args.until
    )

    if use_chunks:
        log.info(
            "TAM-Harvest gestartet (chunked): country=%s region=%s source=%s "
            "mode=%s since=%s until=%s limit=%s/Chunk check=%s",
            country_iso3, args.region or "—", source_key, mode,
            args.since, args.until, args.limit, args.check,
        )
        payload = _run_chunked(
            args, log,
            country_iso3=country_iso3,
            source_key=source_key,
            page_size=page_size,
            mode=mode,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload["status"] in ("ok", "partial") else 2

    # ── Single-Run-Modus ──
    params = HarvestParams(
        country_iso3=country_iso3,
        region_codes=list(args.region or []),
        since=args.since,
        until=args.until,
        limit=max(1, int(args.limit)),
        page_size=page_size,
        triggered_by="cli",
        source_key=source_key,
        mode=mode,
    )

    log.info(
        "TAM-Harvest gestartet: country=%s region=%s source=%s mode=%s "
        "since=%s until=%s limit=%s check=%s",
        country_iso3, params.region_codes or "—", source_key, mode,
        params.since, params.until, params.limit, args.check,
    )

    db = SessionLocal()
    try:
        # Hinweis: Force-Loeschung passiert jetzt zentral in run_harvest()
        # und wird im Run-Log vermerkt. Kein zusaetzliches Pre-Delete hier.
        result: HarvestResult = run_harvest(db, params, check_only=args.check)
    finally:
        db.close()

    payload = _result_to_dict(
        result, mode=mode, country_iso3=country_iso3,
        source_key=source_key, check_only=bool(args.check),
        since=params.since, until=params.until,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if result.status in ("ok", "partial", "check_only") else 2


if __name__ == "__main__":
    sys.exit(main())
