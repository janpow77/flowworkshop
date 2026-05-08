#!/usr/bin/env python3
"""
flowworkshop · scripts/backfill_beneficiary_records.py

Phase 6a Backfill: Liest die bestehenden per-Source-Tabellen
(``workshop_df_<source>``) ueber ``get_beneficiary_sources()`` und mapped
ihre Zeilen ueber ``services.geocoding_service.detect_columns`` auf das
kanonische Schema. Schreibt jede Zeile als ``BeneficiaryRecord`` in die
zentrale ``workshop_beneficiary_records``-Tabelle.

Idempotent dank ``smart``-Mode (ON CONFLICT DO NOTHING). Mehrfache Laeufe
fuegen nichts doppelt ein. Mit ``--full-refresh`` werden Konflikte
upgedatet, mit ``--force`` werden vor dem Lauf alle Records der Quelle
geloescht. Die alten per-Source-Tabellen bleiben als Audit-Backup
erhalten — das Loeschen ist eine **separate** Admin-Aktion.

Aufruf-Beispiele:

    # Dry-Run: nur zaehlen, nichts schreiben.
    docker exec auditworkshop-backend \\
        python scripts/backfill_beneficiary_records.py --dry

    # Eine Quelle in die zentrale Tabelle uebernehmen.
    docker exec auditworkshop-backend \\
        python scripts/backfill_beneficiary_records.py --source hessen_efre_2021_2027

    # Alle Quellen mit full-refresh (Korrekturen ziehen nach).
    docker exec auditworkshop-backend \\
        python scripts/backfill_beneficiary_records.py --full-refresh
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Pfad zum Backend-Verzeichnis (analog zu harvest_state_aid.py).
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402

from database import SessionLocal, engine  # noqa: E402
from models.beneficiary_records import BeneficiaryHarvestRun, BeneficiaryRecord  # noqa: E402
from services.beneficiary_harvester import (  # noqa: E402
    _normalize_company_name_simple,
    compute_record_hash,
)
from services.dataframe_service import (  # noqa: E402
    _safe_table_name,
    get_beneficiary_sources,
)
from services.state_aid_service import parse_amount, parse_date  # noqa: E402

log = logging.getLogger("backfill_beneficiary_records")


# ── CLI ───────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill der Beneficiary-Datensaetze in die zentrale Tabelle.",
    )
    parser.add_argument(
        "--dry", action="store_true",
        help="Nur zaehlen, nichts schreiben (Plausibilitaets-Check).",
    )
    parser.add_argument(
        "--source", action="append", default=[],
        help=(
            "Source-Key (entspricht Eintrag in workshop_df_metadata.source). "
            "Mehrfach angebbar. Default: alle Beneficiary-Quellen."
        ),
    )
    parser.add_argument(
        "--country-code", default=None,
        help="Filter (DE/AT) — nur Quellen dieses Landes.",
    )
    mode_group = parser.add_mutually_exclusive_group(required=False)
    mode_group.add_argument(
        "--smart", dest="mode", action="store_const", const="smart",
        help="Default: ON CONFLICT DO NOTHING (idempotent).",
    )
    mode_group.add_argument(
        "--full-refresh", dest="mode", action="store_const", const="full-refresh",
        help="Bei Konflikt UPDATE — Korrekturen aus den per-Source-Tabellen "
             "ziehen nach.",
    )
    mode_group.add_argument(
        "--force", dest="mode", action="store_const", const="force",
        help="Pre-Delete der Quelle vor Insert.",
    )
    parser.add_argument("--verbose", action="store_true", help="DEBUG-Logging.")
    parser.set_defaults(mode="smart")
    return parser


# ── Helper ────────────────────────────────────────────────────────────────────


def _coerce_value(value: Any) -> Any:
    """SQL-Roh-Wert in JSONB-/String-tauglichen Typ konvertieren."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    return value


