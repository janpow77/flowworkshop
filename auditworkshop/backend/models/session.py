"""Persistente Workshop-Session.

Die Session wird ueber das Login-Token im Authorization-Header referenziert
und ueberlebt damit Backend-Restarts (im Gegensatz zum bisherigen In-Memory-
Dictionary).
"""
from datetime import datetime

from sqlalchemy import Column, String, DateTime

from database import Base


class WorkshopSession(Base):
    __tablename__ = "workshop_sessions"

    token = Column(String(64), primary_key=True)
    user_id = Column(String(36), nullable=False, index=True)
    email = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    organization = Column(String(255), nullable=False, default="")
    role = Column(String(32), nullable=False, default="participant")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)
