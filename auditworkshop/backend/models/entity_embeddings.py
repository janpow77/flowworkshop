"""
flowworkshop · models/entity_embeddings.py

Layer A — Universeller Embedding-Index (bge-m3) ueber alle drei Module
(state_aid | beneficiary | sanctions | company_entity).

Eine zusaetzliche, ADDITIVE Schicht: Original-Records bleiben unveraendert.
Pro Original-Record genau ein Eintrag in ``workshop_entity_embeddings`` mit
einer pgvector-Spalte (1024 Dim. bge-m3).

UNIQUE-Constraint auf (source_module, source_record_id) sichert Idempotenz —
``upsert_embedding`` darf beliebig oft mit denselben IDs aufgerufen werden.

Verbindung zur Architektur:
- Original-Records: ``workshop_state_aid_awards``, ``workshop_beneficiary_records``,
  ``workshop_sanctions_entries``, ``workshop_company_entities``
- ``services.entity_embeddings`` baut + sucht die Embeddings.
- IVFFlat-Cosine-Index wird im Lifespan separat angelegt (siehe ``main.py``),
  weil SQLAlchemy ``USING ivfflat`` nicht direkt deklariert.
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger, Column, DateTime, String, Text, UniqueConstraint, func,
)
from pgvector.sqlalchemy import Vector

from database import Base


class EntityEmbedding(Base):
    """Universelles Embedding-Storage fuer alle Module.

    Ein Eintrag pro Original-Record (state_aid|beneficiary|sanctions|
    company_entity), mit pgvector-Spalte fuer bge-m3 1024-dim. Original-
    Records bleiben unveraendert — additive Schicht.

    ``text_input`` enthaelt den Text, der embeddet wurde — fuer Audit und
    Debugging (z.B. "Welcher Text wurde fuer state_aid:42 verwendet?").
    ``model_name`` haelt den Modellnamen, damit ein Modell-Wechsel sauber
    versioniert ist (nur frische Embeddings werden bei der Suche genutzt).
    """

    __tablename__ = "workshop_entity_embeddings"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source_module = Column(String(20), nullable=False, index=True)
    # 'state_aid' | 'beneficiary' | 'sanctions' | 'company_entity'
    source_record_id = Column(String(64), nullable=False, index=True)
    text_input = Column(Text, nullable=False)
    embedding = Column(Vector(1024), nullable=False)
    model_name = Column(String(80), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "source_module", "source_record_id",
            name="uq_entity_embedding_source",
        ),
    )