def _stringify(value: Any) -> str | None:
    v = _coerce_value(value)
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _stringify_plz(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if value.is_integer():
            return str(int(value))
    s = str(value).strip()
    return s or None


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        f = float(value)
        if math.isnan(f):
            return None
        return f
    try:
        return float(str(value).replace(",", ".").strip())
    except (ValueError, TypeError):
        return None


def _normalize_text(text_value: Any) -> str:
    """Schwacher Whitespace-/Akzent-Normalizer fuer Hash-Inputs."""
    if text_value is None:
        return ""
    s = str(text_value).strip()
    if not s:
        return ""
    return unicodedata.normalize("NFKC", s)


# ── Hauptfunktion: pro Source ────────────────────────────────────────────────


def backfill_source(source_info: dict, *, mode: str, dry: bool) -> dict:
    """Liest die per-Source-Tabelle und schreibt sie in die zentrale Tabelle.

    ``source_info`` stammt aus ``get_beneficiary_sources()`` und enthaelt
    ``source``, ``bundesland``, ``fonds``, ``periode``, ``country_code``,
    ``filename`` plus dem ``table_name``.
    """
    from services.geocoding_service import detect_columns

    source_key = source_info["source"]
    table_name = source_info.get("table_name") or _safe_table_name(source_key)
    cols = detect_columns(source_key)

    name_col = cols.get("name")
    if not name_col:
        # Ohne Name keine Beneficiary-Zeile — UI haette ohnehin Unbekannt.
        log.warning("Skip %s: keine name-Spalte erkannt.", source_key)
        return {
            "source_key": source_key,
            "status": "skipped_no_name_column",
            "rows_seen": 0,
            "rows_inserted": 0,
            "rows_skipped": 0,
            "rows_failed": 0,
        }

    project_col = cols.get("projekt")
    aktz_col = cols.get("aktenzeichen")
    desc_col = cols.get("beschreibung")
    cost_col = cols.get("kosten")
    location_col = cols.get("standort") or cols.get("ort")
    landkreis_col = cols.get("landkreis")
    plz_col = cols.get("plz")
    lat_col = cols.get("latitude")
    lon_col = cols.get("longitude")
    beginn_col = cols.get("beginn")
    ende_col = cols.get("ende")

    # Alle Spalten der Tabelle holen, damit wir raw_payload korrekt fuellen.
    with engine.connect() as conn:
        all_cols_rows = conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = :t ORDER BY ordinal_position"
        ), {"t": table_name}).fetchall()
        all_cols = [r[0] for r in all_cols_rows]
        if not all_cols:
            log.warning("Skip %s: Tabelle %s leer/nicht gefunden.",
                        source_key, table_name)
            return {
                "source_key": source_key,
                "status": "skipped_no_table",
                "rows_seen": 0, "rows_inserted": 0,
                "rows_skipped": 0, "rows_failed": 0,
            }

        # Mit doppelten Quotes wegen Sonderzeichen im Spaltennamen.
        col_list_sql = ", ".join(f'"{c}"' for c in all_cols)
        rows = conn.execute(
            text(f'SELECT {col_list_sql} FROM "{table_name}"')
        ).fetchall()

    if dry:
        return {
            "source_key": source_key,
            "table_name": table_name,
            "status": "dry",
            "rows_seen": len(rows),
            "rows_inserted": 0,
            "rows_skipped": 0,
            "rows_failed": 0,
            "name_col": name_col,
            "cost_col": cost_col,
            "location_col": location_col,
        }

    # Run-Eintrag fuer Audit-Spur.
    run_id = str(uuid.uuid4())
    db = SessionLocal()
    try:
        run = BeneficiaryHarvestRun(
            id=run_id,
            source_key=source_key,
            triggered_by="cli:backfill",
            status="running",
            parameters={
                "mode": mode,
                "table_name": table_name,
                "bundesland": source_info.get("bundesland"),
                "fonds": source_info.get("fonds"),
                "periode": source_info.get("periode"),
                "country_code": source_info.get("country_code"),
                "filename": source_info.get("filename"),
                "rows_in_source": len(rows),
            },
        )
        db.add(run)
        db.commit()

        # Force-Mode: Pre-Delete vor dem Iterieren.
        force_deleted = 0
        if mode == "force":
            force_deleted = (
                db.query(BeneficiaryRecord)
                .filter(BeneficiaryRecord.source_key == source_key)
                .delete(synchronize_session=False)
            )
            db.commit()

        seen = inserted = skipped = failed = 0
        for idx, row in enumerate(rows, start=1):
            seen += 1
            try:
                entry = dict(row._mapping)
                # Original-Row als JSONB serialisierbar machen.
                raw_row = {k: _coerce_value(v) for k, v in entry.items()}

                # Pflicht: Name. Ohne Name → failed (kein valider Datensatz).
                name_value = entry.get(name_col)
                name_str = _stringify(name_value) or ""
                if not name_str:
                    failed += 1
                    continue

                # Felder fuer Hash- und Spalten-Inhalt zusammenbauen.
                hash_input = {
                    "beneficiary_name": name_str,
                    "project_name": _stringify(entry.get(project_col)) if project_col else None,
                    "project_aktenzeichen": _stringify(entry.get(aktz_col)) if aktz_col else None,
                    "bundesland": source_info.get("bundesland"),
                    "periode": source_info.get("periode"),
                    "fonds": source_info.get("fonds"),
                    "funded_at_raw": _stringify(entry.get(beginn_col)) if beginn_col else None,
                    "cost_total_raw": _stringify(entry.get(cost_col)) if cost_col else None,
                }
                # Eindeutigkeit innerhalb der Quelle: bei vollstaendigen
                # Duplikaten in der Quell-Tabelle (mehrfache identische
                # Zeilen) wuerde unser Hash kollidieren — wir mischen die
                # source_row_number in Cluster, damit jede Zeile eindeutig
                # bleibt. Das ist ein Backfill-spezifischer Kompromiss:
                # in der Source-Tabelle gibt es haeufig 1-zu-1-Duplikate.
                hash_input["__row_idx"] = idx
                record_hash = compute_record_hash(hash_input, source_key)

                cost_total = parse_amount(
                    _stringify(entry.get(cost_col)) if cost_col else None
                )
                project_start = parse_date(
                    _stringify(entry.get(beginn_col)) if beginn_col else None
                )
                project_end = parse_date(
                    _stringify(entry.get(ende_col)) if ende_col else None
                )
                # Fuer funded_at nutzen wir Projekt-Start als Naeherung.
                funded_at = project_start

                values = {
                    "source_key": source_key,
                    "source_record_id": record_hash,
                    "upload_run_id": run_id,
                    "source_filename": source_info.get("filename"),
                    "source_sheet": None,
                    "source_row_number": idx,
                    "beneficiary_name": name_str,
                    "beneficiary_name_normalized": _normalize_company_name_simple(name_str),
                    "project_name": _stringify(entry.get(project_col)) if project_col else None,
                    "project_aktenzeichen": _stringify(entry.get(aktz_col)) if aktz_col else None,
                    "project_description": _stringify(entry.get(desc_col)) if desc_col else None,
                    "bundesland": source_info.get("bundesland"),
                    "fonds": source_info.get("fonds"),
                    "periode": source_info.get("periode"),
                    "country_code": source_info.get("country_code"),
                    "location": _stringify(entry.get(location_col)) if location_col else None,
                    "landkreis": _stringify(entry.get(landkreis_col)) if landkreis_col else None,
                    "plz": _stringify_plz(entry.get(plz_col)) if plz_col else None,
                    "nuts_code": None,
                    "latitude": _coerce_float(entry.get(lat_col)) if lat_col else None,
                    "longitude": _coerce_float(entry.get(lon_col)) if lon_col else None,
                    "cost_total_raw": _stringify(entry.get(cost_col)) if cost_col else None,
                    "cost_total": cost_total,
                    "cost_eu_funding_raw": None,
                    "cost_eu_funding": None,
                    "currency": None,
                    "project_start_raw": _stringify(entry.get(beginn_col)) if beginn_col else None,
                    "project_start": project_start,
                    "project_end_raw": _stringify(entry.get(ende_col)) if ende_col else None,
                    "project_end": project_end,
                    "funded_at_raw": _stringify(entry.get(beginn_col)) if beginn_col else None,
                    "funded_at": funded_at,
                    "raw_payload": raw_row,
                }

                stmt = pg_insert(BeneficiaryRecord).values(**values)
                if mode == "smart":
                    stmt = stmt.on_conflict_do_nothing(
                        index_elements=["source_key", "source_record_id"],
                    )
                elif mode == "full-refresh":
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["source_key", "source_record_id"],
                        set_={
                            k: getattr(stmt.excluded, k) for k in (
                                "upload_run_id", "source_filename",
                                "source_sheet", "source_row_number",
                                "beneficiary_name", "beneficiary_name_normalized",
                                "project_name", "project_aktenzeichen",
                                "project_description",
                                "bundesland", "fonds", "periode", "country_code",
                                "location", "landkreis", "plz", "nuts_code",
                                "latitude", "longitude",
                                "cost_total_raw", "cost_total",
                                "cost_eu_funding_raw", "cost_eu_funding",
                                "currency",
                                "project_start_raw", "project_start",
                                "project_end_raw", "project_end",
                                "funded_at_raw", "funded_at",
                                "raw_payload",
                            )
                        },
                    )
                # mode == 'force': Pre-Delete hat geleert.
                result = db.execute(stmt)
                rc = result.rowcount or 0
                if mode == "smart":
                    if rc > 0:
                        inserted += 1
                    else:
                        skipped += 1
                else:
                    if rc > 0:
                        inserted += 1
            except Exception as exc:  # noqa: BLE001
                failed += 1
                log.warning(
                    "Backfill-Fehler bei %s row=%d: %s",
                    source_key, idx, exc,
                )

        db.commit()
        run.status = "ok" if failed == 0 else "partial"
        run.records_seen = seen
        run.records_inserted = inserted
        run.records_skipped = skipped
        run.records_failed = failed
        if mode == "force" and force_deleted:
            run.error_message = f"force: {force_deleted} Records vorab geloescht."
        run.finished_at = datetime.now(timezone.utc)
        db.commit()

        return {
            "source_key": source_key,
            "table_name": table_name,
            "status": run.status,
            "mode": mode,
            "rows_seen": seen,
            "rows_inserted": inserted,
            "rows_skipped": skipped,
            "rows_failed": failed,
            "force_deleted": force_deleted if mode == "force" else None,
            "run_id": run_id,
        }
    finally:
        db.close()


