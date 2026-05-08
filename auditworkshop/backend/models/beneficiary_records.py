"""
flowworkshop · models/beneficiary_records.py

Phase 6a: Zentrale Beneficiary-Tabelle mit kanonischem Schema.
Statt der bisher ~36 per-Bundesland-Tabellen (workshop_df_<bundesland>_<fonds>_<periode>)
fuehren wir hier eine einheitliche Tabelle workshop_beneficiary_records mit
- kanonischen Spalten (beneficiary_name, project_name, ...),
- Original-`*_raw`-Strings (Originalwerte unveraendert),
- raw_payload (JSONB, gesamte Original-Zeile zur Rueckverfolgung) und
- (source_key, source_record_id) als UNIQUE-Constraint fuer Smart-Mode-
  Idempotenz analog `models.state_aid.StateAidAward`.

Die Tabelle wird von `services.beneficiary_harvester` beschrieben und von
`services.dataframe_service.search_beneficiary_records` gelesen.
"""
from sqlalchemy import (
    Column, String, Text, Integer, BigInteger, DateTime,
    Numeric, Date, Float, Index, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB

from database import Base


class BeneficiaryRecord(Base):
    """Phase 6a §1 — kanonisches Beneficiary-Schema.

    Pro XLSX-Zeile genau ein Datensatz. Idempotent ueber
    UNIQUE(source_key, source_record_id). Original-Strings werden in den
    `*_raw`-Feldern gespeichert; parsed-Helper koennen NULL sein, wenn
    parse_amount/parse_date am Original-String scheitern.
    """

    __tablename__ = "workshop_beneficiary_records"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source_key = Column(String(120), nullable=False, index=True)
    source_record_id = Column(String(64), nullable=False, index=True)
    upload_run_id = Column(String(36), nullable=True, index=True)

    # Ursprung der Zeile — Audit-Spur in die Original-Datei.
    source_filename = Column(String(255), nullable=True)
    source_sheet = Column(String(80), nullable=True)
    source_row_number = Column(Integer, nullable=True)

    # Kanonisches Schema — Original-Strings unveraendert.
    beneficiary_name = Column(Text, nullable=False)
    beneficiary_name_normalized = Column(Text, nullable=False, index=True)

    project_name = Column(Text, nullable=True)
    project_aktenzeichen = Column(String(120), nullable=True)
    project_description = Column(Text, nullable=True)

    # Geo
    bundesland = Column(String(80), nullable=True, index=True)
    fonds = Column(String(40), nullable=True, index=True)         # EFRE/ESF/JTF
    periode = Column(String(20), nullable=True)
    country_code = Column(String(3), nullable=True, index=True)
    location = Column(Text, nullable=True)
    landkreis = Column(String(120), nullable=True)
    plz = Column(String(10), nullable=True)
    nuts_code = Column(String(20), nullable=True, index=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    # Betraege — Original-String UND parsed Helper
    cost_total_raw = Column(String(80), nullable=True)
    cost_total = Column(Numeric(18, 2), nullable=True, index=True)
    cost_eu_funding_raw = Column(String(80), nullable=True)
    cost_eu_funding = Column(Numeric(18, 2), nullable=True)
    currency = Column(String(8), nullable=True)

    # Daten — Original UND parsed Helper
    project_start_raw = Column(String(40), nullable=True)
    project_start = Column(Date, nullable=True)
    project_end_raw = Column(String(40), nullable=True)
    project_end = Column(Date, nullable=True)
    funded_at_raw = Column(String(40), nullable=True)
    funded_at = Column(Date, nullable=True, index=True)

    # Original-Row als JSONB — 100 % Rueckverfolgbarkeit zur Quell-Zeile.
    raw_payload = Column(JSONB, nullable=False)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint(
            "source_key", "source_record_id",
            name="uq_beneficiary_source_record",
        ),
        Index("ix_beneficiary_country_bundesland", "country_code", "bundesland"),
        Index("ix_beneficiary_search", "beneficiary_name_normalized"),
    )


class BeneficiaryHarvestRun(Base):
    """Phase 6a §2 — Lauf-Logs des Beneficiary-Harvesters.

    Aufbau analog ``models.state_aid.StateAidHarvestRun``: jede Smart-Mode-
    Iteration (XLSX-Upload, Refresh, etc.) erzeugt einen Run-Eintrag mit
    Insert-/Skip-/Failed-Counter sowie einer JSONB-`parameters`-Spur.
    """

    __tablename__ = "workshop_beneficiary_harvest_runs"

    id = Column(String(36), primary_key=True)
    source_key = Column(String(120), nullable=False, index=True)
    started_at = Column(DateTime, server_default=func.now(), index=True)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(16), nullable=False, server_default="running")
    # 'running' | 'ok' | 'partial' | 'failed' | 'check_only'

    records_seen = Column(Integer, server_default="0")
    records_inserted = Column(Integer, server_default="0")
    records_skipped = Column(Integer, server_default="0")
    records_failed = Column(Integer, server_default="0")

    error_message = Column(Text, nullable=True)
    triggered_by = Column(String(80), nullable=False)  # 'cli' | 'admin:<uid>' | 'upload'

    parameters = Column(JSONB, nullable=True)
    # Eingabeparameter des Laufs (mode, source_key, bundesland, fonds, ...)
