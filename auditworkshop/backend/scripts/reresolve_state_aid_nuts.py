"""
flowworkshop · scripts/reresolve_state_aid_nuts.py

Re-Resolve NUTS-Codes anhand vorhandener `nuts_label` mit der aktuellen
`derive_nuts_code`-Logik.

Default-Modus
-------------
Erfasst nur Records, deren NUTS-Aufloesung bisher Land-Level (0) oder NULL ist
und die ein nuts_label haben. Schreibt nur, wenn der neu abgeleitete Code
spezifischer ist als der bestehende (Level > alt).

`--upgrade`
-----------
Laeuft ueber alle Records mit nuts_label und schreibt jeden Treffer, dessen
neuer Code spezifischer (hoeheres Level) ist als der bestehende. Damit
profitieren auch AT-Records mit Level=2, fuer die wir mit dem neuen
NUTS-3-Lookup einen Bezirks-Code (Level=3) ableiten koennen.

Aufruf:
    docker exec auditworkshop-backend python scripts/reresolve_state_aid_nuts.py
    docker exec auditworkshop-backend python scripts/reresolve_state_aid_nuts.py --upgrade
    docker exec auditworkshop-backend python scripts/reresolve_state_aid_nuts.py --upgrade --dry --country AT
"""
from __future__ import annotations

import argparse
import logging
import sys

sys.path.insert(0, "/app")

from sqlalchemy import or_

from database import SessionLocal
from models.state_aid import StateAidAward
from services.state_aid_service import derive_nuts_code

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
log = logging.getLogger("reresolve_nuts")


def main() -> int:
    p = argparse.ArgumentParser(description="Re-Resolve NUTS-Codes anhand vorhandener nuts_label.")
    p.add_argument("--dry", action="store_true", help="Nur zaehlen, nichts schreiben.")
    p.add_argument("--country", help="Nur ein Land (z.B. DE).")
    p.add_argument("--batch", type=int, default=1000)
    p.add_argument(
        "--upgrade",
        action="store_true",
        help=(
            "Auch bestehende Aufloesungen aktualisieren, wenn der neue Code "
            "spezifischer ist (hoeheres nuts_level). Default: nur Level 0/NULL."
        ),
    )
    args = p.parse_args()

    db = SessionLocal()
    try:
        q = db.query(StateAidAward).filter(StateAidAward.nuts_label.isnot(None))
        if args.upgrade:
            log.info("Modus: --upgrade — alle Records mit nuts_label.")
        else:
            q = q.filter(
                or_(StateAidAward.nuts_level == 0, StateAidAward.nuts_level.is_(None))
            )
            log.info("Modus: nur Level 0/NULL.")
        if args.country:
            q = q.filter(StateAidAward.country_code == args.country.upper())

        total = q.count()
        log.info("Kandidaten: %d (country=%s)", total, args.country or "alle")

        changed = 0
        unchanged = 0
        seen = 0
        # Iteriere in Chunks
        last_id = None
        while True:
            chunk_q = q
            if last_id is not None:
                chunk_q = chunk_q.filter(StateAidAward.id > last_id)
            chunk = chunk_q.order_by(StateAidAward.id).limit(args.batch).all()
            if not chunk:
                break
            for a in chunk:
                seen += 1
                last_id = a.id
                new_code, new_level = derive_nuts_code(
                    region_label=a.nuts_label, country_iso2=a.country_code,
                )
                old_code = a.nuts_code or ""
                old_lvl = a.nuts_level or 0
                if (new_code or "") == old_code and (new_level or 0) == old_lvl:
                    unchanged += 1
                    continue
                # Nur wirklich verbessern (hoeheres Level als bisher)
                if (new_level or 0) > old_lvl:
                    if not args.dry:
                        a.nuts_code = new_code
                        a.nuts_level = new_level
                    changed += 1
                else:
                    unchanged += 1
            if not args.dry:
                db.commit()
            log.info("Verarbeitet %d/%d — bisher %d aktualisiert, %d unveraendert",
                     seen, total, changed, unchanged)

        log.info("Fertig: %d aktualisiert, %d unveraendert (dry=%s)", changed, unchanged, args.dry)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
