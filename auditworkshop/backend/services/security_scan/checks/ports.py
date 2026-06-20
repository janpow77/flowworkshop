"""Erreichbarkeit/Dienste (NET-02/03/04) — nicht-intrusiver TCP-Connect-Scan.

Stellt ausschließlich fest, ob ein Port eine TCP-Verbindung annimmt. Kein
Service-Probing, kein Ansprechen/Ausnutzen des Dienstes (eingriffstiefe=passiv).
"""
from __future__ import annotations

import socket
from concurrent.futures import ThreadPoolExecutor

from config import SECURITY_EXPECTED_PORTS, SECURITY_SCAN_PORTS
from ..report import GELB, GRAU, KONFORM, Finding, make_finding

# Bezeichnung sensibler Dienste für die Befund-Erläuterung.
_PORT_LABEL = {
    21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP", 53: "DNS", 80: "HTTP",
    110: "POP3", 143: "IMAP", 443: "HTTPS", 445: "SMB", 587: "SMTP", 993: "IMAPS",
    995: "POP3S", 1433: "MSSQL", 3306: "MySQL", 3389: "RDP", 5432: "PostgreSQL",
    6379: "Redis", 8080: "HTTP-alt", 8443: "HTTPS-alt", 9200: "Elasticsearch",
    27017: "MongoDB",
}
_SENSIBLE = {21, 22, 23, 445, 1433, 3306, 3389, 5432, 6379, 9200, 27017}


def _is_open(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def check_ports(host: str, timeout: float) -> tuple[list[Finding], dict]:
    ports = SECURITY_SCAN_PORTS
    with ThreadPoolExecutor(max_workers=min(16, len(ports) or 1)) as ex:
        results = list(ex.map(lambda p: (p, _is_open(host, p, timeout)), ports))
    open_ports = sorted(p for p, ok in results if ok)
    extra = [p for p in open_ports if p not in SECURITY_EXPECTED_PORTS]
    observed = {"scanned": ports, "open": open_ports, "extra": extra}

    def _label(p: int) -> str:
        return f"{p} ({_PORT_LABEL.get(p, 'unbekannt')})"

    findings: list[Finding] = []

    # NET-04: detaillierter Portscan-Befund
    if not open_ports:
        findings.append(make_finding("NET-04", istzustand="Keiner der geprüften Ports nahm eine Verbindung an.",
                                     bewertung=GRAU, rohbefund=observed))
    elif not extra:
        findings.append(make_finding("NET-04", istzustand=f"Nur zweckgebundene Ports erreichbar: {', '.join(_label(p) for p in open_ports)}.",
                                     bewertung=KONFORM, rohbefund=observed))
    else:
        sens = [p for p in extra if p in _SENSIBLE]
        hint = " Darunter Verwaltungs-/Datenbankdienste." if sens else ""
        findings.append(make_finding(
            "NET-04",
            istzustand=f"Zusätzlich erreichbar: {', '.join(_label(p) for p in extra)}.{hint} Der Portscan hat nur die Erreichbarkeit festgestellt; ein Ansprechen/Ausnutzen ist nicht erfolgt.",
            bewertung=GELB,
            empfehlung="Zugang zu Verwaltungs-/Legacy-Diensten auf bekannte Quell-Adressen beschränken oder über ein vorgelagertes Netzsegment kapseln.",
            rohbefund=observed))

    # NET-02: zusammenfassende Bewertung offener Standardports
    if not extra:
        findings.append(make_finding("NET-02", istzustand="Keine über den Zweck hinausgehenden offenen Ports.",
                                     bewertung=KONFORM, rohbefund=observed))
    else:
        findings.append(make_finding("NET-02", istzustand=f"{len(extra)} Port(s) über den Webbetrieb hinaus erreichbar.",
                                     bewertung=GELB, empfehlung="Angriffsfläche durch Schließen/Kapseln nicht benötigter Ports reduzieren.",
                                     rohbefund=observed))

    # NET-03: Admin-Oberflächen — nicht von außen abschließend beurteilbar
    findings.append(make_finding(
        "NET-03",
        istzustand="Eine abschließende Beurteilung des Schutzes von Administrationsoberflächen ist von außen nicht-intrusiv nicht möglich.",
        bewertung=GRAU,
        empfehlung="Im Rahmen einer manuellen Prüfung unter Einbeziehung der Betreiberdokumentation bewerten."))

    return findings, observed