# ── Main ──────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s  %(name)s  %(message)s",
    )

    sources = get_beneficiary_sources(country_code=args.country_code)
    if args.source:
        target_keys = set(args.source)
        sources = [s for s in sources if s["source"] in target_keys]
    if not sources:
        log.error("Keine passenden Beneficiary-Quellen gefunden.")
        print(json.dumps({"status": "no_sources", "results": []}, ensure_ascii=False))
        return 2

    log.info(
        "Backfill startet — mode=%s, dry=%s, sources=%d",
        args.mode, args.dry, len(sources),
    )

    totals = {
        "rows_seen": 0,
        "rows_inserted": 0,
        "rows_skipped": 0,
        "rows_failed": 0,
        "sources_processed": 0,
    }
    results: list[dict] = []
    for src in sources:
        try:
            res = backfill_source(src, mode=args.mode, dry=args.dry)
        except Exception as exc:  # noqa: BLE001
            log.exception("Backfill-Quelle %s fehlgeschlagen.", src.get("source"))
            res = {
                "source_key": src.get("source"),
                "status": "exception",
                "error": str(exc),
                "rows_seen": 0, "rows_inserted": 0,
                "rows_skipped": 0, "rows_failed": 0,
            }
        results.append(res)
        totals["rows_seen"] += res.get("rows_seen", 0)
        totals["rows_inserted"] += res.get("rows_inserted", 0)
        totals["rows_skipped"] += res.get("rows_skipped", 0)
        totals["rows_failed"] += res.get("rows_failed", 0)
        totals["sources_processed"] += 1
        log.info(
            "%s: status=%s seen=%d inserted=%d skipped=%d failed=%d",
            res.get("source_key"), res.get("status"),
            res.get("rows_seen", 0), res.get("rows_inserted", 0),
            res.get("rows_skipped", 0), res.get("rows_failed", 0),
        )

    payload = {
        "status": "dry" if args.dry else "ok",
        "mode": args.mode,
        "country_code": args.country_code,
        "totals": totals,
        "results": results,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
