"""VUL-02 — CVE-Indikation via OSV.dev.

Gleicht ein aus dem Versionsbanner erkanntes Produkt+Version gegen die
OSV.dev-Schwachstellendatenbank ab. Ausdrücklich nur **Indikation**: das
Werkzeug löst keine Schwachstelle aus und bestätigt sie nicht. Die tatsächliche
Ausnutzbarkeit ist nur per gesondert beauftragtem Penetrationstest verifizierbar.
"""
from __future__ import annotations

import logging
import re

import httpx

from config import OSV_API_URL
from ..report import GELB, GRAU, ROT, Finding, make_finding

log = logging.getLogger(__name__)

_BANNER_RE = re.compile(r"([A-Za-z][A-Za-z0-9_\-]+)[/ ]v?(\d+\.\d+(?:\.\d+)?)")
# Bekannte Produkt-Banner → OSV-Paketname (heuristisch).
_PRODUCT_ALIASES = {
    "nginx": "nginx", "apache": "apache", "httpd": "apache",
    "openssl": "openssl", "php": "php", "iis": "iis", "tomcat": "tomcat",
}


def _parse_banner(banner: str | None) -> tuple[str, str] | None:
    if not banner:
        return None
    m = _BANNER_RE.search(banner)
    if not m:
        return None
    product = m.group(1).lower()
    return _PRODUCT_ALIASES.get(product, product), m.group(2)


def _osv_query(name: str, version: str, timeout: float) -> list[dict]:
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(f"{OSV_API_URL}/v1/query",
                               json={"version": version, "package": {"name": name}})
            resp.raise_for_status()
            return resp.json().get("vulns", []) or []
    except Exception as exc:  # noqa: BLE001
        log.warning("OSV-Abfrage fehlgeschlagen (%s %s): %s", name, version, exc)
        return []


def check_cve(observed_http: dict, timeout: float) -> Finding:
    banners = [observed_http.get("server"), observed_http.get("powered_by")]
    parsed = [p for b in banners for p in [_parse_banner(b)] if p]

    if not parsed:
        return make_finding("VUL-02",
                            istzustand="Keine eindeutige Produkt-/Versionskennung erkannt — kein CVE-Abgleich möglich.",
                            bewertung=GRAU,
                            empfehlung="Manueller Abgleich der eingesetzten Komponenten gegen eine Schwachstellendatenbank.")

    hits: list[dict] = []
    for name, version in parsed:
        for v in _osv_query(name, version, timeout):
            hits.append({"product": name, "version": version, "id": v.get("id"),
                         "summary": (v.get("summary") or "")[:160]})

    if hits:
        ids = ", ".join(sorted({h["id"] for h in hits if h.get("id")})[:8])
        return make_finding("VUL-02",
                            istzustand=f"Erkannte Komponente(n) {', '.join(f'{n} {v}' for n, v in parsed)} mit dokumentierten Schwachstellen abgeglichen — Treffer in der Schwachstellendatenbank: {ids}.",
                            bewertung=ROT,
                            empfehlung="Komponente auf eine bereinigte Version aktualisieren. Hinweis: Dies ist eine INDIKATION aus dem Versionsbanner — die tatsächliche Ausnutzbarkeit lässt sich ausschließlich im Rahmen eines gesondert und schriftlich beauftragten Penetrationstests verifizieren, der bewusst nicht Teil dieser Prüfung ist.",
                            rohbefund={"hits": hits, "parsed": parsed})

    return make_finding("VUL-02",
                        istzustand=f"Erkannte Komponente(n) {', '.join(f'{n} {v}' for n, v in parsed)} — kein Treffer in der abgefragten Schwachstellendatenbank (OSV).",
                        bewertung=GELB,
                        empfehlung="Versionsbanner unterdrücken (verringert die Angriffsfläche) und Komponenten aktuell halten. Ein fehlender OSV-Treffer ist kein Freibrief — vollständige CVE-Abdeckung nicht garantiert.",
                        rohbefund={"parsed": parsed})
