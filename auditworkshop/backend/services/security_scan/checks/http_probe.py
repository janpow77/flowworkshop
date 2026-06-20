"""HTTP-Prüfungen — Sicherheitsheader (HDR), Cookies (COO), HTTPS-Erzwingung
(NET-01) und Versionsbanner (VUL-01). Nicht-intrusiv: nur reguläre GET-Anfragen.
"""
from __future__ import annotations

import logging
import re

import httpx

from ..report import GELB, GRAU, KONFORM, ROT, Finding, make_finding

log = logging.getLogger(__name__)

_VERSION_RE = re.compile(r"\d+\.\d+(\.\d+)?")


def probe_http(host: str, timeout: float) -> tuple[list[Finding], dict]:
    findings: list[Finding] = []
    observed: dict = {"server": None, "powered_by": None, "headers": {}, "cookies": []}

    https_url = f"https://{host}/"
    resp = None
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, verify=False) as client:
            resp = client.get(https_url, headers={"User-Agent": "ISMS-Pruefwerkzeug/1.0 (nicht-intrusiv)"})
    except Exception as exc:  # noqa: BLE001
        log.warning("HTTPS-Probe fehlgeschlagen (%s): %s", https_url, exc)

    if resp is None:
        for pid in ("HDR-01", "HDR-02", "HDR-03", "HDR-04", "HDR-05", "HDR-06", "COO-01", "COO-02", "COO-03", "VUL-01"):
            findings.append(make_finding(pid, istzustand="Nicht prüfbar — HTTPS nicht erreichbar.", bewertung=GRAU))
        findings.append(_check_https_redirect(host, timeout))
        return findings, observed

    headers = {k.lower(): v for k, v in resp.headers.items()}
    observed["headers"] = {k: headers.get(k) for k in (
        "strict-transport-security", "content-security-policy", "x-content-type-options",
        "x-frame-options", "referrer-policy", "server", "x-powered-by")}

    # ── HDR-01: HSTS ─────────────────────────────────────────────────────────
    hsts = headers.get("strict-transport-security")
    if not hsts:
        findings.append(make_finding("HDR-01", istzustand="Header Strict-Transport-Security nicht gesetzt.",
                                     bewertung=ROT, empfehlung="HSTS mit max-age≥31536000 und includeSubDomains setzen."))
    else:
        m = re.search(r"max-age\s*=\s*(\d+)", hsts)
        max_age = int(m.group(1)) if m else 0
        if max_age >= 31536000:
            findings.append(make_finding("HDR-01", istzustand=f"HSTS gesetzt (max-age={max_age}).",
                                         bewertung=KONFORM, rohbefund={"hsts": hsts}))
        else:
            findings.append(make_finding("HDR-01", istzustand=f"HSTS gesetzt, aber max-age={max_age} < 31536000.",
                                         bewertung=GELB, empfehlung="max-age auf mindestens ein Jahr (31536000) anheben, includeSubDomains ergänzen.",
                                         rohbefund={"hsts": hsts}))

    # ── HDR-02: CSP ──────────────────────────────────────────────────────────
    csp = headers.get("content-security-policy")
    findings.append(make_finding("HDR-02",
                                 istzustand="Content-Security-Policy gesetzt." if csp else "Content-Security-Policy nicht gesetzt.",
                                 bewertung=KONFORM if csp else GELB,
                                 empfehlung="" if csp else "Restriktive Content-Security-Policy ergänzen.",
                                 rohbefund={"csp": csp}))

    # ── HDR-03: X-Content-Type-Options ───────────────────────────────────────
    xcto = (headers.get("x-content-type-options") or "").lower()
    findings.append(make_finding("HDR-03",
                                 istzustand="nosniff gesetzt." if "nosniff" in xcto else "X-Content-Type-Options (nosniff) nicht gesetzt.",
                                 bewertung=KONFORM if "nosniff" in xcto else GELB,
                                 empfehlung="" if "nosniff" in xcto else "Header 'X-Content-Type-Options: nosniff' setzen."))

    # ── HDR-04: Clickjacking-Schutz ──────────────────────────────────────────
    xfo = headers.get("x-frame-options")
    frame_anc = csp and "frame-ancestors" in csp.lower()
    if xfo or frame_anc:
        findings.append(make_finding("HDR-04", istzustand=f"Clickjacking-Schutz gesetzt ({'X-Frame-Options' if xfo else 'CSP frame-ancestors'}).",
                                     bewertung=KONFORM))
    else:
        findings.append(make_finding("HDR-04", istzustand="Kein Clickjacking-Schutz (weder X-Frame-Options noch CSP frame-ancestors).",
                                     bewertung=GELB, empfehlung="X-Frame-Options: DENY/SAMEORIGIN oder CSP frame-ancestors setzen."))

    # ── HDR-05: Referrer-Policy ──────────────────────────────────────────────
    ref = headers.get("referrer-policy")
    findings.append(make_finding("HDR-05",
                                 istzustand=f"Referrer-Policy gesetzt ({ref})." if ref else "Referrer-Policy nicht gesetzt.",
                                 bewertung=KONFORM if ref else GELB,
                                 empfehlung="" if ref else "Restriktive Referrer-Policy (z.B. strict-origin-when-cross-origin) setzen."))

    # ── HDR-06 + VUL-01: Server-/Versionskennung ─────────────────────────────
    server = headers.get("server")
    powered = headers.get("x-powered-by")
    observed["server"] = server
    observed["powered_by"] = powered
    banners = [b for b in (server, powered) if b]
    has_version = any(_VERSION_RE.search(b) for b in banners)
    if not banners:
        findings.append(make_finding("HDR-06", istzustand="Keine Server-/Versionskennung preisgegeben.", bewertung=KONFORM))
        findings.append(make_finding("VUL-01", istzustand="Kein Versionsbanner preisgegeben.", bewertung=KONFORM))
    elif has_version:
        findings.append(make_finding("HDR-06", istzustand=f"Produkt-/Versionskennung preisgegeben: {', '.join(banners)}.",
                                     bewertung=GELB, empfehlung="Produkt-/Versionsinformationen in Server-/X-Powered-By-Headern unterdrücken.",
                                     rohbefund={"server": server, "powered_by": powered}))
        findings.append(make_finding("VUL-01", istzustand=f"Versionsbanner erkannt: {', '.join(banners)}.",
                                     bewertung=GELB, empfehlung="Versionsbanner unterdrücken; Komponenten aktuell halten.",
                                     rohbefund={"server": server, "powered_by": powered}))
    else:
        findings.append(make_finding("HDR-06", istzustand=f"Produktkennung ohne Version preisgegeben: {', '.join(banners)}.",
                                     bewertung=GELB, empfehlung="Auch Produktkennung möglichst reduzieren.",
                                     rohbefund={"server": server, "powered_by": powered}))
        findings.append(make_finding("VUL-01", istzustand=f"Produktkennung ohne Version: {', '.join(banners)}.", bewertung=KONFORM,
                                     rohbefund={"server": server, "powered_by": powered}))

    # ── COO-01..03: Cookies ──────────────────────────────────────────────────
    set_cookies = resp.headers.get_list("set-cookie") if hasattr(resp.headers, "get_list") else []
    observed["cookies"] = set_cookies
    findings.extend(_check_cookies(set_cookies))

    # ── NET-01: HTTPS-Erzwingung ─────────────────────────────────────────────
    findings.append(_check_https_redirect(host, timeout))
    return findings, observed


