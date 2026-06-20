"""
flowworkshop · models/security_scan.py

Webseiten-Sicherheitsprüfung (Kernanforderung 6 — ISMS-Systemprüfung).

Jeder nicht-intrusive Prüflauf einer Webanwendung (TLS, HTTP-Header, Cookies,
HTTPS-Erzwingung, offene Ports, Versionsbanner + CVE-Indikation) wird hier
persistiert — inklusive der dokumentierten Berechtigungs-Selbstbestätigung des
Prüfers (Audit-Nachweis nach §2 der Prüfmethodik) und der Ampel-Bewertung.

Die Einzelbefunde liegen als JSON (`findings`) gemäß Datenmodell §6 vor:
``pruef_id, bezug, sollzustand, istzustand, bewertung, empfehlung, rohbefund,
eingriffstiefe``. ``eingriffstiefe`` ist strukturell immer ``passiv`` — aktive,
einwilligungsbedürftige Tests sind ausgeschlossen.
"""
from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Integer, JSON, String, Text, func,
)

from database import Base


class SecurityScanRun(Base):
    """Ein nicht-intrusiver Sicherheits-Prüflauf einer Webanwendung."""

    __tablename__ = "workshop_security_scan_runs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    scan_id = Column(String(36), nullable=False, unique=True, index=True)

    target_url = Column(String(2000), nullable=False)
    target_host = Column(String(255), nullable=True)
    triggered_by = Column(String(80), nullable=False)  # 'user:<uid>'

    # ── Berechtigungs-Selbstbestätigung (Audit-Nachweis §2) ──────────────────
    authorization_confirmed = Column(Boolean, nullable=False, server_default="false")
    authorization_declared_by = Column(String(255), nullable=True)  # email/uid
    authorization_text = Column(Text, nullable=True)  # akzeptierter Rechtstext
    authorized_at = Column(DateTime, nullable=True)

    started_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(16), nullable=False, server_default="pending")
    # 'pending' | 'running' | 'completed' | 'failed'

    # ── Ampel-Aggregation ────────────────────────────────────────────────────
    count_konform = Column(Integer, nullable=False, server_default="0")
    count_gelb = Column(Integer, nullable=False, server_default="0")
    count_rot = Column(Integer, nullable=False, server_default="0")
    count_grau = Column(Integer, nullable=False, server_default="0")
    overall = Column(String(16), nullable=True)  # 'konform' | 'gelb' | 'kritisch'

    findings = Column(JSON, nullable=True)  # Liste der Einzelbefunde (§6-Felder)
    observed = Column(JSON, nullable=True)  # beobachtete Architektur-Rohdaten
    screenshot_path = Column(String(500), nullable=True)
    architecture_path = Column(String(500), nullable=True)

    error_message = Column(Text, nullable=True)
    parameters = Column(JSON, nullable=True)
