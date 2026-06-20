"""Rendert die *beobachtete* Architektur der Zielanwendung als PNG (Pillow).

Zeigt die von außen erkannte Kette: Prüfer → Domain/IP → TLS-Terminierung →
Webserver(Produkt/Version) → erreichbare Ports/Dienste, plus den Status der
Sicherheitsheader. Boxen werden nach Ampel eingefärbt. Keine Wertung über das
hinaus, was beobachtet wurde.
"""
from __future__ import annotations

import logging
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from .report import GELB, GRAU, KONFORM, ROT

log = logging.getLogger(__name__)

_COLORS = {
    KONFORM: (16, 122, 87),    # emerald
    GELB: (180, 120, 10),      # amber
    ROT: (190, 40, 60),        # rose
    GRAU: (100, 110, 125),     # slate
}
_BG = (248, 250, 252)
_BOX_FILL = (255, 255, 255)
_TEXT = (30, 41, 59)
_ARROW = (120, 130, 145)


def _font(size: int):
    for name in ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:  # noqa: BLE001
            continue
    return ImageFont.load_default()


def _area_severity(findings_by_id: dict, ids: list[str]) -> str:
    sev = [findings_by_id[i].bewertung for i in ids if i in findings_by_id]
    if ROT in sev:
        return ROT
    if GELB in sev:
        return GELB
    if all(s == GRAU for s in sev) and sev:
        return GRAU
    return KONFORM


def render_architecture_png(host: str, observed: dict, findings_by_id: dict) -> bytes:
    W, H = 1000, 560
    img = Image.new("RGB", (W, H), _BG)
    d = ImageDraw.Draw(img)
    f_title = _font(22)
    f_box = _font(15)
    f_small = _font(12)

    d.text((30, 22), "Beobachtete Architektur (von außen)", font=f_title, fill=_TEXT)
    d.text((30, 52), f"Ziel: {host}", font=f_small, fill=_TEXT)

    cert = (observed.get("tls") or {}).get("certificate") or {}
    protos = ", ".join((observed.get("tls") or {}).get("protocols") or []) or "—"
    http_obs = observed.get("http") or {}
    server = http_obs.get("server") or "unbekannt"
    open_ports = (observed.get("ports") or {}).get("open") or []
    extra_ports = (observed.get("ports") or {}).get("extra") or []

    # Box-Kette (x, y, w, h, titel, zeilen, severity-ids)
    boxes = [
        (30, 110, 150, 90, "Prüfer", ["nicht-intrusiv"], []),
        (210, 110, 200, 90, "Domain / TLS", [f"Protokolle: {protos}", f"Cert: {(cert.get('rest_days') if cert else '—')} Tage"],
         ["TLS-01", "TLS-02", "TLS-03", "TLS-04", "TLS-05"]),
        (440, 110, 240, 90, "Webserver", [server[:34]], ["HDR-06", "VUL-01", "VUL-02"]),
        (710, 110, 260, 90, "Erreichbare Ports",
         [", ".join(str(p) for p in open_ports[:8]) or "—", (f"+{len(extra_ports)} über Zweck" if extra_ports else "nur 80/443")],
         ["NET-02", "NET-04"]),
    ]
    cy = 110 + 45
    for (x, y, w, h, title, lines, ids) in boxes:
        sev = _area_severity(findings_by_id, ids) if ids else GRAU
        color = _COLORS[sev]
        d.rounded_rectangle([x, y, x + w, y + h], radius=10, fill=_BOX_FILL, outline=color, width=3)
        d.text((x + 12, y + 10), title, font=f_box, fill=color)
        for i, ln in enumerate(lines):
            d.text((x + 12, y + 36 + i * 18), ln, font=f_small, fill=_TEXT)
        # Pfeil zum nächsten
        if x + w < 690:
            d.line([x + w, cy, x + w + 30, cy], fill=_ARROW, width=2)
            d.polygon([(x + w + 30, cy), (x + w + 22, cy - 5), (x + w + 22, cy + 5)], fill=_ARROW)

    # Untere Reihe: Sicherheits-Schichten (Header / Cookies / HTTPS-Erzwingung)
    layers = [
        (30, 250, "Sicherheitsheader", ["HDR-01", "HDR-02", "HDR-03", "HDR-04", "HDR-05"]),
        (370, 250, "Cookies", ["COO-01", "COO-02", "COO-03"]),
        (640, 250, "HTTPS-Erzwingung", ["NET-01"]),
    ]
    for (x, y, title, ids) in layers:
        sev = _area_severity(findings_by_id, ids)
        color = _COLORS[sev]
        w = 300 if title == "Sicherheitsheader" else 230
        d.rounded_rectangle([x, y, x + w, y + 70], radius=10, fill=_BOX_FILL, outline=color, width=3)
        d.text((x + 12, y + 10), title, font=f_box, fill=color)
        d.text((x + 12, y + 38), f"Status: {sev}", font=f_small, fill=_TEXT)

    # Legende
    ly = 360
    d.text((30, ly), "Ampel:", font=f_small, fill=_TEXT)
    for i, (sev, label) in enumerate([(KONFORM, "konform"), (GELB, "erhöhtes Risiko"), (ROT, "kritisch"), (GRAU, "nicht prüfbar")]):
        bx = 90 + i * 200
        d.rectangle([bx, ly, bx + 16, ly + 14], fill=_COLORS[sev])
        d.text((bx + 22, ly), label, font=f_small, fill=_TEXT)

    d.text((30, H - 30), "Darstellung der von außen messbaren Konfiguration · keine Aussage über organisatorische Anforderungen (BSI 200-2).",
           font=_font(11), fill=(110, 120, 135))

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
