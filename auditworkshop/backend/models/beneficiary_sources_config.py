"""
flowworkshop · models/beneficiary_sources_config.py

Phase 6b — Datengetriebene Worker-Pipeline fuer Beneficiaries.

Eine zentrale Konfigurationstabelle, in der pro Begueenstigtenverzeichnis-
Quelle steht: URL, Field-Mapping, Validierungen, Update-Frequenz. Der
Worker liest sie und macht den Smart-Mode-Harvest datengetrieben — keine
Code-Aenderung mehr noetig, wenn ein neues Bundesland dazukommt.

Pattern analog zu ``models.state_aid.StateAidSource``, aber mit zusaetz-
lichen Feldern fuer XLSX-/CSV-Konfiguration: ``field_mapping``,
``required_fields``, ``validations``, ``last_seen_sha256`` (Inhalts-Hash
der letzten gesehenen Datei — verhindert unnoetige Re-Harvests).
"""
from sqlalchemy import (
    Boolean, Column, DateTime, Integer, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB

from database import Base


class BeneficiarySourceConfig(Base):
    """Phase 6b §1 — datengetriebene Quellen-Konfiguration.

    Pro Quelle ein Eintrag mit allem, was der Worker fuer einen
    Smart-Mode-Harvest braucht. Das ``field_mapping`` und die
    ``validations`` sind JSONB, damit das Admin-UI sie ohne
    Schema-Migration erweitern kann.

    Der Worker pflegt die Status-Felder (``last_successful_harvest_at``,
    ``record_count``, ``quality``, ``last_seen_sha256``) — die Config-
    Felder werden vom Admin-UI geschrieben.
    """

    __tablename__ = "workshop_beneficiary_sources_config"

    source_key = Column(String(120), primary_key=True)
    display_name = Column(String(200), nullable=False)
    bundesland = Column(String(80), nullable=True)
    fonds = Column(String(40), nullable=True)
    periode = Column(String(20), nullable=True)
    country_code = Column(String(3), nullable=True, index=True)

    # Quelle
    source_type = Column(String(20), nullable=False)  # 'xlsx_url' | 'csv_url' | 'manual_upload'
    source_url = Column(String(500), nullable=True)
    source_landing_page = Column(String(500), nullable=True)
    update_frequency_days = Column(Integer, nullable=True)
    license = Column(String(120), nullable=True)

    # Harvest-Config
    sheet_name = Column(String(80), nullable=True)
    header_row = Column(Integer, server_default="0")
    field_mapping = Column(JSONB, nullable=True)        # {"beneficiary_name": "Beguenstigter", ...}
    required_fields = Column(JSONB, nullable=True)      # ["beneficiary_name", "cost_total"]
    validations = Column(JSONB, nullable=True)          # [{"field": "...", "regex": "..."}]

    # Status (vom Worker gepflegt)
    enabled = Column(Boolean, server_default="true")
    last_successful_harvest_at = Column(DateTime, nullable=True)
    last_harvest_run_id = Column(String(36), nullable=True)
    last_seen_sha256 = Column(String(64), nullable=True)   # Inhalts-Hash der zuletzt gesehenen Datei
    record_count = Column(Integer, server_default="0")
    quality = Column(String(8), nullable=True)             # 'green' | 'yellow' | 'red'
    coverage_note = Column(Text, nullable=True)
    notes_for_pruefer = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
