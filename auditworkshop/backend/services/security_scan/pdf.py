"""Befundbericht als PDF (fitz/PyMuPDF) im Musterbericht-Stil (Spec §5).

Enthält wie gefordert URL-Name, Screenshot und beobachtete Architektur sowie
den Geltungsbereich-Hinweis (kein Ersatz für BSI 200-2).
"""
from __future__ import annotations

import logging
from pathlib import Path

import fitz  # pymupdf

log = logging.getLogger(__name__)

_MARGIN = 50
_PAGE_W, _PAGE_H = 595, 842  # A4
_COL = {
    "konform": (0.06, 0.48, 0.34),
    "gelb": (0.70, 0.47, 0.04),
    "rot": (0.74, 0.16, 0.23),
    "grau": (0.39, 0.43, 0.49),
}
_TEXT = (0.12, 0.16, 0.22)
_LIGHT = (0.43, 0.47, 0.53)
_OVERALL_LABEL = {"konform": "konform", "gelb": "Abweichung mit erhöhtem Risiko", "kritisch": "kritisch"}


class _R:
    def __init__(self, doc: fitz.Document):
        self.doc = doc
        self.page = doc.new_page(width=_PAGE_W, height=_PAGE_H)
        self.y = _MARGIN

    def _space(self, need: float) -> None:
        if self.y + need > _PAGE_H - _MARGIN:
            self.page = self.doc.new_page(width=_PAGE_W, height=_PAGE_H)
            self.y = _MARGIN

    def h1(self, text: str) -> None:
        self._space(34)
        self.page.insert_text((_MARGIN, self.y + 16), text, fontsize=17, fontname="hebo", color=_TEXT)
        self.y += 30

    def h2(self, text: str, color=_TEXT) -> None:
        self._space(26)
        self.page.insert_text((_MARGIN, self.y + 13), text, fontsize=13, fontname="hebo", color=color)
        self.y += 24

    def para(self, text: str, size: int = 10, color=_TEXT, gap: int = 6) -> None:
        used = _measure(text, size)
        # Vor dem Schreiben paginieren, damit die Textbox finit/nicht-leer ist.
        self._space(min(used, _PAGE_H - 2 * _MARGIN))
        rect = fitz.Rect(_MARGIN, self.y, _PAGE_W - _MARGIN, _PAGE_H - _MARGIN)
        leftover = self.page.insert_textbox(rect, text, fontsize=size, fontname="helv", color=color, align=0)
        if leftover < 0:
            # Passte nicht ganz → neue Seite, ganzen Absatz erneut.
            self.page = self.doc.new_page(width=_PAGE_W, height=_PAGE_H)
            self.y = _MARGIN
            rect = fitz.Rect(_MARGIN, self.y, _PAGE_W - _MARGIN, _PAGE_H - _MARGIN)
            self.page.insert_textbox(rect, text, fontsize=size, fontname="helv", color=color, align=0)
        self.y += used + gap

    def kv(self, key: str, val: str) -> None:
        self._space(16)
        self.page.insert_text((_MARGIN, self.y + 10), key, fontsize=10, fontname="hebo", color=_TEXT)
        self.page.insert_text((_MARGIN + 150, self.y + 10), val, fontsize=10, fontname="helv", color=_TEXT)
        self.y += 16

    def badge(self, label: str, bewertung: str) -> None:
        color = _COL.get(bewertung, _LIGHT)
        w = 8 + len(label) * 5.5
        self._space(20)
        self.page.draw_rect(fitz.Rect(_MARGIN, self.y, _MARGIN + w, self.y + 15), color=color, fill=color)
        self.page.insert_text((_MARGIN + 5, self.y + 11), label, fontsize=9, fontname="hebo", color=(1, 1, 1))
        self.y += 20

    def image(self, png_path: str, max_h: int = 360) -> None:
        try:
            pix = fitz.Pixmap(png_path)
            w, h = pix.width, pix.height
            avail_w = _PAGE_W - 2 * _MARGIN
            scale = min(avail_w / w, max_h / h)
            dw, dh = w * scale, h * scale
            self._space(dh + 10)
            self.page.insert_image(fitz.Rect(_MARGIN, self.y, _MARGIN + dw, self.y + dh), filename=png_path)
            self.y += dh + 10
        except Exception:  # noqa: BLE001
            log.exception("Bild-Embed fehlgeschlagen: %s", png_path)
            self.para("[Bild nicht verfügbar]", color=_LIGHT)


