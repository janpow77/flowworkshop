#!/usr/bin/env python3
"""Setzt die Begünstigten-Quellen zurück auf manual_upload (Not-Aus).

Hintergrund: das produktive Backend harvestet im Snapshot-Modus, der
bestehende Datensaetze vor dem Import loescht. Bis der Modus geklaert ist,
darf der naechtliche Auto-Harvest keine Quelle mehr anfassen.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import SessionLocal
from models.beneficiary_sources_config import BeneficiarySourceConfig

db = SessionLocal()
try:
    rows = (
        db.query(BeneficiarySourceConfig)
        .filter(BeneficiarySourceConfig.source_type.in_(("xlsx_url", "csv_url")))
        .all()
    )
    for cfg in rows:
        cfg.source_type = "manual_upload"
    db.commit()
    print(f"{len(rows)} Quellen auf manual_upload zurueckgesetzt.")

    from collections import Counter
    verteilung = Counter(
        c.source_type for c in db.query(BeneficiarySourceConfig).all()
    )
    print("Verteilung jetzt:", dict(verteilung))
finally:
    db.close()
