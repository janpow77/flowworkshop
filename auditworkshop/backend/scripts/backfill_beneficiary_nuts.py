"""
flowworkshop · scripts/backfill_beneficiary_nuts.py

Idempotenter Backfill der Spalte ``workshop_beneficiary_records.nuts_code``.

Hintergrund: Die Records aus den XLSX-Importen liefern in vielen Bundeslaendern
keinen NUTS-Code mit (NRW, Sachsen-Anhalt, Hessen, Thueringen, ...). Damit
Mode ``kreis_project_counts`` ueber ``services.dataframe_service`` Treffer
liefern kann, brauchen wir wenigstens einen NUTS-1-Code (Bundesland) — wo
moeglich einen NUTS-3-Code (Kreis), abgeleitet aus PLZ oder Ort.

Aufloesungsstrategie pro Record (erste Stufe gewinnt):

DE:
  1. NUTS-Code im ``location``-String (z.B. ``DE40B``, ``DEB11``).
  2. ``plz``-Spalte → ``lookup_plz`` → ``ort``/``bundesland`` → NUTS-3 via
     ``load_nuts3_de_lookup`` (z.B. ``60311`` → Frankfurt am Main → ``DE712``).
  3. ``location``-String per ``derive_nuts_code`` (Stadt/Kreis-Match).
  4. ``bundesland`` → NUTS-1 via ``DE_REGION_TO_NUTS1`` (Fallback).

AT:
  1. ``plz`` → ``lookup_plz`` → ``bundesland`` → NUTS-2 via ``AT_REGION_TO_NUTS2``.
  2. ``location``/``bundesland`` per ``derive_nuts_code``.
  3. ``bundesland`` → NUTS-2.

Verwendung:
    docker exec auditworkshop-backend python scripts/backfill_beneficiary_nuts.py [--dry] [--limit N]

Das Skript ist idempotent: Records mit bereits gefuelltem ``nuts_code`` bleiben
unangetastet. Bei wiederholten Laeufen werden nur neue NULL-Records bearbeitet.
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
import time
from pathlib import Path

# Fuer den Container-Run: backend/ ins sys.path haengen, sonst greift der
# CLI-Aufruf nicht auf die ``services``-Module zu.
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import text  # noqa: E402

from database import engine  # noqa: E402
from services.geocoding_service import lookup_plz  # noqa: E402
from services.state_aid_service import (  # noqa: E402
    AT_REGION_TO_NUTS2,
    DE_REGION_TO_NUTS1,
    derive_nuts_code,
    load_nuts3_de_lookup,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s  %(name)s  %(message)s",
)
log = logging.getLogger("backfill_nuts")


# Regex fuer NUTS-Codes innerhalb des location-Strings (z.B. "DE40B Frankfurt").
# Anker: muss am String-Anfang stehen ODER nach einem Trenner (Whitespace,
# Komma, Doppelpunkt, Klammer, Pipe). Ohne den Anker matcht "DER" innerhalb
# von "Brandenburg an DER Havel" oder "AUF DER Höhe".
_NUTS_PATTERN = re.compile(
    r"(?:^|[\s,;:/|()\[\]\-])((?:DE|AT)[0-9][0-9A-Z]{0,3})(?=[\s,;:/|()\[\]\-]|$)"
)
# 4-5-stellige PLZ irgendwo im String (Excel haengt manchmal ".0" an).
_PLZ_PATTERN = re.compile(r"\b(\d{4,5})\b")


def _strip_plz_float(value: str | None) -> str | None:
    """Excel-Float-PLZs ('37351.0') auf den Integer-Teil reduzieren."""
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    m = re.match(r"^(\d{4,5})(?:\.0+)?$", s)
    if m:
        return m.group(1)
    return s


def _bundesland_to_nuts1_de(bundesland: str | None) -> str | None:
    """DE-Bundesland → NUTS-1. Akzeptiert Originalschreibweise und Aliasse."""
    if not bundesland:
        return None
    key = bundesland.strip().lower()
    return DE_REGION_TO_NUTS1.get(key)


def _bundesland_to_nuts2_at(bundesland: str | None) -> str | None:
    """AT-Bundesland → NUTS-2."""
    if not bundesland:
        return None
    key = bundesland.strip().lower()
    return AT_REGION_TO_NUTS2.get(key)


def _resolve_nuts(record: dict) -> str | None:
    """Ermittelt einen NUTS-Code (NUTS-3 wenn moeglich) fuer einen Record.

    Gibt entweder einen NUTS-3/2/1-Code oder ``None`` zurueck. Auf
    ``None`` faellt der Aufrufer zurueck — er kann das Feld dann auf
    Bundesland-Ebene befuellen.
    """
    cc = (record.get("country_code") or "").strip().upper() or "DE"
    location = (record.get("location") or "").strip()
    plz = _strip_plz_float(record.get("plz"))
    bundesland = (record.get("bundesland") or "").strip() or None

    # 1. Direkter NUTS-Code im location-String (z.B. Brandenburg ESF "DE40B").
    # Wir akzeptieren nur Codes, die zum country_code passen — sonst wuerde
    # eine Zeile mit Standort "AT13" im DE-Ordner als AT13 gemerkt, was die
    # Choropleth-Aggregation pro Land verfaelscht.
    if location:
        for m in _NUTS_PATTERN.finditer(location.upper()):
            candidate = m.group(1)
            if cc == "DE" and candidate.startswith("DE"):
                return candidate
            if cc == "AT" and candidate.startswith("AT"):
                return candidate

    # 2. PLZ-Pfad: PLZ → Ort+Bundesland → NUTS-3-Lookup ueber Kreis-Name.
    # Wenn kein separates PLZ-Feld vorhanden ist, fischen wir die fuehrende
    # PLZ aus dem location-String (z.B. AT: "9020 Klagenfurt,..." → "9020").
    if not plz and location:
        m_plz = _PLZ_PATTERN.search(location)
        if m_plz:
            plz = m_plz.group(1)
    if plz:
        plz_hit = lookup_plz(plz, country_code=cc)
        if plz_hit:
            ort = (plz_hit.get("ort") or "").strip().lower()
            bl_from_plz = (plz_hit.get("bundesland") or "").strip()
            if cc == "DE":
                nuts3_lookup = load_nuts3_de_lookup()
                # 2a) Direkter Ortsname-Treffer (z.B. "Frankfurt am Main" → DE712)
                if ort and ort in nuts3_lookup:
                    return nuts3_lookup[ort]
                # 2b) Kreis-Variante "Stadt, Stadtkreis" probiert derive_nuts_code
                if ort:
                    code, _level = derive_nuts_code(
                        region_label=ort, country_iso2="DE",
                    )
                    # Codes von Laenge >= 3 akzeptieren — derive faellt auf
                    # "DE" (Land) zurueck wenn nichts matcht. Wir behalten
                    # NUTS-1 als Fallback nur, wenn mindestens das Bundesland
                    # rauskommt.
                    if code and len(code) >= 3:
                        return code
                # 2c) Bundesland aus PLZ → NUTS-1
                nuts1 = _bundesland_to_nuts1_de(bl_from_plz)
                if nuts1:
                    return nuts1
            elif cc == "AT":
                # AT: PLZ-DB hat ueberwiegend kein NUTS-3, daher Bundesland.
                nuts2 = _bundesland_to_nuts2_at(bl_from_plz)
                if nuts2:
                    return nuts2

    # 3. location-String → derive_nuts_code (Kreis-/Stadtname matchen).
    if location:
        # Komma- oder Bindestrich-Aufteilung: "Berlin, Mitte" → "Berlin".
        head = re.split(r"[,/(]", location)[0].strip()
        if head:
            code, _level = derive_nuts_code(region_label=head, country_iso2=cc)
            # Nur akzeptieren, wenn der Code zum erwarteten Land gehoert —
            # `derive_nuts_code` erkennt direkt "AT13" als gueltigen Code,
            # auch wenn country_iso2='DE' uebergeben wurde.
            if code and code != cc and len(code) >= 3 and code.startswith(cc):
                return code

    # 4. Letzter Fallback: Bundesland → NUTS-1/2.
    if cc == "DE":
        return _bundesland_to_nuts1_de(bundesland)
    if cc == "AT":
        return _bundesland_to_nuts2_at(bundesland)

    return None


def _select_batch(conn, batch_size: int, last_id: int) -> list[dict]:
    """Holt eine Batch von Records mit fehlendem nuts_code, id-paginiert."""
    sql = text(
        """
        SELECT id, country_code, bundesland, location, plz
        FROM workshop_beneficiary_records
        WHERE (nuts_code IS NULL OR nuts_code = '')
          AND id > :last_id
        ORDER BY id ASC
        LIMIT :batch_size
        """
    )
    rows = conn.execute(sql, {"last_id": last_id, "batch_size": batch_size}).fetchall()
    return [dict(r._mapping) for r in rows]


def run(*, dry: bool, limit: int | None, batch_size: int = 1000) -> None:
    """Hauptloop — paginiert ueber alle Records mit fehlendem nuts_code."""
    last_id = 0
    total_seen = 0
    total_updated = 0
    total_skipped = 0
    started = time.time()

    while True:
        with engine.connect() as conn:
            batch = _select_batch(conn, batch_size, last_id)
        if not batch:
            break

        updates: list[tuple[int, str]] = []
        for record in batch:
            total_seen += 1
            last_id = max(last_id, int(record["id"]))
            nuts_code = _resolve_nuts(record)
            if nuts_code:
                updates.append((int(record["id"]), nuts_code))
            else:
                total_skipped += 1
            if limit is not None and total_seen >= limit:
                break

        if updates and not dry:
            with engine.begin() as conn:
                # Bulk-Update via VALUES-Liste — ein Roundtrip pro Batch.
                values_sql = ", ".join(
                    f"({rec_id}, :nuts_{idx})"
                    for idx, (rec_id, _) in enumerate(updates)
                )
                params = {f"nuts_{idx}": code for idx, (_, code) in enumerate(updates)}
                conn.execute(
                    text(
                        f"""
                        UPDATE workshop_beneficiary_records AS w
                        SET nuts_code = v.nuts,
                            updated_at = NOW()
                        FROM (VALUES {values_sql}) AS v(id, nuts)
                        WHERE w.id = v.id
                        """
                    ),
                    params,
                )
        total_updated += len(updates)

        if total_seen % 1000 == 0 or (limit is not None and total_seen >= limit):
            elapsed = time.time() - started
            log.info(
                "Fortschritt: gesehen=%d, aktualisiert=%d, ohne_match=%d, "
                "letzte_id=%d, %.1fs",
                total_seen, total_updated, total_skipped, last_id, elapsed,
            )

        if limit is not None and total_seen >= limit:
            break

    elapsed = time.time() - started
    log.info(
        "Fertig: gesehen=%d, aktualisiert=%d, ohne_match=%d, dauer=%.1fs%s",
        total_seen, total_updated, total_skipped, elapsed,
        " (DRY-RUN, keine Schreiboperationen)" if dry else "",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill der NUTS-Codes in workshop_beneficiary_records.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximal N Records bearbeiten (Default: alle).",
    )
    parser.add_argument(
        "--dry",
        action="store_true",
        help="Nur Treffer simulieren, keine UPDATEs ausfuehren.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Batch-Groesse fuer Pagination + Bulk-UPDATE (Default 1000).",
    )
    args = parser.parse_args()
    run(dry=args.dry, limit=args.limit, batch_size=args.batch_size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
