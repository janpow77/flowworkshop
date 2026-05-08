"""
flowworkshop · models/access_log.py
DSGVO-konformes Access-Log fuer das Workshop-Backend.

Speichert pro /api/*-Request eine Zeile mit:
- Zeitpunkt, Methode, Pfad und FastAPI-Route-Template
- Status-Code, Dauer in Millisekunden, Response-Groesse
- Optional: user_id + role aus der Session (falls Token vorhanden)
- ip_hash (SHA256 ueber IP + Salt) — kein Klartext-IP
- ua_short (gekuerzter User-Agent + grobe Browser-Kategorie)
- referer_path (nur Pfad, keine Query)

Sensible Endpoints werden nur ueber path/query_string erfasst — niemals der
Body. Query-Parameter wie ``password``, ``token``, ``api_key`` werden vor dem
Insert auf ``***`` maskiert.

Pruning: ``services.scheduler.prune_access_log`` loescht taeglich Eintraege
aelter als ``WORKSHOP_ACCESS_LOG_TTL_DAYS`` (Default: 30 Tage).
"""
from sqlalchemy import (
    Column, String, Integer, BigInteger, DateTime, Index, func,
)

from database import Base


class AccessLog(Base):
    """Eine Zeile pro /api/*-Request (Health/Docs/Static werden ignoriert)."""
    __tablename__ = "workshop_access_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)

    method = Column(String(8), nullable=False)             # GET | POST | PUT | ...
    path = Column(String(255), nullable=False, index=True) # konkrete URL ohne Query
    # Route-Template aus FastAPI (z.B. /api/state-aid/award/{id})
    path_template = Column(String(255), nullable=True, index=True)
    query_string = Column(String(500), nullable=True)      # bereits sanitisiert
    status_code = Column(Integer, nullable=False, index=True)
    duration_ms = Column(Integer, nullable=True)

    # Auth-Kontext (best-effort — wenn Session erkannt wird)
    user_id = Column(String(36), nullable=True, index=True)
    role = Column(String(16), nullable=True)               # admin|moderator|attendee|anon

    # Datenschutz: nur Hashes
    ip_hash = Column(String(64), nullable=True)            # SHA256 hex
    ua_short = Column(String(80), nullable=True)
    referer_path = Column(String(255), nullable=True)
    response_size = Column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_access_log_user_time", "user_id", "created_at"),
        Index("ix_access_log_path_time", "path_template", "created_at"),
    )
