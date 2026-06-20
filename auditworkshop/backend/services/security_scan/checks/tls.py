"""TLS-Prüfungen (TLS-01..05) — nicht-intrusiv via stdlib ``ssl`` + ``cryptography``.

Beobachtet ausschließlich, welche Protokollversionen das Zielsystem zur
Aushandlung anbietet und liest das Serverzertifikat aus. Keine aktiven Angriffe.
"""
from __future__ import annotations

import logging
import socket
import ssl
from datetime import datetime, timezone

from ..report import GELB, GRAU, KONFORM, ROT, Finding, make_finding

log = logging.getLogger(__name__)

# Protokollversionen, die geprüft werden (Name → ssl.TLSVersion)
_PROTOCOLS = [
    ("TLS 1.0", ssl.TLSVersion.TLSv1),
    ("TLS 1.1", ssl.TLSVersion.TLSv1_1),
    ("TLS 1.2", ssl.TLSVersion.TLSv1_2),
    ("TLS 1.3", ssl.TLSVersion.TLSv1_3),
]
_KONFORM_PROTOS = {"TLS 1.2", "TLS 1.3"}
_VERALTET_PROTOS = {"TLS 1.0", "TLS 1.1"}

_WEAK_CIPHER_MARKERS = ("RC4", "3DES", "DES-", "NULL", "EXPORT", "MD5")


def _supports_protocol(host: str, port: int, version: ssl.TLSVersion, timeout: float) -> bool:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        ctx.minimum_version = version
        ctx.maximum_version = version
    except (ValueError, OSError):
        # Diese Version ist im lokalen OpenSSL gar nicht mehr verfügbar → gilt
        # als „nicht angeboten" (kann nicht ausgehandelt werden).
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host):
                return True
    except (ssl.SSLError, OSError, socket.timeout):
        return False


