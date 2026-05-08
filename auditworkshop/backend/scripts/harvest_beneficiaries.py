#!/usr/bin/env python3
"""
flowworkshop · scripts/harvest_beneficiaries.py

Phase 6a CLI: Beneficiary-Harvest aus einer XLSX-/CSV-Datei in die zentrale
Tabelle ``workshop_beneficiary_records``. Analog zu
``scripts/harvest_state_aid.py`` mit drei Modi (smart, full-refresh, force).

Beispiele:

    # Default: smart — neue Records einfuegen, alte unberuehrt lassen.
    docker exec auditworkshop-backend \\
        python scripts/harvest_beneficiaries.py \\
        --source-key hessen_efre_2021_2027 \\
        --file /app/data/transparenzliste_hessen.xlsx \\
        --bundesland Hessen --fonds EFRE --periode 2021-2027

    # Volles Re-Scan (Korrekturen ziehen nach).
    docker exec auditworkshop-backend \\
        python scripts/harvest_beneficiaries.py \\
        --source-key hessen_efre_2021_2027 \\
        --file /app/data/transparenzliste_hessen.xlsx \\
        --full-refresh

    # Hard-Reset.
    docker exec auditworkshop-backend \\
        python scripts/harvest_beneficiaries.py \\
        --source-key hessen_efre_2021_2027 \\
        --file /app/data/transparenzliste_hessen.xlsx \\
        --force
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Pfad zum Backend-Verzeichnis (analog harvest_state_aid.py).
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import SessionLocal  # noqa: E402
from services.beneficiary_harvester import (  # noqa: E402
    BeneficiaryHarvestParams,
    run_beneficiary_harvest,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="XLSX-/CSV-Beneficiary in die zentrale Tabelle harvesten.",
    )
    parser.add_argument(
        "--source-key", required=True,
        help="Logischer Source-Key, z.B. 'hessen_efre_2021_2027'.",
    )
    parser.add_argument(
        "--file", required=True, type=Path,
        help="Pfad zur XLSX/XLS/CSV-Datei.",
    )
    parser.add_argument("--bundesland", default=None)
    parser.add_argument("--fonds", default=None,
                        help="EFRE/ESF/JTF (Anzeige-Wert).")
    parser.add_argument("--periode", default=None,
                        help="Foerderperiode wie 2021-2027.")
    parser.add_argument("--country-code", default=None,
                        help="ISO-2 Country-Code wie DE/AT.")
    parser.add_argument(
        "--field-mapping", default=None,
        help=(
            "Optional JSON-String oder Datei-Pfad. Mapping kanonischer "
            "Aliase auf Original-Header (z.B. "
            "'{\"name\": \"Name des Beguenstigten\", ...}'). "
            "Wenn nicht gesetzt, wird ueber COLUMN_PATTERNS heuristisch "
            "erkannt."
        ),
    )
    parser.add_argument(
        "--sheet", default=None,
        help="Sheet-Name oder 0-basierter Index.",
    )
    parser.add_argument(
        "--header-row", type=int, default=0,
        help="Header-Zeilen-Index (0-basiert). Bei 0 nutzt der Parser smart-Detection.",
    )
    mode_group = parser.add_mutually_exclusive_group(required=False)
    mode_group.add_argument(
        "--smart", dest="mode", action="store_const", const="smart",
        help="Default: ON CONFLICT DO NOTHING (idempotent).",
    )
    mode_group.add_argument(
        "--full-refresh", dest="mode", action="store_const", const="full-refresh",
        help="Bei Konflikt UPDATE.",
    )
    mode_group.add_argument(
        "--force", dest="mode", action="store_const", const="force",
        help="Pre-Delete der Quelle, danach reiner Insert.",
    )
    parser.add_argument("--verbose", action="store_true", help="DEBUG-Logging.")
    parser.set_defaults(mode="smart")
    return parser


def _load_field_mapping(value: str | None) -> dict[str, str] | None:
    """Akzeptiert entweder JSON-String oder Pfad zu einer JSON-Datei."""
    if not value:
        return None
    candidate = Path(value)
    if candidate.exists():
        with candidate.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    return json.loads(value)


def _parse_sheet(value: str | None) -> str | int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return value


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s  %(name)s  %(message)s",
    )
    log = logging.getLogger("harvest_beneficiaries")

    file_path: Path = args.file
    if not file_path.exists():
        log.error("Datei nicht gefunden: %s", file_path)
        return 2

    file_content = file_path.read_bytes()
    field_mapping = _load_field_mapping(args.field_mapping)

    params = BeneficiaryHarvestParams(
        source_key=args.source_key,
        bundesland=args.bundesland,
        fonds=args.fonds,
        periode=args.periode,
        country_code=args.country_code,
        file_content=file_content,
        file_name=file_path.name,
        field_mapping=field_mapping,
        sheet_name=_parse_sheet(args.sheet),
        header_row=args.header_row,
        mode=args.mode,
        triggered_by="cli",
    )

    log.info(
        "Beneficiary-Harvest gestartet: source=%s mode=%s file=%s",
        args.source_key, args.mode, file_path.name,
    )

    db = SessionLocal()
    try:
        result = run_beneficiary_harvest(db, params)
    finally:
        db.close()

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("status") in ("ok", "partial") else 2


if __name__ == "__main__":
    sys.exit(main())