def _measure(text: str, size: int) -> float:
    # grobe Zeilenhöhen-Abschätzung: ~ (Zeichen / Zeichen-pro-Zeile) * Zeilenhöhe
    cpl = max(1, int((_PAGE_W - 2 * _MARGIN) / (size * 0.5)))
    lines = sum(max(1, (len(seg) // cpl) + 1) for seg in text.split("\n"))
    return lines * (size + 3)


def render_security_pdf(run) -> bytes:
    doc = fitz.open()
    r = _R(doc)

    # ── Kopf ─────────────────────────────────────────────────────────────────
    r.h1("Befundbericht zur technischen Sicherheitsprüfung")
    r.para("Kernanforderung 6 — ISMS-Systemprüfung · nicht-intrusive technische Prüfung", size=10, color=_LIGHT)
    r.y += 4
    r.kv("Prüfgegenstand:", run.target_url or "")
    r.kv("Prüfzeitpunkt:", (run.finished_at or run.started_at).strftime("%d.%m.%Y, %H:%M Uhr") if (run.finished_at or run.started_at) else "—")
    r.kv("Prüfumfang:", "Von außen erreichbare Konfiguration inkl. Portscan + passiver Schwachstellenindikation")
    r.kv("Berechtigung:", f"Selbstbestätigung des Prüfers ({run.authorization_declared_by or '—'})")
    r.kv("Bezugsrahmen:", "APP.3.1, NET.3.3, BSI TR-02102-2")
    r.y += 8

    # ── Zusammenfassung ──────────────────────────────────────────────────────
    r.h2("Zusammenfassung")
    total = run.count_konform + run.count_gelb + run.count_rot + run.count_grau
    r.para(
        f"Die Prüfung hat {total} Prüfgegenstände bewertet: {run.count_konform} konform, "
        f"{run.count_gelb} Abweichung mit erhöhtem Risiko, {run.count_rot} kritische Abweichung "
        f"und {run.count_grau} nicht prüfbar. Die Gesamtbewertung richtet sich nach der "
        f"schwerwiegendsten Einzelabweichung (Prinzip der schwächsten Stelle).")
    r.badge(f"Gesamtbewertung: {_OVERALL_LABEL.get(run.overall, run.overall)}",
            "rot" if run.overall == "kritisch" else run.overall)

    # ── Einzelbefunde ────────────────────────────────────────────────────────
    r.h2("Einzelbefunde")
    findings = run.findings or []
    last_group = None
    for f in findings:
        grp = f.get("gruppe", "")
        if grp and grp != last_group:
            r.y += 4
            r.para(grp, size=11, color=_LIGHT, gap=2)
            last_group = grp
        title = f"{f.get('pruef_id')} — {f.get('titel', '')}"
        r._space(18)
        r.page.insert_text((_MARGIN, r.y + 11), title, fontsize=10.5, fontname="hebo", color=_TEXT)
        r.y += 16
        r.badge(f.get("bewertung_label", f.get("bewertung", "")), f.get("bewertung", "grau"))
        if f.get("istzustand"):
            r.para("Befund: " + f["istzustand"], size=9.5)
        if f.get("empfehlung"):
            r.para("Empfehlung: " + f["empfehlung"], size=9.5, color=_LIGHT)
        r.y += 4

    # ── Screenshot ───────────────────────────────────────────────────────────
    if run.screenshot_path and Path(run.screenshot_path).exists():
        r.page = doc.new_page(width=_PAGE_W, height=_PAGE_H)
        r.y = _MARGIN
        r.h2("Screenshot der Zielseite")
        r.para(f"Gerenderte Ansicht von {run.target_url} zum Prüfzeitpunkt.", size=9.5, color=_LIGHT)
        r.image(run.screenshot_path, max_h=520)

    # ── Architektur ──────────────────────────────────────────────────────────
    if run.architecture_path and Path(run.architecture_path).exists():
        r.page = doc.new_page(width=_PAGE_W, height=_PAGE_H)
        r.y = _MARGIN
        r.h2("Beobachtete Architektur")
        r.image(run.architecture_path, max_h=420)

    # ── Geltungsbereich ──────────────────────────────────────────────────────
    r.y += 8
    r.h2("Hinweis zum Geltungsbereich")
    r.para(
        "Dieser Bericht bewertet ausschließlich die technisch von außen messbare Konfiguration. "
        "Er trifft keine Aussage über die Erfüllung organisatorischer, prozessualer und "
        "dokumentarischer Anforderungen des IT-Grundschutzes und ersetzt keine "
        "Grundschutz-Konformitätsprüfung im Sinne des BSI-Standards 200-2. Die CVE-Indikation "
        "(VUL-02) ist keine bestätigte Verwundbarkeit; deren Ausnutzbarkeit ist nur per "
        "gesondert beauftragtem Penetrationstest verifizierbar.", size=9.5, color=_LIGHT)

    out = doc.tobytes()
    doc.close()
    return out
