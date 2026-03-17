"""
flowworkshop · models/checklist.py
WorkshopChecklist, WorkshopQuestion, WorkshopEvidence
Referenz: audit_designer VpChecklist/VpQuestion (vollwertiges Modell).
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Text, Integer, Float, DateTime, Enum, ForeignKey,
    UniqueConstraint, func,
)
from sqlalchemy.orm import relationship

from database import Base


class AnswerType(str, enum.Enum):
    BOOLEAN = "boolean"          # Ja / Nein / Teilweise / Entfaellt (yes/no/partial/na)
    BOOLEAN_JN = "boolean_jn"   # Ja / Nein
    DATE = "date"
    AMOUNT = "amount"
    ENUM = "enum"
    TEXT = "text"


# Gueltige answer_value-Werte fuer BOOLEAN-Fragen
BOOLEAN_ANSWERS = {"yes", "no", "partial", "na"}
BOOLEAN_JN_ANSWERS = {"yes", "no"}


class RemarkAiStatus(str, enum.Enum):
    DRAFT = "draft"
    ACCEPTED = "accepted"
    EDITED = "edited"
    REJECTED = "rejected"


class WorkshopChecklist(Base):
    __tablename__ = "workshop_checklists"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(
        String(36), ForeignKey("workshop_projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    template_id = Column(String(100), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    project = relationship("WorkshopProject", back_populates="checklists")
    questions = relationship(
        "WorkshopQuestion", back_populates="checklist", cascade="all, delete-orphan",
        order_by="WorkshopQuestion.sort_order",
    )


class WorkshopQuestion(Base):
    __tablename__ = "workshop_questions"
    __table_args__ = (
        UniqueConstraint("checklist_id", "question_key", name="uq_checklist_question_key"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    checklist_id = Column(
        String(36), ForeignKey("workshop_checklists.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    question_key = Column(String(50), nullable=False, index=True)
    question_text = Column(Text, nullable=True)
    answer_type = Column(Enum(AnswerType), default=AnswerType.BOOLEAN)
    category = Column(String(100), nullable=True)
    sort_order = Column(Integer, default=0)

    # Antwort
    answer_value = Column(Text, nullable=True)

    # Bemerkungen
    remark_manual = Column(Text, nullable=True)
    remark_ai = Column(Text, nullable=True)
    remark_ai_edited = Column(Text, nullable=True)
    remark_ai_status = Column(Enum(RemarkAiStatus), nullable=True)
    reject_feedback = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    checklist = relationship("WorkshopChecklist", back_populates="questions")
    evidence = relationship(
        "WorkshopEvidence", back_populates="question", cascade="all, delete-orphan",
    )


class WorkshopEvidence(Base):
    __tablename__ = "workshop_evidence"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    question_id = Column(
        String(36), ForeignKey("workshop_questions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    source_name = Column(String(255), nullable=True)
    filename = Column(String(255), nullable=True)
    location = Column(String(100), nullable=True)
    snippet = Column(Text, nullable=True)
    score = Column(Float, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    question = relationship("WorkshopQuestion", back_populates="evidence")
