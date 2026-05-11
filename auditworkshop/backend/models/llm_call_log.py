"""flowworkshop · models/llm_call_log.py

Detail-Log pro abgeschlossenem LLM-Call. Wird direkt aus
``services/ollama_service.py`` per Background-Executor geschrieben — d.h.
erfasst auch SSE-Streams vollstaendig (im Gegensatz zu workshop_access_log,
das durch BaseHTTPMiddleware-Lifecycle bei SSE keine Token-Daten sieht).

Pruning analog access_log via services.scheduler (gleicher TTL).
"""
from sqlalchemy import Column, String, Integer, BigInteger, DateTime, Index, func

from database import Base


class LlmCallLog(Base):
    __tablename__ = "workshop_llm_call_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)

    # Aus dem Request-Kontext (ContextVar in der Middleware gesetzt).
    # NULL, wenn der Call ausserhalb eines HTTP-Requests passiert
    # (z.B. Background-Job, Warmup).
    route = Column(String(255), nullable=True, index=True)
    user_id = Column(String(36), nullable=True)

    model = Column(String(80), nullable=True, index=True)
    backend = Column(String(20), nullable=True)  # "ollama" | "gateway"
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=False)

    # Statusfeld: "ok" (default), "error", "cancelled", "timeout"
    status = Column(String(16), nullable=False, default="ok", index=True)
    error = Column(String(255), nullable=True)

    __table_args__ = (
        Index("ix_llm_call_route_time", "route", "created_at"),
        Index("ix_llm_call_model_time", "model", "created_at"),
        Index("ix_llm_call_status_time", "status", "created_at"),
    )