def _check_cookies(set_cookies: list[str]) -> list[Finding]:
    if not set_cookies:
        msg = "Keine Cookies gesetzt — Attribute nicht prüfbar."
        return [make_finding(pid, istzustand=msg, bewertung=GRAU) for pid in ("COO-01", "COO-02", "COO-03")]

    insecure, no_httponly, no_samesite = [], [], []
    for raw in set_cookies:
        low = raw.lower()
        name = raw.split("=", 1)[0].strip()
        if "secure" not in low:
            insecure.append(name)
        if "httponly" not in low:
            no_httponly.append(name)
        if "samesite" not in low:
            no_samesite.append(name)

    out = []
    out.append(make_finding("COO-01",
                            istzustand="Alle Cookies mit Secure." if not insecure else f"Cookies ohne Secure: {', '.join(insecure)}.",
                            bewertung=KONFORM if not insecure else ROT,
                            empfehlung="" if not insecure else "Secure-Attribut bei allen Cookies setzen.",
                            rohbefund={"insecure": insecure}))
    out.append(make_finding("COO-02",
                            istzustand="Sitzungs-Cookies mit HttpOnly." if not no_httponly else f"Cookies ohne HttpOnly: {', '.join(no_httponly)}.",
                            bewertung=KONFORM if not no_httponly else GELB,
                            empfehlung="" if not no_httponly else "HttpOnly bei Sitzungs-Cookies setzen.",
                            rohbefund={"no_httponly": no_httponly}))
    out.append(make_finding("COO-03",
                            istzustand="Cookies mit SameSite." if not no_samesite else f"Cookies ohne SameSite: {', '.join(no_samesite)}.",
                            bewertung=KONFORM if not no_samesite else GELB,
                            empfehlung="" if not no_samesite else "SameSite=Strict oder Lax setzen.",
                            rohbefund={"no_samesite": no_samesite}))
    return out


def _check_https_redirect(host: str, timeout: float) -> Finding:
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False, verify=False) as client:
            r = client.get(f"http://{host}/", headers={"User-Agent": "ISMS-Pruefwerkzeug/1.0"})
        loc = r.headers.get("location", "")
        if 300 <= r.status_code < 400 and loc.lower().startswith("https://"):
            return make_finding("NET-01", istzustand=f"HTTP wird per {r.status_code} auf HTTPS weitergeleitet.",
                                bewertung=KONFORM, rohbefund={"status": r.status_code, "location": loc})
        if 300 <= r.status_code < 400:
            return make_finding("NET-01", istzustand=f"HTTP-Weiterleitung ({r.status_code}), aber nicht auf HTTPS ({loc}).",
                                bewertung=ROT, empfehlung="Weiterleitung mit 301 auf HTTPS einrichten.",
                                rohbefund={"status": r.status_code, "location": loc})
        return make_finding("NET-01", istzustand=f"HTTP liefert Inhalt ohne HTTPS-Weiterleitung (Status {r.status_code}).",
                            bewertung=ROT, empfehlung="Serverseitige 301-Weiterleitung von HTTP auf HTTPS einrichten.",
                            rohbefund={"status": r.status_code})
    except Exception as exc:  # noqa: BLE001
        return make_finding("NET-01", istzustand="HTTP-Port nicht erreichbar — Weiterleitung nicht prüfbar (kann konform sein).",
                            bewertung=GRAU, rohbefund={"error": str(exc)})
