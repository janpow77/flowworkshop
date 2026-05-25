"""
flowworkshop · models/state_aid.py
EU-Beihilfe-Transparenzregister (Plan: docs/eu-state-aid-register-plan.md §5).
"""
from sqlalchemy import (
    Column, String, Text, Integer, Boolean, DateTime,
    Numeric, JSON, Date, Index, UniqueConstraint, func,
)
import uuid

from database import Base


class StateAidHarvestRun(Base):
    """Plan §5.1 — Lauf-Logs des Harvesters."""

    __tablename__ = "workshop_state_aid_harvest_runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_key = Column(String(60), nullable=False, index=True)
    source_url = Column(String(500), nullable=True)
    started_at = Column(DateTime, server_default=func.now(), index=True)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(16), nullable=False, server_default="running")
    # 'running' | 'ok' | 'partial' | 'failed' | 'check_only'

    records_seen = Column(Integer, server_default="0")
    records_inserted = Column(Integer, server_default="0")
    records_updated = Column(Integer, server_default="0")
    records_failed = Column(Integer, server_default="0")
    # Smart-Mode (Plan §11): Anzahl Datensaetze, die bereits vorhanden waren
    # und unveraendert uebersprungen wurden (ON CONFLICT DO NOTHING).
    records_skipped = Column(Integer, server_default="0")

    error_message = Column(Text, nullable=True)
    triggered_by = Column(String(80), nullable=False)  # 'cli' | 'admin:<uid>' | 'cron'
    source_version = Column(String(80), nullable=True)
    source_last_modified = Column(DateTime, nullable=True)

    parameters = Column(JSON, nullable=True)
    # Eingabeparameter des Laufs (country, region, since, limit, ...)


class StateAidAward(Base):
    """Plan §5.2 — Normalisierter Beihilfe-Award."""

    __tablename__ = "workshop_state_aid_awards"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_key = Column(String(60), nullable=False, index=True)
    source_record_id = Column(String(120), nullable=False, index=True)
    source_url = Column(String(500), nullable=True)
    harvest_run_id = Column(String(36), nullable=True, index=True)

    # Beguenstigter
    beneficiary_name = Column(String(500), nullable=False)
    beneficiary_name_normalized = Column(String(500), nullable=False, index=True)
    beneficiary_identifier = Column(String(200), nullable=True, index=True)
    beneficiary_type = Column(String(120), nullable=True)

    # Geo
    country_code = Column(String(3), nullable=True, index=True)
    country_name = Column(String(80), nullable=True)
    nuts_code = Column(String(20), nullable=True, index=True)
    nuts_label = Column(String(160), nullable=True)
    nuts_level = Column(Integer, nullable=True)

    # Sektor
    nace_code = Column(String(10), nullable=True)
    nace_label = Column(String(240), nullable=True)

    # Betrag
    aid_amount = Column(Numeric(18, 2), nullable=True)
    aid_currency = Column(String(8), nullable=True)
    aid_amount_eur = Column(Numeric(18, 2), nullable=True, index=True)
    aid_nominal_amount = Column(Numeric(18, 2), nullable=True)

    # Massnahme
    aid_instrument = Column(String(240), nullable=True)
    aid_objective = Column(Text, nullable=True)
    aid_measure_title = Column(Text, nullable=True)

    granting_authority = Column(String(300), nullable=True)
    entrusted_entity = Column(String(300), nullable=True)
    financial_intermediaries = Column(String(300), nullable=True)

    # Daten
    granting_date = Column(Date, nullable=True, index=True)
    publication_date = Column(Date, nullable=True)

    # KOM-Faelle
    measure_reference = Column(String(60), nullable=True)
    sa_reference = Column(String(40), nullable=True, index=True)
    case_url = Column(String(500), nullable=True)
    decision_url = Column(String(500), nullable=True)

    raw_payload = Column(JSON, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("source_key", "source_record_id", name="uq_state_aid_source_record"),
        Index("ix_state_aid_search", "beneficiary_name_normalized", "country_code"),
        Index("ix_state_aid_country_date", "country_code", "granting_date"),
        # Phase-3-Hardening: Prefix-Match auf nuts_code wird per B-Tree
        # effizient (`nuts_code LIKE 'DE2%'`). Composite-Index country+nuts
        # beschleunigt die typische Suche "alle Awards in Bayern".
        Index("ix_state_aid_nuts_prefix", "nuts_code"),
        Index("ix_state_aid_country_nuts", "country_code", "nuts_code"),
    )


class StateAidSource(Base):
    """Plan §5.3 — Quellenstatus (TAM, nationale Register, Manuell)."""

    __tablename__ = "workshop_state_aid_sources"

    source_key = Column(String(60), primary_key=True)
    display_name = Column(String(200), nullable=False)
    source_type = Column(String(20), nullable=False)
    # 'tam' | 'national' | 'cases' | 'manual'

    country_code = Column(String(3), nullable=True, index=True)
    base_url = Column(String(500), nullable=True)
    last_successful_harvest_at = Column(DateTime, nullable=True)
    last_record_date = Column(Date, nullable=True)
    record_count = Column(Integer, server_default="0")
    coverage_note = Column(Text, nullable=True)
    quality = Column(String(8), nullable=True)
    # 'green' | 'yellow' | 'red'
    enabled = Column(Boolean, server_default="true")

    # Coverage-Erweiterung (Mai 2026, Item 5): Wir cachen die Gesamtzahl der
    # Datensaetze, die die externe Quelle (z.B. TAM) zum Zeitpunkt des letzten
    # Harvests zurueckgemeldet hat. Damit koennen wir den Coverage-Score
    # `lokal / expected * 100` ausweisen — ohne dass jeder Audit-Report-Aufruf
    # das externe Register erneut abfragt. Optional, weil nicht jede Quelle
    # eine Total-Zahl liefert.
    expected_total = Column(Integer, nullable=True)
    expected_total_updated_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
