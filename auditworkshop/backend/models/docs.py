"""
flowworkshop · models/docs.py
Dokumente-Bereich (Plan v3.2 §7) — CIRCABC-ähnlich.
"""
from sqlalchemy import (
    Column, String, Text, Integer, Boolean, BigInteger, DateTime,
    ForeignKey, JSON, Index, func,
)
import uuid

from database import Base


class DocumentFolder(Base):
    __tablename__ = "workshop_doc_folders"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    parent_id = Column(String(36), nullable=True, index=True)
    name = Column(String(160), nullable=False)
    slug = Column(String(160), nullable=False)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, server_default="0", nullable=False)
    # 'public_read' | 'members_read' | 'moderators_only'
    visibility = Column(String(20), nullable=False, server_default="members_read")
    # 'members' | 'moderators' | 'none'
    upload_policy = Column(String(20), nullable=False, server_default="moderators")
    is_shared_pool = Column(Boolean, server_default="false", nullable=False)
    icon = Column(String(40), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    created_by_id = Column(String(36), nullable=True)


class DocumentFile(Base):
    __tablename__ = "workshop_doc_files"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    folder_id = Column(
        String(36),
        ForeignKey("workshop_doc_folders.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    tags = Column(JSON, nullable=True)
    mime_type = Column(String(120), nullable=True)
    size_bytes = Column(BigInteger, server_default="0", nullable=False)
    current_version_no = Column(Integer, server_default="1", nullable=False)
    storage_dir = Column(String(255), nullable=False)
    uploader_id = Column(String(36), nullable=True, index=True)
    uploader_name = Column(String(160), nullable=True)
    uploader_organization = Column(String(255), nullable=True)
    uploader_bundesland = Column(String(64), nullable=True, index=True)
    uploaded_at = Column(DateTime, server_default=func.now(), index=True)
    download_count = Column(Integer, server_default="0", nullable=False)
    deleted_at = Column(DateTime, nullable=True)


class DocumentVersion(Base):
    __tablename__ = "workshop_doc_versions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    file_id = Column(
        String(36),
        ForeignKey("workshop_doc_files.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    version_no = Column(Integer, nullable=False)
    storage_key = Column(String(500), nullable=False)
    sha256 = Column(String(64), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    mime_type = Column(String(120), nullable=True)
    uploader_id = Column(String(36), nullable=True)
    uploader_name = Column(String(160), nullable=True)
    uploaded_at = Column(DateTime, server_default=func.now())
    change_note = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_doc_version_file_no", "file_id", "version_no"),
    )


class DocumentDownloadLog(Base):
    __tablename__ = "workshop_doc_download_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    file_id = Column(String(36), nullable=False, index=True)
    version_no = Column(Integer, nullable=True)
    user_id = Column(String(36), nullable=True)
    ip_hash = Column(String(64), nullable=True)
    downloaded_at = Column(DateTime, server_default=func.now(), index=True)
