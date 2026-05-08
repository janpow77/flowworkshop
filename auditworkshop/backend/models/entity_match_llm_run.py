"""
flowworkshop · models/entity_match_llm_run.py

Layer C — Audit-Trail fuer den naechtlichen LLM-Verifikations-Batch.

Jeder Lauf des EntityMatch-LLM-Batchs (cron oder admin-getriggert) wird hier
persistiert. Pro Run:
  - Trigger (cron/admin:<uid>)
  - Status (running/ok/partial/failed)
  - Eligible/Verified/Confirmed/Rejected/Unknown-Counters
  - Parameter (max_matches, score_min, score_max, ...) als JSON
  - Fehler-Message bei failed/partial

Das Modell ist additiv — schreibt nichts in workshop_entity_matches selbst,
sondern liefert nur den Audit-Trail. Der eigentliche Verdict-Effekt
(rejected, confirmed_by_user_id) landet auf den EntityMatch-Eintraegen
direkt; siehe services/entity_match_llm_verifier.py.
"""
from sqlalchemy import (
    BigInteger, Column, DateTime, Integer, JSON, String, Text, func,
)

from database import Base


class EntityMatchLlmRun(Base):
    """Ein Lauf des naechtlichen LLM-Verifikations-Batchs."""

    __tablename__ = "workshop_entity_match_llm_runs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    started_at = Column(
        DateTime, server_default=func.now(), nullable=False, index=True,
    )
    finished_at = Column(DateTime, nullable=True)

    triggered_by = Column(String(80), nullable=False)
    # 'cron' | 'admin:<uid>' | 'cli'
    status = Column(String(16), nullable=False, server_default="running")
    # 'running' | 'ok' | 'partial' | 'failed'

    total_eligible = Column(Integer, nullable=True)
    total_verified = Column(Integer, nullable=True)
    matches_confirmed = Column(Integer, nullable=True)
    matches_rejected = Column(Integer, nullable=True)
    matches_unknown = Column(Integer, nullable=True)
    skipped_due_to_timeout = Column(Integer, nullable=True)

    parameters = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
