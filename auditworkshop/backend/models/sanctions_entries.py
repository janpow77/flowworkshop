"""
flowworkshop · models/sanctions_entries.py

Phase 6c — Schema-Normalisierung der Sanktionslisten.

Eine Tabelle ``workshop_sanctions_entries`` haelt alle Eintraege aller
aktivierten Sanktionsquellen (eu_fsf, un_sc, us_ofac_sdn, gb_hmt_sanctions,
ch_seco). Original-Werte werden VERBATIM gespeichert; nur das
Such-Hilfsfeld ``name_normalized`` traegt die normalisierte Vergleichsform
(siehe ``services/sanctions_service.normalize_name``).

Diese Tabelle ist Source-of-Truth fuer die Persistierung. Die rapidfuzz-
Suche selbst laeuft weiterhin gegen einen In-Memory-Index, der bei jedem
Refresh aus der DB neu aufgebaut wird (siehe ``MultiSanctionsService``).

Relation zu ``SanctionsRefreshRun``: Jeder Eintrag, der im Rahmen eines
Refreshes neu aufgenommen oder aktualisiert wird, traegt die
``refresh_run_id`` des Laufs — damit ist ueber die Audit-Tabelle
nachvollziehbar, in welchem Lauf welcher Eintrag dazu kam.
"""
from sqlalchemy import (
    BigInteger, Column, DateTime, Index, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB

from database import Base


class SanctionsEntry(Base):
    """Ein Eintrag aus einer beliebigen Sanctions-CSV (OpenSanctions-Schema).

    Kanonisches Schema: alle Felder, die OpenSanctions im
    ``targets.simple.csv`` liefert, plus ``raw_payload`` mit der vollstaendigen
    CSV-Zeile als JSON. Original-Strings werden NICHT veraendert — nur
    ``name_normalized`` wird per ``normalize_name()`` befuellt, damit
    Postgres-seitige Helfer-Indizes (pg_trgm, ILIKE) funktionieren.
    """

    __tablename__ = "workshop_sanctions_entries"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # Quelle + Eintrags-ID — Unique zusammen
    source_key = Column(String(40), nullable=False, index=True)
    entry_id = Column(String(120), nullable=False, index=True)
    schema = Column(String(40), nullable=False, index=True)

    # Kanonisches Schema — Original-Strings verbatim
    name = Column(Text, nullable=False, index=True)
    name_normalized = Column(Text, nullable=False, index=True)
    aliases = Column(JSONB, nullable=True)

    # Original-Felder verbatim — daher Text statt VARCHAR(N), weil
    # OpenSanctions ``birth_date``/``first_seen``/``last_seen`` als
    # semikolongetrennte Mehrfach-Werte liefern kann (mehrere Geburtsdaten
    # bei einer Person, etc.).
    birth_date = Column(Text, nullable=True)
    countries = Column(Text, nullable=True)
    addresses = Column(Text, nullable=True)
    identifiers = Column(Text, nullable=True)
    sanctions_program = Column(Text, nullable=True)
    program_ids = Column(Text, nullable=True)

    first_seen = Column(Text, nullable=True)
    last_seen = Column(Text, nullable=True)

    # Vollstaendige CSV-Zeile als JSON (Audit + Recovery)
    raw_payload = Column(JSONB, nullable=False)

    # Audit-Spur: welcher Refresh-Lauf hat diesen Eintrag aufgenommen/aktualisiert.
    refresh_run_id = Column(BigInteger, nullable=True, index=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "source_key", "entry_id", name="uq_sanctions_source_entry",
        ),
        Index("ix_sanctions_search", "name_normalized"),
        Index("ix_sanctions_schema_source", "source_key", "schema"),
    )
