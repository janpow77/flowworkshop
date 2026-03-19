"""
flowworkshop · models/registration.py
Anmeldung, Tagesordnung, Themenboard.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Text, Integer, Float, Boolean, DateTime, Enum, func,
)
from sqlalchemy.orm import relationship

from database import Base


class AgendaItemType(str, enum.Enum):
    VORTRAG = "vortrag"
    DISKUSSION = "diskussion"
    WORKSHOP = "workshop"
    PAUSE = "pause"
    ORGANISATION = "organisation"


class AgendaItemStatus(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    DONE = "done"
    SKIPPED = "skipped"


class SubmissionVisibility(str, enum.Enum):
    PUBLIC = "public"
    MODERATION = "moderation"


class WorkshopMeta(Base):
    """Workshop-Metadaten (Singleton — immer nur eine Zeile)."""
    __tablename__ = "workshop_meta"

    id = Column(Integer, primary_key=True, default=1)
    title = Column(String(255), default="Prüferworkshop EFRE Hessen")
    subtitle = Column(String(500), default="KI und LLMs in der EFRE-Prüfbehörde")
    date = Column(String(50), default="")
    time = Column(String(50), default="09:00 - 16:00 Uhr")
    location_short = Column(String(255), default="")
    location_full = Column(String(500), default="")
    organizer = Column(String(255), default="Hessische Prüfbehörde")
    registration_deadline = Column(String(50), default="")
    qr_url = Column(String(500), default="")
    admin_pin = Column(String(20), default="1234")
    workshop_mode = Column(Boolean, default=False)  # False=Vorfeld, True=Workshop-Tag
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class AgendaItem(Base):
    __tablename__ = "workshop_agenda_items"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    day = Column(Integer, default=1)  # 1=Dienstag, 2=Mittwoch, 3=Donnerstag
    time = Column(String(20), nullable=False)
    duration_minutes = Column(Integer, default=30)
    item_type = Column(Enum(AgendaItemType), default=AgendaItemType.VORTRAG)
    title = Column(String(500), nullable=False)
    speaker = Column(String(255), nullable=True)
    note = Column(Text, nullable=True)
    category = Column(String(50), default="plenary")  # plenary, workshop5
    status = Column(Enum(AgendaItemStatus), default=AgendaItemStatus.PENDING)
    started_at = Column(DateTime, nullable=True)  # Wann der Punkt gestartet wurde
    scenario_id = Column(Integer, nullable=True)  # Szenario 1-6 (optional)
    visible = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())


class Registration(Base):
    __tablename__ = "workshop_registrations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    organization = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    department = Column(String(255), nullable=True)
    fund = Column(String(100), nullable=True)  # EFRE, ESF, ESF+, INTERREG, etc.
    invite_token = Column(String(64), nullable=True, unique=True)
    privacy_accepted = Column(Boolean, default=False)
    anthropic_consent = Column(Boolean, default=False)
    filename = Column(String(255), nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class TopicSubmission(Base):
    __tablename__ = "workshop_topic_submissions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    registration_id = Column(String(36), nullable=True)
    topic = Column(String(500), nullable=False)
    question = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    visibility = Column(Enum(SubmissionVisibility), default=SubmissionVisibility.PUBLIC)
    anonymous = Column(Boolean, default=False)
    organization = Column(String(255), nullable=True)
    votes = Column(Integer, default=0)
    filename = Column(String(255), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
