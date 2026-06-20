"""Datenmodell (§6), Prüfkatalog und Bewertungslogik (§4).

Jeder Befund ist ein ``Finding`` mit den Feldern aus §6 des Prüfkatalogs.
``bewertung`` folgt der Ampel: konform (grün) · gelb · rot · grau (nicht
prüfbar). ``eingriffstiefe`` ist strukturell immer ``passiv``.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal

Bewertung = Literal["konform", "gelb", "rot", "grau"]

# ── Bewertungs-Stufen (Spec §4) ──────────────────────────────────────────────
KONFORM = "konform"   # grün — Ist == Soll
GELB = "gelb"         # Abweichung mit erhöhtem Risiko
ROT = "rot"           # kritische Abweichung
GRAU = "grau"         # nicht prüfbar (manuell/organisatorisch zu bewerten)

BEWERTUNG_LABEL = {
    KONFORM: "konform",
    GELB: "Abweichung mit erhöhtem Risiko",
    ROT: "kritische Abweichung",
    GRAU: "nicht prüfbar",
}

# Gesamtbewertung (schwächste Stelle)
OVERALL_KONFORM = "konform"
OVERALL_GELB = "gelb"
OVERALL_KRITISCH = "kritisch"


# ── Prüfkatalog (Spec §3): Soll-Zustände + Grundschutz-Bezug ─────────────────
PRUEFKATALOG: dict[str, dict[str, str]] = {
    # 3.1 Transportverschlüsselung
    "TLS-01": {"gruppe": "Transportverschlüsselung (TLS)", "titel": "Unterstützte Protokollversionen", "bezug": "TR-02102-2",
               "soll": "Ausschließlich TLS 1.2 und TLS 1.3; SSLv2/3, TLS 1.0/1.1 deaktiviert"},
    "TLS-02": {"gruppe": "Transportverschlüsselung (TLS)", "titel": "Cipher-Suiten", "bezug": "TR-02102-2",
               "soll": "Nur konforme Suiten; kein RC4, 3DES, NULL oder Export"},
    "TLS-03": {"gruppe": "Transportverschlüsselung (TLS)", "titel": "Gültigkeit des Serverzertifikats", "bezug": "APP.3.1.A14",
               "soll": "Zeitlich gültig, vertrauenswürdige Kette, Domänenübereinstimmung"},
    "TLS-04": {"gruppe": "Transportverschlüsselung (TLS)", "titel": "Schlüssellänge und Signaturverfahren", "bezug": "TR-02102-2",
               "soll": "RSA ab 3000 Bit oder ECC ab 250 Bit; keine SHA-1-Signatur"},
    "TLS-05": {"gruppe": "Transportverschlüsselung (TLS)", "titel": "Perfect Forward Secrecy", "bezug": "TR-02102-2",
               "soll": "PFS-fähige Suiten bevorzugt ausgehandelt"},
    # 3.2 HTTP-Sicherheitsheader
    "HDR-01": {"gruppe": "HTTP-Sicherheitsheader", "titel": "Strict-Transport-Security", "bezug": "APP.3.1.A14",
               "soll": "Gesetzt mit max-age von mindestens 31536000"},
    "HDR-02": {"gruppe": "HTTP-Sicherheitsheader", "titel": "Content-Security-Policy", "bezug": "APP.3.1.A1",
               "soll": "Gesetzt mit restriktiver Richtlinie"},
    "HDR-03": {"gruppe": "HTTP-Sicherheitsheader", "titel": "X-Content-Type-Options", "bezug": "APP.3.1.A1",
               "soll": "nosniff gesetzt"},
    "HDR-04": {"gruppe": "HTTP-Sicherheitsheader", "titel": "X-Frame-Options bzw. frame-ancestors", "bezug": "APP.3.1.A1",
               "soll": "Clickjacking-Schutz gesetzt"},
    "HDR-05": {"gruppe": "HTTP-Sicherheitsheader", "titel": "Referrer-Policy", "bezug": "APP.3.1.A1",
               "soll": "Restriktiver Wert gesetzt"},
    "HDR-06": {"gruppe": "HTTP-Sicherheitsheader", "titel": "Server- und Versionskennung", "bezug": "APP.3.1.A1",
               "soll": "Keine Preisgabe von Produkt- und Versionsinformationen"},
    # 3.3 Cookies
    "COO-01": {"gruppe": "Cookies und Sitzungsverwaltung", "titel": "Secure-Attribut", "bezug": "APP.3.1.A7",
               "soll": "Bei allen Cookies gesetzt"},
    "COO-02": {"gruppe": "Cookies und Sitzungsverwaltung", "titel": "HttpOnly-Attribut", "bezug": "APP.3.1.A7",
               "soll": "Bei Sitzungs-Cookies gesetzt"},
    "COO-03": {"gruppe": "Cookies und Sitzungsverwaltung", "titel": "SameSite-Attribut", "bezug": "APP.3.1.A7",
               "soll": "Strict oder Lax gesetzt"},
    # 3.4 Erreichbarkeit und Dienste
    "NET-01": {"gruppe": "Erreichbarkeit und Dienste", "titel": "Erzwingung von HTTPS", "bezug": "APP.3.1.A14",
               "soll": "Weiterleitung von HTTP auf HTTPS"},
    "NET-02": {"gruppe": "Erreichbarkeit und Dienste", "titel": "Offene Standardports", "bezug": "NET.3.3",
               "soll": "Keine über den Zweck hinausgehenden offenen Ports"},
    "NET-03": {"gruppe": "Erreichbarkeit und Dienste", "titel": "Erreichbarkeit von Administrationsoberflächen", "bezug": "APP.3.1.A4",
               "soll": "Keine öffentlich erreichbaren Administrationspfade"},
    "NET-04": {"gruppe": "Erreichbarkeit und Dienste", "titel": "Offene Ports (nicht-intrusiver Portscan)", "bezug": "NET.3.3",
               "soll": "Nur die für den Zweck erforderlichen Ports erreichbar"},
    # 3.5 Passive Schwachstellenindikation
    "VUL-01": {"gruppe": "Passive Schwachstellenindikation", "titel": "Software-Versionsbanner", "bezug": "APP.3.1.A1",
               "soll": "Keine Preisgabe von Produkt-/Versionsinformationen"},
    "VUL-02": {"gruppe": "Passive Schwachstellenindikation", "titel": "Abgleich erkannter Versionen mit Schwachstellendatenbank", "bezug": "APP.3.1.A16",
               "soll": "Keine Komponente mit bekannter, öffentlich dokumentierter Schwachstelle (CVE)"},
}


@dataclass
class Finding:
    """Ein Einzelbefund gemäß Datenmodell §6."""
    pruef_id: str
    bezug: str
    sollzustand: str
    istzustand: str
    bewertung: Bewertung
    empfehlung: str = ""
    rohbefund: dict[str, Any] = field(default_factory=dict)
    eingriffstiefe: str = "passiv"  # strukturell ausgeschlossen: aktive Tests

    @property
    def titel(self) -> str:
        return PRUEFKATALOG.get(self.pruef_id, {}).get("titel", self.pruef_id)

    @property
    def gruppe(self) -> str:
        return PRUEFKATALOG.get(self.pruef_id, {}).get("gruppe", "")

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["titel"] = self.titel
        d["gruppe"] = self.gruppe
        d["bewertung_label"] = BEWERTUNG_LABEL.get(self.bewertung, self.bewertung)
        return d


def make_finding(pruef_id: str, *, istzustand: str, bewertung: Bewertung,
                 empfehlung: str = "", rohbefund: dict | None = None) -> Finding:
    """Erzeugt einen Finding mit Soll/Bezug aus dem Prüfkatalog."""
    cat = PRUEFKATALOG.get(pruef_id, {})
    return Finding(
        pruef_id=pruef_id,
        bezug=cat.get("bezug", ""),
        sollzustand=cat.get("soll", ""),
        istzustand=istzustand,
        bewertung=bewertung,
        empfehlung=empfehlung,
        rohbefund=rohbefund or {},
    )


def aggregate(findings: list[Finding]) -> dict[str, Any]:
    """Zählt Ampel-Stufen und bestimmt die Gesamtbewertung (schwächste Stelle)."""
    counts = {KONFORM: 0, GELB: 0, ROT: 0, GRAU: 0}
    for f in findings:
        counts[f.bewertung] = counts.get(f.bewertung, 0) + 1
    if counts[ROT] > 0:
        overall = OVERALL_KRITISCH
    elif counts[GELB] > 0:
        overall = OVERALL_GELB
    else:
        overall = OVERALL_KONFORM
    return {"counts": counts, "overall": overall}


@dataclass
class SecurityScanReport:
    """Aggregierter Befundbericht eines Scan-Laufs."""
    scan_id: str
    url: str
    host: str
    issued_at: datetime
    authorized_by: str | None
    authorization_text: str | None
    findings: list[Finding] = field(default_factory=list)
    observed: dict[str, Any] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    overall: str = OVERALL_KONFORM
    has_screenshot: bool = False
    has_architecture: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "scan_id": self.scan_id,
            "url": self.url,
            "host": self.host,
            "issued_at": self.issued_at.isoformat(),
            "authorized_by": self.authorized_by,
            "authorization_text": self.authorization_text,
            "bezugsrahmen": "APP.3.1, NET.3.3, BSI TR-02102-2",
            "overall": self.overall,
            "counts": self.counts,
            "findings": [f.to_dict() for f in self.findings],
            "observed": self.observed,
            "has_screenshot": self.has_screenshot,
            "has_architecture": self.has_architecture,
        }
