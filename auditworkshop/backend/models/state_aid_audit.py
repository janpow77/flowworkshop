"""
flowworkshop · models/state_aid_audit.py

Audit-Trail fuer den Cross-Register-Pruefbericht (faktisch, ohne Bewertung).

Persistiert wer wann mit welchen Parametern einen PDF-Bericht erzeugt hat.
Speichert NUR Metadaten — kein PDF, kein Bewertungsergebnis. Der SHA256 des
PDF dient der Reproduzierbarkeit (gleiche Eingabe + gleicher Datenstand =
gleicher Hash).
"""
from sqlalchemy import (
    BigInteger, Column, DateTime, Integer, String, Index, func,
)

from database import Base


class AuditReportLog(Base):
    """Ein einzelner erzeugter Cross-Register-Pruefbericht.

    Pflichtdaten: created_at + query (was wurde gesucht).
    Optional: Auftraggeber, Pruefer-Name (manuelle Eingabe durch den
    Anwender beim Erzeugen) und die Hit-Counts pro Register.

    Wir speichern KEINE Bewertung, KEINEN Risiko-Score und KEINEN PDF-Inhalt:
    der Pruefer urteilt selbst, das System liefert nur die aufbereiteten Fakten.
    """
    __tablename__ = "workshop_audit_report_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    created_at = Column(
        DateTime, server_default=func.now(), nullable=False, index=True,
    )

    # Eingabe
    query = Column(String(255), nullable=False, index=True)
    auftraggeber = Column(String(120), nullable=True)
    pruefer_name = Column(String(120), nullable=True)
    pruefer_user_id = Column(String(36), nullable=True, index=True)

    # Aggregat-Zahlen aus den drei Registern (rein faktisch)
    state_aid_hits = Column(Integer, nullable=True)
    beneficiaries_hits = Column(Integer, nullable=True)
    sanctions_hits = Column(Integer, nullable=True)
    cross_references = Column(Integer, nullable=True)

    # PDF-Reproduzierbarkeit
    pdf_size_bytes = Column(Integer, nullable=True)
    pdf_sha256 = Column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_audit_report_query_created", "query", "created_at"),
    )
