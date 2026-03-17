"""
flowworkshop · models/document.py
Projektdokumente — hochgeladene Unterlagen pro Projekt.
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship

from database import Base


class ProjectDocument(Base):
    __tablename__ = "workshop_project_documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(
        String(36), ForeignKey("workshop_projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    filename = Column(String(255), nullable=False)
    source_label = Column(String(100), nullable=False)
    extracted_text = Column(Text, nullable=True)
    char_count = Column(Integer, default=0)
    parse_method = Column(String(50), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    project = relationship("WorkshopProject", back_populates="documents")
