"""
flowworkshop · models/project.py
WorkshopProject — Referenz: audit_designer VpProject (vereinfacht, ohne Auth).
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, Enum, func
from sqlalchemy.orm import relationship

from database import Base


class Foerderphase(str, enum.Enum):
    FP_2014_2020 = "2014-2020"
    FP_2021_2027 = "2021-2027"


class WorkshopProject(Base):
    __tablename__ = "workshop_projects"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    aktenzeichen = Column(String(100), nullable=False, index=True)
    geschaeftsjahr = Column(String(10), nullable=False)
    program = Column(String(255), default="EFRE Hessen")
    foerderphase = Column(Enum(Foerderphase), nullable=True)
    zuwendungsempfaenger = Column(String(255), nullable=True)
    projekttitel = Column(String(500), nullable=True)
    foerderkennzeichen = Column(String(100), nullable=True)
    bewilligungszeitraum = Column(String(100), nullable=True)
    gesamtkosten = Column(String(50), nullable=True)
    foerdersumme = Column(String(50), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    checklists = relationship(
        "WorkshopChecklist", back_populates="project", cascade="all, delete-orphan"
    )
    documents = relationship(
        "ProjectDocument", back_populates="project", cascade="all, delete-orphan"
    )
