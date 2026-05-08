"""
flowworkshop · scripts/renormalize_state_aid_names.py

Aktualisiert `beneficiary_name_normalized` in workshop_state_aid_awards mit der
aktuellen `normalize_company_name`-Logik. Notwendig nach Aenderungen am
Normalisierer (z.B. Hyphen-Handling-Fix fuer Fraunhofer-Gesellschaft).

Aufruf:
    docker exec auditworkshop-backend python scripts/renormalize_state_aid_names.py
    docker exec auditworkshop-backend python scripts/renormalize_state_aid_names.py --dry --country DE
"""
from __future__ import annotations

import argparse
import logging
import sys

sys.path.insert(0, "/app")

from database import SessionLocal
from models.state_aid import StateAidAward
from services.state_aid_service import normalize_company_name

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
log = logging.getLogger("renormalize_names")


def main() -> int:
    p = argparse.ArgumentParser(description="Re-Normalize beneficiary_name_normalized.")
    p.add_argument("--dry", action="store_true")
    p.add_argument("--country", help="Nur ein Land (DE/AT).")
    p.add_argument("--batch", type=int, default=2000)
    args = p.parse_args()

    db = SessionLocal()
    try:
        q = db.query(StateAidAward)
        if args.country:
            q = q.filter(StateAidAward.country_code == args.country.upper())

        total = q.count()
        log.info("Records: %d (country=%s)", total, args.country or "alle")

        changed = 0
        unchanged = 0
        seen = 0
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
                new_norm = normalize_company_name(a.beneficiary_name)
                if new_norm == (a.beneficiary_name_normalized or ""):
                    unchanged += 1
                    continue
                if not args.dry:
                    a.beneficiary_name_normalized = new_norm
                changed += 1
            if not args.dry:
                db.commit()
            if seen % (args.batch * 5) == 0 or seen == total:
                log.info("Verarbeitet %d/%d — %d aktualisiert", seen, total, changed)

        log.info("Fertig: %d aktualisiert, %d unveraendert (dry=%s)", changed, unchanged, args.dry)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
