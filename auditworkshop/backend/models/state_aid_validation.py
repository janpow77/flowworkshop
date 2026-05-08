"""
flowworkshop · models/state_aid_validation.py

Persistierung der Validator-Laeufe (Self-Check) fuer State-Aid und kuenftig
weitere Module. Jede Zeile = ein vollstaendiger Lauf mit Findings im JSON-Feld.
"""
from sqlalchemy import (
    BigInteger, Column, DateTime, Integer, JSON, String, Index, func,
)

from database import Base


class StateAidValidationRun(Base):
    """Ein Validator-Lauf (z.B. nightly, manuell ueber Admin-API).

    `module` macht das Modell wiederverwendbar — initial nur `state_aid`,
    aber spaeter auch `beneficiaries`, `sanctions`, ...
    """
    __tablename__ = "workshop_validation_runs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    started_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)
    finished_at = Column(DateTime, nullable=True)

    module = Column(String(40), nullable=False, server_default="state_aid")
    status = Column(String(16), nullable=False)        # ok | warnings | failed
    duration_ms = Column(Integer, nullable=True)

    checks_total = Column(Integer, nullable=True)
    checks_passed = Column(Integer, nullable=True)
    checks_warned = Column(Integer, nullable=True)
    checks_failed = Column(Integer, nullable=True)

    findings = Column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_validation_module_started", "module", "started_at"),
    )
