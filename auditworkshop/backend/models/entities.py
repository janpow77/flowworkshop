"""
flowworkshop · models/entities.py

Phase 6d — Entity-Resolution: kanonische Master-Tabelle, die State-Aid +
Beneficiaries + Sanctions auf eine Firma/Person verlinkt.

Architektur (additive Schicht):
- ``CompanyEntity``: Master-Eintrag pro Firma/Person. Keine Original-Daten,
  sondern Aggregat aus den drei Quell-Tabellen plus GLEIF/Wikidata-Hierarchie.
- ``EntityMatch``: n:1-Beziehung. Verbindet einen Original-Record (State-Aid
  Award / BeneficiaryRecord / SanctionsEntry) mit genau einer CompanyEntity.

Kein Schreibvorgang in den Original-Tabellen. Eine Quell-Zeile kann
genau einer Entity zugeordnet sein (UNIQUE auf source_module +
source_record_id), aber eine Entity hat in der Regel viele Matches.

Idempotenz: Rebuild-Skripte koennen jederzeit erneut laufen — bestehende
Matches werden nicht dupliziert (UNIQUE-Constraint).

Confidence-Klassen (siehe ``services.entity_resolution``):
- 100  LEI-Match
- 95   Identifier-Match (HRB, Steuer-Nr.)
- 90   Name-Exact (nach Normalisierung)
- 75-89  Fuzzy-Score (rapidfuzz token_set_ratio/WRatio)
- < 75  KEIN Match angelegt — zu unsicher
"""
from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Float, ForeignKey, Index,
    String, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB

from database import Base


class CompanyEntity(Base):
    """Master-Eintrag pro Firma/Person — additive Schicht.

    Original-Daten in den Quell-Tabellen (workshop_state_aid_awards,
    workshop_beneficiary_records, workshop_sanctions_entries) bleiben
    unveraendert. Diese Tabelle ist jederzeit rebuildbar.

    Felder:
    - ``canonical_name`` / ``canonical_name_normalized``: kanonische Bezeichner
      und vergleichsfertige Form (siehe ``state_aid_service.normalize_company_name``).
    - ``entity_type``: 'company' | 'person' — derzeit unterscheiden wir nur
      grob; Sanctions kann auch Personen liefern, die anderen Quellen sind
      Firmen.
    - ``lei``: GLEIF Legal Entity Identifier — wenn vorhanden, ist das der
      verbindlichste Identifier (UNIQUE).
    - ``identifiers``: JSONB mit allen bekannten nationalen Identifiern, z.B.
      ``{"hrb": ["HRB 12345 Berlin"], "ust_id": "DE123456789", ...}``.
    - ``addresses``: JSONB-Liste, jeder Eintrag mit ``{city, postal_code,
      street, country, source}``.
    - ``parent_entity_id`` / ``ultimate_parent_entity_id``: Konzernhierarchie
      ueber GLEIF/Wikidata. Self-FK auf dieselbe Tabelle.
    - ``first_match_method``: wie wurde diese Entity zum ersten Mal angelegt
      (z.B. 'lei', 'identifier', 'name_exact', 'name_fuzzy').
    """

    __tablename__ = "workshop_company_entities"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    canonical_name = Column(String(500), nullable=False, index=True)
    canonical_name_normalized = Column(String(500), nullable=False, index=True)
    entity_type = Column(String(20), nullable=False)  # 'company' | 'person'
    country_code = Column(String(3), nullable=True, index=True)

    # Identifier (alle bekannten)
    lei = Column(String(20), nullable=True, unique=True)
    identifiers = Column(JSONB, nullable=True)

    addresses = Column(JSONB, nullable=True)

    # Konzernhierarchie (von GLEIF/Wikidata)
    parent_entity_id = Column(
        BigInteger,
        ForeignKey("workshop_company_entities.id"),
        nullable=True,
        index=True,
    )
    ultimate_parent_entity_id = Column(
        BigInteger,
        ForeignKey("workshop_company_entities.id"),
        nullable=True,
    )

    # Provenance
    first_match_method = Column(String(40), nullable=True)
    discovered_at = Column(DateTime, server_default=func.now())
    last_seen_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(),
    )

    __table_args__ = (
        # Trigram-Index wird im Lifespan separat angelegt, damit GIN
        # gin_trgm_ops genutzt werden kann (SQLAlchemy bekommt USING-Klausel
        # nicht direkt mit). Hier nur der reguelaere BTree-Index.
        Index(
            "ix_company_entity_name_norm",
            "canonical_name_normalized",
        ),
    )


class EntityMatch(Base):
    """Verbindung zwischen Original-Record und CompanyEntity.

    Eine n:1-Beziehung — ein Original-Record kann genau einer Entity zugeordnet
    sein (UNIQUE auf ``source_module`` + ``source_record_id``); eine Entity
    hat ueblicherweise viele Matches (mehrere State-Aid-Awards, mehrere
    Beneficiary-Eintraege, ein Sanctions-Eintrag).

    Der Pruefer kann ein Match manuell bestaetigen (``confirmed_by_user_id``
    + ``confirmed_at``) oder als falsch markieren (``rejected = True``).
    Rejected-Matches bleiben in der Tabelle (Audit-Trail), werden aber im
    Audit-Report gefiltert.
    """

    __tablename__ = "workshop_entity_matches"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    entity_id = Column(
        BigInteger,
        ForeignKey("workshop_company_entities.id"),
        nullable=False,
        index=True,
    )

    # Quell-Identifikation
    source_module = Column(String(20), nullable=False, index=True)
    # 'state_aid' | 'beneficiary' | 'sanctions'
    source_record_id = Column(String(64), nullable=False, index=True)
    source_table = Column(String(40), nullable=False)
    # tatsaechlicher Tabellenname zur Rueckverfolgung
    # ('workshop_state_aid_awards' / 'workshop_beneficiary_records' /
    #  'workshop_sanctions_entries')

    # Match-Provenance
    match_method = Column(String(40), nullable=False)
    # 'lei' | 'identifier' | 'name_exact' | 'name_fuzzy_<score>'
    match_confidence = Column(Float, nullable=False)  # 0.0..100.0
    match_evidence = Column(JSONB, nullable=False)
    # was passte? z.B. {"lei": "...", "name_in_record": "..."}

    # Pruefer-Workflow
    confirmed_by_user_id = Column(String(36), nullable=True)
    rejected = Column(Boolean, server_default="false", nullable=False)
    confirmed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "source_module", "source_record_id",
            name="uq_entity_match_source",
        ),
        Index(
            "ix_entity_match_module_table",
            "source_module", "source_table",
        ),
    )