def _peer_cert_and_cipher(host: str, port: int, timeout: float):
    """Holt DER-Zertifikat + ausgehandelte Cipher über eine reguläre Verbindung."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with socket.create_connection((host, port), timeout=timeout) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as ss:
            der = ss.getpeercert(binary_form=True)
            cipher = ss.cipher()  # (name, protocol, secret_bits)
            return der, cipher


def check_tls(host: str, port: int, timeout: float, *, hostname: str | None = None) -> tuple[list[Finding], dict]:
    findings: list[Finding] = []
    observed: dict = {"protocols": [], "cipher": None, "certificate": None}
    hostname = hostname or host

    # ── TLS-01: Protokollversionen ───────────────────────────────────────────
    supported: list[str] = []
    for name, ver in _PROTOCOLS:
        if _supports_protocol(host, port, ver, timeout):
            supported.append(name)
    observed["protocols"] = supported

    if not supported:
        findings.append(make_finding(
            "TLS-01", istzustand="Keine TLS-Verbindung herstellbar (Port 443 nicht erreichbar oder kein TLS).",
            bewertung=GRAU, empfehlung="Erreichbarkeit/TLS-Konfiguration manuell prüfen.",
            rohbefund={"supported": supported}))
        # Ohne TLS-Verbindung können TLS-02..05 nicht beurteilt werden.
        for pid in ("TLS-02", "TLS-03", "TLS-04", "TLS-05"):
            findings.append(make_finding(pid, istzustand="Nicht prüfbar — keine TLS-Verbindung.", bewertung=GRAU))
        return findings, observed

    veraltet = sorted(_VERALTET_PROTOS & set(supported))
    if veraltet:
        findings.append(make_finding(
            "TLS-01",
            istzustand=f"Zusätzlich veraltete Protokolle aktiv: {', '.join(veraltet)} (neben {', '.join(sorted(_KONFORM_PROTOS & set(supported)))}).",
            bewertung=ROT,
            empfehlung="Veraltete Protokolle (TLS 1.0/1.1, SSLv2/3) serverseitig deaktivieren.",
            rohbefund={"supported": supported}))
    else:
        findings.append(make_finding(
            "TLS-01", istzustand=f"Nur konforme Protokolle: {', '.join(supported)}.",
            bewertung=KONFORM, rohbefund={"supported": supported}))

    # ── Zertifikat + Cipher laden ────────────────────────────────────────────
    der = None
    cipher = None
    try:
        der, cipher = _peer_cert_and_cipher(host, port, timeout)
        observed["cipher"] = list(cipher) if cipher else None
    except Exception as exc:  # noqa: BLE001
        log.warning("TLS-Zertifikat/Cipher konnte nicht gelesen werden: %s", exc)

    # ── TLS-02: Cipher-Suite ─────────────────────────────────────────────────
    if cipher:
        cname = (cipher[0] or "").upper()
        weak = [m for m in _WEAK_CIPHER_MARKERS if m in cname]
        if weak:
            findings.append(make_finding(
                "TLS-02", istzustand=f"Ausgehandelte Cipher-Suite '{cipher[0]}' enthält schwache Verfahren: {', '.join(weak)}.",
                bewertung=ROT, empfehlung="Schwache Cipher-Suiten (RC4/3DES/NULL/Export) deaktivieren.",
                rohbefund={"cipher": cipher[0]}))
        else:
            findings.append(make_finding(
                "TLS-02", istzustand=f"Ausgehandelte Cipher-Suite: '{cipher[0]}' ({cipher[2]} Bit) — keine schwachen Verfahren erkannt.",
                bewertung=KONFORM, empfehlung="Vollständige Cipher-Liste ggf. mit einem spezialisierten TLS-Scanner gegenprüfen.",
                rohbefund={"cipher": cipher[0], "bits": cipher[2]}))
        # ── TLS-05: PFS ──────────────────────────────────────────────────────
        if "ECDHE" in cname or "DHE" in cname or cipher[1] == "TLSv1.3":
            findings.append(make_finding(
                "TLS-05", istzustand=f"PFS-fähige Aushandlung ('{cipher[0]}').",
                bewertung=KONFORM, rohbefund={"cipher": cipher[0]}))
        else:
            findings.append(make_finding(
                "TLS-05", istzustand=f"Ausgehandelte Suite ohne Perfect Forward Secrecy ('{cipher[0]}').",
                bewertung=GELB, empfehlung="PFS-fähige Suiten (ECDHE/DHE) bevorzugt aushandeln.",
                rohbefund={"cipher": cipher[0]}))
    else:
        findings.append(make_finding("TLS-02", istzustand="Cipher-Suite nicht ermittelbar.", bewertung=GRAU))
        findings.append(make_finding("TLS-05", istzustand="PFS nicht ermittelbar.", bewertung=GRAU))

    # ── TLS-03 + TLS-04: Zertifikat ──────────────────────────────────────────
    if der:
        findings.extend(_eval_certificate(der, hostname, observed))
    else:
        findings.append(make_finding("TLS-03", istzustand="Zertifikat nicht lesbar.", bewertung=GRAU))
        findings.append(make_finding("TLS-04", istzustand="Zertifikat nicht lesbar.", bewertung=GRAU))

    return findings, observed


def _eval_certificate(der: bytes, hostname: str, observed: dict) -> list[Finding]:
    from cryptography import x509
    from cryptography.hazmat.primitives.asymmetric import ec, rsa

    out: list[Finding] = []
    cert = x509.load_der_x509_certificate(der)
    now = datetime.now(timezone.utc)
    not_before = cert.not_valid_before_utc
    not_after = cert.not_valid_after_utc

    # SAN / Domänenabgleich
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
    except x509.ExtensionNotFound:
        san = []
    issuer = cert.issuer.rfc4514_string()
    rest_days = (not_after - now).days
    observed["certificate"] = {
        "issuer": issuer, "not_after": not_after.isoformat(),
        "san": san, "rest_days": rest_days,
    }

    def _domain_match() -> bool:
        h = hostname.lower()
        for name in san:
            n = name.lower()
            if n == h:
                return True
            if n.startswith("*.") and h.endswith(n[1:]) and h.count(".") >= n.count("."):
                return True
        return False

    if now < not_before or now > not_after:
        out.append(make_finding(
            "TLS-03", istzustand=f"Zertifikat zeitlich ungültig (gültig {not_before.date()}–{not_after.date()}).",
            bewertung=ROT, empfehlung="Zertifikat erneuern.", rohbefund=observed["certificate"]))
    elif not _domain_match():
        out.append(make_finding(
            "TLS-03", istzustand=f"Zertifikat gültig, aber keine Domänenübereinstimmung (SAN: {', '.join(san) or '—'}).",
            bewertung=ROT, empfehlung="Zertifikat mit passendem SAN für die Domäne ausstellen.",
            rohbefund=observed["certificate"]))
    else:
        out.append(make_finding(
            "TLS-03", istzustand=f"Gültiges Zertifikat, Domänenübereinstimmung, Restlaufzeit {rest_days} Tage (Aussteller: {issuer}).",
            bewertung=KONFORM, rohbefund=observed["certificate"]))

    # TLS-04: Schlüssellänge + Signatur
    pub = cert.public_key()
    key_info = ""
    key_ok = False
    if isinstance(pub, rsa.RSAPublicKey):
        bits = pub.key_size
        key_info = f"RSA {bits} Bit"
        key_ok = bits >= 3000
    elif isinstance(pub, ec.EllipticCurvePublicKey):
        bits = pub.curve.key_size
        key_info = f"ECC {bits} Bit ({pub.curve.name})"
        key_ok = bits >= 250
    else:
        key_info = type(pub).__name__
        key_ok = True  # konservativ: unbekannt → nicht abwerten

    sig_algo = (cert.signature_hash_algorithm.name if cert.signature_hash_algorithm else "unbekannt")
    sha1 = "sha1" in sig_algo.lower()
    if sha1 or not key_ok:
        problems = []
        if not key_ok:
            problems.append(f"Schlüssellänge zu kurz ({key_info})")
        if sha1:
            problems.append("SHA-1-Signatur")
        out.append(make_finding(
            "TLS-04", istzustand="; ".join(problems) + ".",
            bewertung=ROT, empfehlung="Zertifikat mit RSA≥3000/ECC≥250 Bit und SHA-256-Signatur ausstellen.",
            rohbefund={"key": key_info, "sig": sig_algo}))
    else:
        out.append(make_finding(
            "TLS-04", istzustand=f"{key_info}, Signatur {sig_algo}.",
            bewertung=KONFORM, rohbefund={"key": key_info, "sig": sig_algo}))
    return out
