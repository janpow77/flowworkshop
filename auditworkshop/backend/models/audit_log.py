"""Einfacher Audit-Trail fuer Workshop-Aktionen."""
import uuid
from datetime import datetime

from sqlalchemy import Column, String, Text, DateTime

from database import Base


class AuditLog(Base):
    __tablename__ = "workshop_audit_log"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    user_name = Column(String(255), nullable=True)
    organization = Column(String(255), nullable=True)
    action = Column(String(100), nullable=False)  # z.B. "scenario_1", "checklist_assess", "knowledge_ingest"
    detail = Column(Text, nullable=True)  # Freitext-Detail
