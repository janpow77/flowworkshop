"""
flowworkshop · models/corporate_lookup_cache.py

Cache fuer Konzernverbund-Lookups (services/corporate_registry.py).

Wir cachen die Antworten von GLEIF + Wikidata, damit wiederholte Aufrufe
mit dem gleichen Suchbegriff nicht jedes Mal zwei oeffentliche APIs
befragen muessen. TTL: 7 Tage (Konzernstrukturen aendern sich selten).

Personenbezogene Daten gibt es hier nicht — Konzernhierarchien (LEI-
Records, Wikidata-Q-IDs) sind nicht-personenbezogene Public Data.
"""
from sqlalchemy import (
    BigInteger, Column, DateTime, Index, JSON, String, func,
)

from database import Base


class CorporateLookupCache(Base):
    """Cache pro normalisiertem Suchbegriff.

    Schluessel: `query_normalized` — Lowercase + Whitespace-collapsed.
    `payload` haelt die CorporateGroup als JSON (siehe
    `corporate_registry.CorporateGroup.to_dict`).
    `expires_at` standardmaessig fetched_at + 7 Tage; einen Eintrag,
    dessen `expires_at` < jetzt ist, behandeln wir als "stale" und
    ueberschreiben ihn beim naechsten Lookup.
    """

    __tablename__ = "workshop_corporate_lookup_cache"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    query_normalized = Column(String(255), nullable=False, index=True)
    payload = Column(JSON, nullable=False)
    fetched_at = Column(
        DateTime, server_default=func.now(), nullable=False, index=True,
    )
    source = Column(String(20), nullable=True)
    # 'gleif' | 'wikidata' | 'mixed'
    expires_at = Column(DateTime, nullable=True, index=True)

    __table_args__ = (
        Index(
            "ix_corp_cache_query_fetched",
            "query_normalized", "fetched_at",
        ),
    )
