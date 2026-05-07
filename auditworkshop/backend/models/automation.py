"""
flowworkshop · models/automation.py
Audit-/Logging-Tabellen für Auto-Harvest, Sanktions-Refresh und LLM-Fragen
(Plan v3.2 §16.2-16.4).
"""
from sqlalchemy import (
    Column, String, Text, Integer, Boolean, BigInteger, DateTime,
    JSON, Float, Index, func,
)
import uuid

from database import Base


class HarvestRun(Base):
    __tablename__ = "workshop_harvest_runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    started_at = Column(DateTime, server_default=func.now(), index=True)
    finished_at = Column(DateTime, nullable=True)
    triggered_by = Column(String(80), nullable=False)        # 'cron' | 'admin:<user_id>'
    status = Column(String(16), nullable=False, server_default="running")
    sources_total = Column(Integer, server_default="0")
    sources_ok = Column(Integer, server_default="0")
    sources_skipped = Column(Integer, server_default="0")
    sources_failed = Column(Integer, server_default="0")
    errors = Column(JSON, nullable=True)
    log_excerpt = Column(Text, nullable=True)


class HarvestSourceUpdate(Base):
    __tablename__ = "workshop_harvest_source_updates"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id = Column(String(36), nullable=False, index=True)
    source = Column(String(120), nullable=False, index=True)
    bundesland = Column(String(64), nullable=True)
    fonds = Column(String(40), nullable=True)
    url = Column(String(500), nullable=True)
    status = Column(String(20), nullable=False)  # 'updated'|'unchanged'|'failed'|'new'
    rows_before = Column(Integer, nullable=True)
    rows_after = Column(Integer, nullable=True)
    file_size_bytes = Column(BigInteger, nullable=True)
    sha256_old = Column(String(64), nullable=True)
    sha256_new = Column(String(64), nullable=True)
    error = Column(Text, nullable=True)
    updated_at = Column(DateTime, server_default=func.now())


class SanctionsRefreshRun(Base):
    __tablename__ = "workshop_sanctions_refresh"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    started_at = Column(DateTime, server_default=func.now(), index=True)
    finished_at = Column(DateTime, nullable=True)
    triggered_by = Column(String(80), nullable=False)
    status = Column(String(16), nullable=False)
    source_url = Column(String(500), nullable=True)
    file_size_bytes = Column(BigInteger, nullable=True)
    sha256_old = Column(String(64), nullable=True)
    sha256_new = Column(String(64), nullable=True)
    rows_before = Column(Integer, nullable=True)
    rows_after = Column(Integer, nullable=True)
    persons_before = Column(Integer, nullable=True)
    persons_after = Column(Integer, nullable=True)
    organizations_before = Column(Integer, nullable=True)
    organizations_after = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)


class Notification(Base):
    """Internes Notification-Center (Plan v3.2 Phase 6) — kein Mail-Versand.
    Bell-Icon im Frontend zeigt unread-Count.
    """
    __tablename__ = "workshop_notifications"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(String(36), nullable=False, index=True)
    kind = Column(String(40), nullable=False)
    # 'forum_reply' | 'forum_mention' | 'admin_pending' |
    # 'admin_harvest_failed' | 'admin_sanctions_failed' | 'doc_uploaded'
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=True)
    link = Column(String(500), nullable=True)
    read_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)

    __table_args__ = (
        Index("ix_notif_user_unread", "user_id", "read_at"),
    )


class LlmQuestionLog(Base):
    """Plan v3.2 §16.4 — Logging aller Workshop-LLM-Streams für spätere
    Optimierung (Mode-Erkennung, Trigger, Prompt-Tuning).
    """
    __tablename__ = "workshop_llm_question_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)
    user_id = Column(String(36), nullable=True, index=True)
    session_id = Column(String(64), nullable=True)
    ip_hash = Column(String(64), nullable=True)
    scenario = Column(Integer, nullable=False, index=True)
    prompt = Column(Text, nullable=False)
    prompt_normalized = Column(String(500), nullable=True, index=True)
    documents_count = Column(Integer, server_default="0")
    with_context = Column(Boolean, server_default="true")

    answer_path = Column(String(64), nullable=True, index=True)
    matched_mode = Column(String(40), nullable=True)
    name_filter_label = Column(String(120), nullable=True)
    items_returned = Column(Integer, nullable=True)
    fallback_used = Column(Boolean, server_default="false")

    elapsed_ms = Column(Integer, nullable=True)
    model_name = Column(String(80), nullable=True)
    token_count = Column(Integer, nullable=True)
    tok_per_s = Column(Float, nullable=True)
    ttfb_ms = Column(Integer, nullable=True)

    response_excerpt = Column(Text, nullable=True)
    response_total_chars = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)

    user_feedback = Column(String(20), nullable=True)
    user_feedback_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_llm_log_scenario_created", "scenario", "created_at"),
    )
