"""
flowworkshop · services/state_aid_audit_pdf.py

Erzeugt den Cross-Register-Prüfbericht als PDF mit pymupdf.

Stilvorgaben:
- A4-Hochformat, Helvetica (built-in pymupdf)
- Header auf jeder Seite: 'Cross-Register-Prüfbericht — {query}' + Seitenzahl
- Footer: 'Erstellt am ... · Auftraggeber: ...'
- Tabellen mit klaren Linien, alternierender Zeilenfarbe (grau)
- KEINE Ampeln, KEINE farbigen Severity-Marker, KEIN Risiko-Score
- Pflichthinweis (Plan §13) am Ende des Berichts

Mai 2026 — Erweiterung:
- Aktenzeichen entfernt (war ein Prüfer-Eingabefeld, ohne Mehrwert).
- Pro Sektion eine vollständige Detail-Tabelle (max. 40 Zeilen).
- Eigener Abschnitt 'Quellen und Datenstand' vor dem Anhang.
- Disclaimer-Block ('Hinweise zur Anwendung') im Anhang.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # nur für Type-Hints, vermeidet Import-Loop
    from services.state_aid_audit_report import AuditReportData

log = logging.getLogger(__name__)

# ── Layout-Konstanten ────────────────────────────────────────────────────────

PAGE_WIDTH = 595.0      # A4-Hochformat
PAGE_HEIGHT = 842.0
MARGIN = 50.0
USABLE_WIDTH = PAGE_WIDTH - 2 * MARGIN
HEADER_BOTTOM = 30.0    # y-Pos. vom Header-Trennstrich
FOOTER_TOP = PAGE_HEIGHT - 46.0  # über dieser y-Linie ist Footer (2 Zeilen)

# Farben (RGB 0..1) — bewusst neutral, keine Severity-Markierungen
COL_TEXT = (0.10, 0.10, 0.10)
COL_HEADER = (0.20, 0.20, 0.20)
COL_LIGHT = (0.55, 0.55, 0.55)
COL_LINE = (0.75, 0.75, 0.75)
COL_ROW_ALT = (0.96, 0.96, 0.96)
COL_LINK = (0.10, 0.30, 0.70)  # für klickbare URLs in Tabellen-Zellen


def render_audit_report_pdf(
    data: "AuditReportData",
    *,
    include_map: bool = False,
) -> bytes:
    """Liefert das PDF als Bytes-Stream.

    Strikt faktisch — keine Bewertung, kein Risiko-Score.

    ``include_map``: wenn True, wird eine eigene Karten-Seite (OSM-Tiles +
    NUTS-Outline + Marker je Treffer-Region) nach der State-Aid-Sektion
    eingefügt. Cover-Block weist auf den einmaligen OSM-Tile-Fetch hin.
    """
    import fitz  # type: ignore

    doc = fitz.open()
    # Karten-Flag wird über das State-Objekt durchgereicht, damit der
    # Cover-Renderer den OSM-Hinweis nur dann zeigt, wenn die Karte aktiv ist.
    state = _RenderState(doc=doc, data=data, include_map=include_map)

    # ── Reihenfolge der Seiten ───────────────────────────────────────────
    # Pageflow-Strategie (Mai 2026):
    #  - HARD break (state.new_page): Cover→Summary, vor Karte, vor Anhang
    #  - SOFT break (section_break): andere Sektionen teilen sich Seiten,
    #    wenn genug Platz übrig ist
    _render_cover(state)
    state.new_page()           # Cover ist visuell eigenständig
    _render_summary(state)
    state.section_break(min_space=240)
    _render_state_aid_section(state)
    if include_map:
        state.new_page()       # Karte braucht volle Seite
        _render_map_section(state)
    state.section_break(min_space=260)
    _render_beneficiaries_section(state)
    state.section_break(min_space=200)
    _render_sanctions_section(state)
    state.section_break(min_space=200)
    _render_cross_references(state)
    semantic_refs_present = any(
        getattr(r, "type", None) in _SEMANTIC_REF_TYPES
        for r in (data.cross_references or [])
    )
    if semantic_refs_present:
        state.section_break(min_space=240)
        _render_semantic_neighbors(state)
    if getattr(data, "llm_verification", None) is not None:
        state.section_break(min_space=260)
        _render_llm_verification(state)
    if getattr(data, "corporate_group", None) is not None:
        state.section_break(min_space=260)
        _render_corporate_group_section(state)
    if getattr(data, "persons_check", None) is not None:
        state.section_break(min_space=220)
        _render_persons_check_section(state)
    state.section_break(min_space=200)
    _render_sources_explanation(state)
    if getattr(data, "coverage", None) is not None:
        state.section_break(min_space=220)
        _render_coverage_section(state)
    state.new_page()           # Anhang als eigene Seite (formal)
    _render_appendix(state)

    # Header/Footer auf alle Seiten zeichnen — passiert in `state.new_page`
    # bzw. in finalize_headers nach allem Inhalt, damit Seitenzahlen
    # die endgültige Anzahl widerspiegeln.
    state.finalize_headers_footers()

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


# ── Render-State ──────────────────────────────────────────────────────────────


class _RenderState:
    """Hält aktuelle Seite, Cursor und Layout-Helfer."""

    def __init__(self, *, doc, data: "AuditReportData", include_map: bool = False):
        self.doc = doc
        self.data = data
        self.include_map = include_map
        self.page = None
        self.cursor_y = MARGIN + 20  # Platz für Header
        self._page_indices: list[int] = []
        # Header-Daten
        self.title = f"Cross-Register-Prüfbericht — {data.query}"
        # Footer-Daten — Auftraggeber/Prüfer werden im PDF nicht mehr ausgegeben
        # (bleiben aber im Audit-Log persistiert). Mai 2026.
        issued = data.issued_at.strftime("%Y-%m-%d %H:%M UTC") if data.issued_at else "—"
        self.footer_text = (
            f"Erstellt am {issued} · Kostenfreies Demo-Angebot · keine Gewähr"
        )
        self.new_page()

    def new_page(self) -> None:
        import fitz  # type: ignore
        self.page = self.doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        self._page_indices.append(self.page.number)
        self.cursor_y = MARGIN + 30  # erste Zeile unter Header

    def ensure_space(self, needed: float) -> None:
        """Bricht auf neue Seite, wenn nicht genug Platz mehr da ist."""
        if self.cursor_y + needed > FOOTER_TOP - 10:
            self.new_page()

    def section_break(self, *, min_space: float = 200, extra: float = 22) -> None:
        """Sanfter Sektionsumbruch.

        Statt eines Zwangs-Umbruchs (``new_page``) wird nur dann eine neue
        Seite begonnen, wenn weniger als ``min_space`` Punkte Restplatz auf
        der aktuellen Seite übrig sind. Andernfalls wird nur ein vertikaler
        Abstand (``extra``) eingefügt, damit kleinere Sektionen sich eine
        Seite teilen können. Header und Footer werden in
        ``finalize_headers_footers`` für die finale Seitenzahl gerendert.
        """
        if self.cursor_y + min_space > FOOTER_TOP - 10:
            self.new_page()
        else:
            self.cursor_y += extra

    def write_text(
        self, text: str, *,
        size: float = 9.5, bold: bool = False,
        color: tuple = COL_TEXT, indent: float = 0.0,
    ) -> None:
        """Schreibt eine Textzeile, bricht ggf. auf neue Seite."""
        line_h = size + 3
        self.ensure_space(line_h)
        font = "helv" if not bold else "hebo"
        try:
            self.page.insert_text(
                (MARGIN + indent, self.cursor_y),
                text,
                fontsize=size,
                fontname=font,
                color=color,
            )
        except Exception:  # noqa: BLE001
            self.page.insert_text(
                (MARGIN + indent, self.cursor_y),
                text,
                fontsize=size,
                color=color,
            )
        self.cursor_y += line_h

    def write_paragraph(
        self, text: str, *,
        size: float = 9.5, bold: bool = False,
        color: tuple = COL_TEXT, indent: float = 0.0,
        max_width: float | None = None,
    ) -> None:
        """Schreibt mehrzeiligen Text mit einfachem Word-Wrap."""
        if not text:
            return
        max_w = max_width if max_width is not None else (USABLE_WIDTH - indent)
        # Sehr einfaches Word-Wrap: ~CHARS_PER_LINE basierend auf Schriftgröße
        chars_per_line = max(40, int(max_w / (size * 0.52)))
        for raw_line in str(text).splitlines() or [str(text)]:
            words = raw_line.split()
            if not words:
                self.cursor_y += size * 0.6
                continue
            line = ""
            for w in words:
                candidate = (line + " " + w).strip()
                if len(candidate) <= chars_per_line:
                    line = candidate
                else:
                    if line:
                        self.write_text(line, size=size, bold=bold, color=color, indent=indent)
                    line = w
            if line:
                self.write_text(line, size=size, bold=bold, color=color, indent=indent)

    def write_h1(self, text: str) -> None:
        self.cursor_y += 6
        self.write_text(text, size=18, bold=True, color=COL_HEADER)
        self.cursor_y += 4

    def write_h2(self, text: str) -> None:
        self.cursor_y += 8
        self.write_text(text, size=13, bold=True, color=COL_HEADER)
        self.cursor_y += 2

    def write_h3(self, text: str) -> None:
        self.cursor_y += 4
        self.write_text(text, size=11, bold=True, color=COL_HEADER)

    def hr(self) -> None:
        self.ensure_space(8)
        self.page.draw_line(
            (MARGIN, self.cursor_y),
            (PAGE_WIDTH - MARGIN, self.cursor_y),
            color=COL_LINE, width=0.5,
        )
        self.cursor_y += 8

    def write_kv(self, key: str, value: str, *, key_width: float = 110) -> None:
        """Schreibt ein Key-Value-Paar in zwei Spalten."""
        line_h = 12
        self.ensure_space(line_h)
        try:
            self.page.insert_text(
                (MARGIN, self.cursor_y), key,
                fontsize=9.5, fontname="hebo", color=COL_HEADER,
            )
            self.page.insert_text(
                (MARGIN + key_width, self.cursor_y), str(value or "—"),
                fontsize=9.5, fontname="helv", color=COL_TEXT,
            )
        except Exception:  # noqa: BLE001
            self.page.insert_text((MARGIN, self.cursor_y), f"{key}  {value}",
                                   fontsize=9.5)
        self.cursor_y += line_h

    def write_table(
        self, headers: list[str], rows: list[list[str]], *,
        col_widths: list[float] | None = None,
        max_rows: int = 200,
        cell_links: list[list[str | None]] | None = None,
        total_row: list[str] | None = None,
        footer_note: str | None = None,
    ) -> None:
        """Einfache Tabelle mit alternierender Zeilenfarbe und Linien.

        Bei Page-Break wird der Tabellen-Header auf der neuen Seite wiederholt.
        Lange Zellen werden zeichenweise auf die Spaltenbreite gekürzt.

        ``cell_links`` (optional) ist parallel zu ``rows`` aufgebaut: pro Zelle
        kann eine URL hinterlegt werden. In diesem Fall wird der Zelltext in
        Link-Farbe gerendert und ein PDF-Link-Annotation überlagert.

        ``total_row`` (optional) wird als fette Summenzeile mit hellgrauem
        Hintergrund am Tabellenende gerendert — bleibt mit der Tabelle in
        einem Block (Page-Break-Schutz vor der Summenzeile).

        ``footer_note`` (optional) wird als kursive, kleine Notiz innerhalb
        der Tabellen-Rahmens unter der Summenzeile gerendert — z.B.
        „… und N weitere im JSON-Bericht". So wandert die Notiz mit der
        Tabelle und bleibt nie als Witwe oben auf einer neuen Seite.
        """
        if not rows:
            self.write_text("(keine Einträge)", size=9, color=COL_LIGHT, indent=4)
            return

        if not col_widths:
            col_widths = [USABLE_WIDTH / max(1, len(headers))] * len(headers)
        # Skalieren auf USABLE_WIDTH
        total = sum(col_widths)
        if total > 0:
            col_widths = [w * USABLE_WIDTH / total for w in col_widths]

        row_h = 14
        header_h = 16

        def _draw_header() -> None:
            self.ensure_space(header_h + row_h * 2)
            self.page.draw_rect(
                (MARGIN, self.cursor_y - 2,
                 PAGE_WIDTH - MARGIN, self.cursor_y + header_h - 4),
                color=COL_LINE, fill=(0.92, 0.92, 0.92), width=0.4,
            )
            x = MARGIN
            baseline_y = self.cursor_y + 9
            for i, h in enumerate(headers):
                try:
                    self.page.insert_text(
                        (x + 4, baseline_y), str(h),
                        fontsize=9, fontname="hebo", color=COL_HEADER,
                    )
                except Exception:  # noqa: BLE001
                    self.page.insert_text((x + 4, baseline_y), str(h), fontsize=9)
                x += col_widths[i]
            self.cursor_y += header_h

        _draw_header()

        # Daten-Zeilen
        import fitz  # für Link-Rechtecke (nur lokal benötigt)
        for ri, row in enumerate(rows[:max_rows]):
            if self.cursor_y + row_h > FOOTER_TOP - 10:
                # Auf neuer Seite Header neu rendern und mit Rest fortfahren.
                # total_row + footer_note werden weitergereicht, damit sie am
                # Ende der gesamten Tabelle (auf der letzten Folgeseite) und
                # NICHT auf jeder Teilseite gerendert werden.
                self.new_page()
                self.write_table(
                    headers, rows[ri:], col_widths=col_widths,
                    max_rows=max_rows - ri,
                    cell_links=(cell_links[ri:] if cell_links else None),
                    total_row=total_row,
                    footer_note=footer_note,
                )
                return

            # Alternierender Hintergrund
            if ri % 2 == 1:
                self.page.draw_rect(
                    (MARGIN, self.cursor_y - 2,
                     PAGE_WIDTH - MARGIN, self.cursor_y + row_h - 4),
                    color=None, fill=COL_ROW_ALT, width=0,
                )
            x = MARGIN
            baseline_y = self.cursor_y + 8
            row_links = cell_links[ri] if cell_links and ri < len(cell_links) else None
            for i, cell in enumerate(row):
                w = col_widths[i] if i < len(col_widths) else 60
                # Truncate auf Spaltenbreite
                txt = str(cell or "")
                max_chars = max(8, int(w / 5.0))
                if len(txt) > max_chars:
                    txt = txt[:max_chars - 1] + "…"
                url = (row_links[i] if row_links and i < len(row_links) else None) or None
                text_color = COL_LINK if url else COL_TEXT
                try:
                    self.page.insert_text(
                        (x + 4, baseline_y), txt,
                        fontsize=8.5, fontname="helv", color=text_color,
                    )
                except Exception:  # noqa: BLE001
                    self.page.insert_text((x + 4, baseline_y), txt, fontsize=8.5)
                if url:
                    try:
                        self.page.insert_link({
                            "kind": fitz.LINK_URI,
                            "from": fitz.Rect(
                                x + 2,
                                self.cursor_y - 2,
                                x + w,
                                self.cursor_y + row_h - 4,
                            ),
                            "uri": url,
                        })
                    except Exception:  # noqa: BLE001
                        pass
                x += w

            # Trennlinie
            self.page.draw_line(
                (MARGIN, self.cursor_y + row_h - 4),
                (PAGE_WIDTH - MARGIN, self.cursor_y + row_h - 4),
                color=COL_LINE, width=0.2,
            )
            self.cursor_y += row_h

        # ── Summenzeile (optional, fett mit hellgrauem Hintergrund) ─────────
        # Bleibt mit der Tabelle in einem Block: wenn nicht genug Platz, in
        # die nächste Seite wandern, dort aber zusammen mit Header rendern.
        if total_row is not None:
            need = row_h + (12 if footer_note else 0)
            if self.cursor_y + need > FOOTER_TOP - 10:
                self.new_page()
                _draw_header()
            self.page.draw_rect(
                (MARGIN, self.cursor_y - 2,
                 PAGE_WIDTH - MARGIN, self.cursor_y + row_h - 4),
                color=COL_LINE, fill=(0.90, 0.90, 0.90), width=0.4,
            )
            x = MARGIN
            baseline_y = self.cursor_y + 8
            for i, cell in enumerate(total_row):
                w = col_widths[i] if i < len(col_widths) else 60
                txt = str(cell or "")
                max_chars = max(8, int(w / 5.0))
                if len(txt) > max_chars:
                    txt = txt[:max_chars - 1] + "…"
                try:
                    self.page.insert_text(
                        (x + 4, baseline_y), txt,
                        fontsize=9, fontname="hebo", color=COL_HEADER,
                    )
                except Exception:  # noqa: BLE001
                    self.page.insert_text((x + 4, baseline_y), txt, fontsize=9)
                x += w
            self.cursor_y += row_h

        # ── Footer-Note innerhalb der Tabelle (z.B. „… und N weitere") ──────
        if footer_note:
            self.ensure_space(12)
            try:
                self.page.insert_text(
                    (MARGIN + 4, self.cursor_y + 7), footer_note,
                    fontsize=8, fontname="helv", color=COL_LIGHT,
                )
            except Exception:  # noqa: BLE001
                self.page.insert_text((MARGIN + 4, self.cursor_y + 7), footer_note,
                                       fontsize=8)
            self.cursor_y += 12

        if len(rows) > max_rows:
            self.write_text(
                f"… {len(rows) - max_rows} weitere Einträge gekürzt.",
                size=8, color=COL_LIGHT, indent=4,
            )

    def finalize_headers_footers(self) -> None:
        """Zeichnet Header und Footer auf alle bisher angelegten Seiten."""
        total = len(self.doc)
        for idx in range(total):
            page = self.doc[idx]
            # Header: Titel oben links (Seitenzahl wandert nach unten zentriert).
            try:
                page.insert_text(
                    (MARGIN, MARGIN - 14), self.title,
                    fontsize=8.5, fontname="hebo", color=COL_HEADER,
                )
                page.draw_line(
                    (MARGIN, MARGIN - 8),
                    (PAGE_WIDTH - MARGIN, MARGIN - 8),
                    color=COL_LINE, width=0.4,
                )
                # Footer auf zwei Zeilen:
                #   Trennstrich
                #   Zeile 1: footer_text linksbündig (Erstell-Info)
                #   Zeile 2: page_label zentriert ("Seite N / Total")
                page.draw_line(
                    (MARGIN, FOOTER_TOP - 4),
                    (PAGE_WIDTH - MARGIN, FOOTER_TOP - 4),
                    color=COL_LINE, width=0.3,
                )
                page.insert_text(
                    (MARGIN, FOOTER_TOP + 6),
                    self.footer_text,
                    fontsize=7.5, fontname="helv", color=COL_LIGHT,
                )
                page_label = f"Seite {idx + 1} / {total}"
                # Helvetica ~4.8pt je Zeichen bei size 9
                approx_w = len(page_label) * 4.8
                page.insert_text(
                    ((PAGE_WIDTH - approx_w) / 2, FOOTER_TOP + 20),
                    page_label,
                    fontsize=9, fontname="hebo", color=COL_HEADER,
                )
            except Exception:  # noqa: BLE001
                # Wenn Schriftarten fehlen, fallen wir auf Default zurück
                pass


# ── Sektionen ─────────────────────────────────────────────────────────────────


def _render_cover(state: _RenderState) -> None:
    """Deckblatt (1 Seite): Titel, Anfrage, öffentlich zugängliche Quellen,
    Methodik, KI-Hinweis, Rechtsblock, Kontakt. Auftraggeber/Prüfer werden
    bewusst nicht ausgegeben."""
    data = state.data
    state.cursor_y = MARGIN + 30
    state.write_text("Cross-Register-Prüfbericht", size=20, bold=True, color=COL_HEADER)
    state.cursor_y += 2
    state.write_text(
        "Faktische Aufbereitung · keine Bewertung · keine Empfehlung",
        size=10, color=COL_LIGHT,
    )
    state.cursor_y += 10
    state.hr()
    state.cursor_y += 2

    # ── Anfrage ──────────────────────────────────────────────────────────────
    state.write_kv("Suchbegriff:", data.query)
    state.write_kv(
        "Erstellt am:",
        data.issued_at.strftime("%Y-%m-%d %H:%M UTC") if data.issued_at else "—",
    )

    state.cursor_y += 4

    # ── Öffentlich zugängliche Datenquellen ──────────────────────────────────
    state.write_h3("Öffentlich zugängliche Datenquellen")
    state.write_paragraph(
        "Aggregation ausschließlich aus öffentlichen Registern. Keine internen "
        "oder personenbezogenen Daten Dritter werden verarbeitet.",
        size=9,
    )

    freshness = data.data_freshness or {}

    def _stand_line(key: str) -> str:
        info = freshness.get(key) or {}
        if isinstance(info, str):
            return f"Datenstand: {info}"
        as_of = info.get("as_of")
        rc = info.get("record_count")
        parts: list[str] = []
        if as_of:
            try:
                parts.append(f"Stand {as_of[:10]}")
            except Exception:  # noqa: BLE001
                parts.append(f"Stand {as_of}")
        else:
            parts.append("Stand: lokaler Upload")
        if isinstance(rc, int) and rc > 0:
            parts.append(f"{rc:,} Datensätze lokal".replace(",", "."))
        note = info.get("note")
        if note:
            parts.append(str(note))
        return "Datenstand: " + " · ".join(parts)

    state.write_text(
        "1.  EU Transparency Aid Module (TAM) + nationale Beihilfe-Register",
        size=9, bold=True,
    )
    state.write_paragraph(
        "https://webgate.ec.europa.eu/competition/transparency/public — "
        "Beihilfen nach Art. 9 Abs. 1 lit. c) VO 651/2014 (AGVO). "
        + _stand_line("state_aid"),
        size=8.5, indent=10, color=COL_LIGHT,
    )
    state.write_paragraph(
        "Jeder Award ist unter https://webgate.ec.europa.eu/competition/"
        "transparency/public/aidAward/show/{Award-ID} direkt einsehbar; "
        "die SA-Ref-Spalte in der Detail-Tabelle ist als klickbarer Link "
        "auf den TAM-Datensatz ausgeführt (Fallback: KOM-Casebook).",
        size=8.5, indent=10, color=COL_LIGHT,
    )

    state.write_text(
        "2.  Begünstigtenverzeichnisse Art. 49 VO (EU) 2021/1060",
        size=9, bold=True,
    )
    state.write_paragraph(
        "Transparenzlisten der EFRE-/ESF-/JTF-Förderbehörden der Bundesländer "
        "und Österreichs (BMK), lokal als XLSX eingespielt. "
        + _stand_line("beneficiaries"),
        size=8.5, indent=10, color=COL_LIGHT,
    )

    state.write_text(
        "3.  OpenSanctions Multi-Source — EU FSF, UN, OFAC, OFSI, SECO",
        size=9, bold=True,
    )
    state.write_paragraph(
        "https://www.opensanctions.org/ — aggregiert EU FSF (Art. 215 AEUV), "
        "UN Security Council Consolidated, OFAC SDN, UK OFSI, SECO. "
        + _stand_line("sanctions"),
        size=8.5, indent=10, color=COL_LIGHT,
    )

    state.cursor_y += 4

    # ── Methodik ─────────────────────────────────────────────────────────────
    state.write_h3("Methodik")
    state.write_paragraph(
        "Rein algorithmische Abfrage und Aggregation ohne menschliche "
        "Vorauswahl: Normalisierung der Firmenbezeichnungen (Rechtsform-Aliase, "
        "Diakritika, Whitespace), token-basierte Fuzzy-Suche mit Trigramm-"
        "Matching und Levenshtein-Score, Identifier-Abgleich (SA-Referenz, "
        "Förderkennzeichen) sowie NUTS-Code-Vergleich für Querbezüge. Keine "
        "Severity-Klassifikation, keine Risiko-Bewertung — die fachliche "
        "Einordnung obliegt allein dem Prüfer.",
        size=9,
    )

    state.cursor_y += 4

    # ── Einsatz lokaler KI-Modelle ───────────────────────────────────────────
    state.write_h3("Einsatz lokaler KI-Modelle")
    llm_used = getattr(data, "llm_verification", None) is not None
    if llm_used:
        state.write_paragraph(
            "Für diesen Bericht wurde zusätzlich eine lokale Sprachmodell-"
            "Zweitmeinung herangezogen: Qwen3-14B (Q8) über Ollama auf einer "
            "dedizierten NVIDIA-GPU (RTX 5060 oder RTX 5070, jeweils 16 GB "
            "VRAM). Das Modell prüft ausschließlich unsichere Querbezüge mit "
            "einer kurzen Begründung; die Rohdaten bleiben unverändert. Weder "
            "Modell noch Daten verlassen das Gerät — keine externe KI-Anbindung.",
            size=9,
        )
    else:
        state.write_paragraph(
            "Für diesen Bericht wurde keine Sprachmodell-Komponente eingesetzt — "
            "Treffer und Querbezüge wurden ausschließlich algorithmisch ermittelt.",
            size=9,
        )
        state.write_paragraph(
            "Optional kann eine lokale Zweitmeinung zugeschaltet werden: Qwen3-14B "
            "(Q8) über Ollama auf einer dedizierten NVIDIA-GPU (RTX 5060 oder "
            "RTX 5070, jeweils 16 GB VRAM). Modell und Daten verbleiben auch dann "
            "vollständig auf dem Gerät — keine externe KI-Anbindung.",
            size=9,
        )

    state.cursor_y += 4

    # ── Karten-Hinweis (nur wenn Karte aktiv) ────────────────────────────────
    if getattr(state, "include_map", False):
        state.write_h3("Hinweis zur Karten-Sektion")
        state.write_paragraph(
            "Diese Auswertung enthält eine optionale Karten-Seite. Die "
            "Hintergrundkacheln werden bei Erstellung des Berichts einmalig "
            "von tile.openstreetmap.org abgerufen (© OpenStreetMap "
            "Mitwirkende). Es werden dabei keine Daten zum Begünstigten oder "
            "zur Anfrage an externe Dienste übertragen — nur generische "
            "Karten-Tiles. Die NUTS-Geometrien stammen aus dem lokalen "
            "Eurostat-Vektor-Datensatz; die Marker werden im Backend gerechnet.",
            size=9,
        )
        state.cursor_y += 4

    # ── Rechtlicher Hinweis ──────────────────────────────────────────────────
    state.write_h3("Rechtlicher Hinweis")
    state.write_paragraph(
        "Kostenfreies, privates Demonstrations- und Recherchewerkzeug — keine "
        "behördliche Anwendung. Keine Gewährleistung für Vollständigkeit, "
        "Richtigkeit oder Aktualität; Haftung — gleich aus welchem Rechtsgrund — "
        "ist ausgeschlossen, soweit gesetzlich zulässig. Der Bericht ersetzt "
        "nicht die eigenständige Prüfung der Originalquellen. Alle Daten werden "
        "lokal verarbeitet; ein Versand an externe Dienste findet außer der "
        "Aktualisierung aus den genannten öffentlichen Quellen nicht statt.",
        size=9,
    )

    state.cursor_y += 4

    # ── Kontakt (einzeilig) ──────────────────────────────────────────────────
    state.write_text(
        "Kontakt für Rückmeldungen und Korrekturhinweise: jan.riener@vwvg.de",
        size=9, bold=True, color=COL_HEADER,
    )


def _render_summary(state: _RenderState) -> None:
    """Executive Summary: rein quantitativ, ohne Bewertung."""
    data = state.data
    state.write_h1("Zusammenfassung")
    state.write_paragraph(
        "Quantitative Auswertung der Treffer pro Register. Die Zahlen "
        "spiegeln den aktuellen Datenbestand wider. Eine fachliche "
        "Einordnung erfolgt durch den Prüfer.",
        size=9.5,
    )
    state.cursor_y += 6

    rows = [
        [
            "EU-State-Aid",
            str(data.state_aid.total_count),
            f"{data.state_aid.total_amount_eur:,.2f} EUR",
        ],
        [
            "Begünstigtenverzeichnis",
            str(data.beneficiaries.total_count),
            f"{data.beneficiaries.total_amount_eur:,.2f} EUR",
        ],
        [
            "Sanktionsliste (FSF)",
            str(data.sanctions.total_hits),
            "—",
        ],
        [
            "Querbezüge (neutral)",
            str(len(data.cross_references)),
            "—",
        ],
    ]
    state.write_table(
        ["Register", "Treffer", "Summe (EUR, sofern verfügbar)"],
        rows,
        col_widths=[200, 90, 200],
    )

    state.cursor_y += 16
    state.write_h3("Querbezüge im Überblick")
    if not data.cross_references:
        state.write_paragraph(
            "Keine Querbezüge zwischen den Registern festgestellt.",
            size=9.5, color=COL_LIGHT,
        )
        return
    # Aufschlüsselung pro Typ
    type_counts: dict[str, int] = {}
    for ref in data.cross_references:
        type_counts[ref.type] = type_counts.get(ref.type, 0) + 1
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        state.write_text(f"  · {t}: {c}", size=9.5)


# Maximale Anzahl Detail-Zeilen pro Sektions-Tabelle. Wird genutzt, damit
# der PDF-Bericht handhabbar bleibt — die JSON-Antwort bleibt vollständig.
DETAIL_ROW_LIMIT = 40


def _render_state_aid_section(state: _RenderState) -> None:
    """State-Aid: Detail-Tabelle (Top 40 nach Datum) + Aggregate."""
    data = state.data.state_aid
    state.write_h1("EU-State-Aid-Register")
    state.write_paragraph(
        "Treffer aus dem EU Transparency Aid Module (TAM) und den nationalen "
        "Beihilfe-Registern. Awards sind ausschließlich solche, für die eine "
        "Veröffentlichungspflicht nach Art. 9 Abs. 1 lit. c) VO (EU) Nr. "
        "651/2014 (AGVO) besteht.",
        size=9.5,
    )
    state.write_kv("Treffer (gesamt):", str(data.total_count))
    state.write_kv("Fördervolumen:", f"{data.total_amount_eur:,.2f} EUR")
    state.write_kv("SA-Referenzen:", "; ".join(data.sa_references[:10]) or "—")
    state.cursor_y += 8

    # ── Detail-Tabelle: alle einzelnen Awards (max. 40, sortiert nach Datum) ─
    state.write_h2(f"Detail-Treffer (max. {DETAIL_ROW_LIMIT}, sortiert nach Datum)")
    sorted_awards = sorted(
        data.awards,
        key=lambda a: (a.get("granting_date") or ""),
        reverse=True,
    )
    detail_rows: list[list[str]] = []
    detail_links: list[list[str | None]] = []
    shown_sum = 0.0
    for a in sorted_awards[:DETAIL_ROW_LIMIT]:
        date_val = (a.get("granting_date") or "")[:10] or "—"
        ben_name = _truncate(a.get("beneficiary_name") or "—", 35)
        region = a.get("nuts_label") or a.get("nuts_code") or "—"
        region = _truncate(region, 18)
        authority = _truncate(a.get("granting_authority") or "—", 28)
        amount_val = a.get("aid_amount_eur") or 0.0
        shown_sum += amount_val
        amount_str = f"{amount_val:,.0f}"
        sa_ref = a.get("sa_reference") or "—"
        detail_rows.append([date_val, ben_name, region, authority, amount_str, sa_ref])
        # SA-Ref-Zelle klickbar machen: bevorzugt TAM-Award-Deep-Link
        # (source_url), Fallback KOM-Casebook (case_url).
        sa_link = a.get("source_url") or a.get("case_url") or None
        detail_links.append([None, None, None, None, None, sa_link])
    remaining = max(0, len(sorted_awards) - DETAIL_ROW_LIMIT)
    state.write_table(
        ["Datum", "Begünstigter", "Region", "Behörde", "Betrag (EUR)", "SA-Ref → TAM"],
        detail_rows,
        col_widths=[55, 130, 70, 105, 65, 70],
        cell_links=detail_links,
        total_row=[
            "Summe", "", "", "",
            f"{shown_sum:,.0f}", f"{len(detail_rows)} Zeilen",
        ],
        footer_note=(
            f"… und {remaining} weitere Treffer · Gesamtvolumen über alle "
            f"{data.total_count} Awards: {data.total_amount_eur:,.0f} EUR "
            f"(im JSON-Bericht vollständig)."
            if remaining > 0
            else f"Anzeige vollständig · alle {data.total_count} Awards enthalten."
        ),
    )

    if data.by_year:
        state.cursor_y += 14
        state.write_h2("Verteilung nach Jahr")
        rows = [
            [str(b["year"]), str(b["count"]), f"{b['total_eur']:,.2f}"]
            for b in data.by_year
        ]
        sum_count = sum(int(b["count"]) for b in data.by_year)
        sum_eur = sum(float(b["total_eur"]) for b in data.by_year)
        state.write_table(
            ["Jahr", "Anzahl", "Summe (EUR)"], rows,
            col_widths=[80, 80, 200],
            total_row=["Gesamt", str(sum_count), f"{sum_eur:,.2f}"],
        )

    # Top-10 Bewilligungsstellen + Beihilfe-Instrumente bewusst NICHT mehr
    # gerendert — gehören in die Schnellauswertungen (eigener Excel-Export),
    # nicht in den Prüfbericht für eine konkrete Firma.

    if data.by_nuts:
        state.cursor_y += 14
        state.write_h2("Verteilung nach NUTS-1")
        rows = [
            [str(b["nuts_code"]), str(b["count"]), f"{b['total_eur']:,.2f}"]
            for b in data.by_nuts
        ]
        sum_count = sum(int(b["count"]) for b in data.by_nuts)
        sum_eur = sum(float(b["total_eur"]) for b in data.by_nuts)
        state.write_table(
            ["NUTS-1", "Anzahl", "Summe (EUR)"], rows,
            col_widths=[80, 80, 200],
            total_row=["Gesamt", str(sum_count), f"{sum_eur:,.2f}"],
        )

    # Top-10 Beihilfe-Instrumente bewusst entfernt (siehe oben).

    if data.case_urls:
        state.cursor_y += 14
        state.write_h2("Verlinkte KOM-Fälle")
        for url in data.case_urls[:20]:
            state.write_text(f"  · {url}", size=8.5, color=COL_LIGHT)


def _render_map_section(state: _RenderState) -> None:
    """Eigene Seite: OSM-Karte mit NUTS-Outline + Markern pro Treffer-Region.

    Wird nur aufgerufen, wenn ``include_map=True`` an ``render_audit_report_pdf``
    übergeben wurde. Falls die Karte technisch nicht erzeugt werden kann
    (keine NUTS-Treffer, OSM-Tile-Netz weg), wird statt der Grafik ein
    erklärender Text gerendert — der Bericht bricht nicht ab.
    """
    state.write_h1("Räumliche Verteilung der Awards")
    state.write_paragraph(
        f"Karte mit OSM-Hintergrund und NUTS-Layer (Eurostat). Marker zeigen "
        f"die Anzahl der State-Aid-Awards für „{state.data.query}“ je "
        "getroffene NUTS-Region; die Zahl im Marker entspricht der Award-Anzahl.",
        size=9.5,
    )

    awards = [
        {
            "nuts_code": a.get("nuts_code"),
            "country_code": a.get("country_code"),
            "aid_amount_eur": a.get("aid_amount_eur"),
        }
        for a in (state.data.state_aid.awards or [])
    ]
    try:
        from services.state_aid_audit_map import render_audit_map
        png_bytes = render_audit_map(
            awards,
            query_name=state.data.query,
            nuts_level=1,
        )
    except Exception:  # noqa: BLE001
        log.exception("Karten-Rendering fehlgeschlagen")
        png_bytes = None

    if not png_bytes:
        state.cursor_y += 10
        state.write_paragraph(
            "Karte konnte nicht erzeugt werden. Mögliche Ursachen: keine "
            "Awards mit NUTS-Code im Datenbestand für die Anfrage, oder das "
            "OSM-Tile-Netz war zum Erstellungszeitpunkt nicht erreichbar. Der "
            "übrige Bericht ist davon nicht betroffen.",
            size=9.5, color=COL_LIGHT,
        )
        return

    # Bild in den verbleibenden Platz auf der Seite einbetten.
    state.cursor_y += 6
    import fitz  # type: ignore
    avail_w = USABLE_WIDTH
    avail_h = FOOTER_TOP - state.cursor_y - 30  # Reserve für Caption
    # Die Karte ist 900×680 — Verhältnis 1.323
    img_ratio = 900 / 680
    if avail_w / img_ratio <= avail_h:
        w = avail_w
        h = avail_w / img_ratio
    else:
        h = avail_h
        w = avail_h * img_ratio
    rect = fitz.Rect(
        MARGIN, state.cursor_y,
        MARGIN + w, state.cursor_y + h,
    )
    try:
        state.page.insert_image(rect, stream=png_bytes)
    except Exception:  # noqa: BLE001
        log.exception("Karten-Image konnte nicht eingefügt werden")
        state.write_paragraph(
            "Die erzeugte Karte konnte nicht ins PDF eingebettet werden.",
            size=9.5, color=COL_LIGHT,
        )
        return
    state.cursor_y += h + 8
    state.write_paragraph(
        "Hintergrund: © OpenStreetMap Mitwirkende (tile.openstreetmap.org). "
        "NUTS-1-Geometrien: Eurostat. Treffer-Regionen sind transparent rot "
        "überlagert; alle anderen NUTS-1-Regionen sind als graue Outline "
        "sichtbar.",
        size=8.5, color=COL_LIGHT,
    )


def _render_beneficiaries_section(state: _RenderState) -> None:
    """Begünstigtenverzeichnis: lokale Transparenzlisten."""
    data = state.data.beneficiaries
    state.write_h1("Begünstigtenverzeichnis")
    state.write_paragraph(
        "Treffer aus den lokal eingespielten Transparenzlisten der Bundesländer "
        "(EFRE/ESF/JTF). Datenquelle: hochgeladene XLSX-Dateien.",
        size=9.5,
    )
    state.write_kv("Treffer (gesamt):", str(data.total_count))
    state.write_kv("Fördervolumen:", f"{data.total_amount_eur:,.2f} EUR")
    state.cursor_y += 8

    # ── Detail-Tabelle: max. 40 Einträge ────────────────────────────────────
    if data.matches:
        state.write_h2(f"Detail-Treffer (max. {DETAIL_ROW_LIMIT})")
        detail_rows = []
        shown_sum = 0.0
        for m in data.matches[:DETAIL_ROW_LIMIT]:
            bundesland = m.get("bundesland") or "—"
            fonds = m.get("fonds") or "—"
            vorhaben = _truncate(m.get("project_name") or "—", 40)
            # Vorhaben-Aktenzeichen aus dem Beneficiary-Record selbst
            ak = m.get("aktenzeichen") or "—"
            kosten = float(m.get("kosten") or 0.0)
            shown_sum += kosten
            kosten_str = f"{kosten:,.0f}"
            detail_rows.append([bundesland, fonds, vorhaben, ak, kosten_str])
        remaining = max(0, len(data.matches) - DETAIL_ROW_LIMIT)
        state.write_table(
            ["Bundesland", "Fonds", "Vorhaben", "Aktenzeichen", "Betrag (EUR)"],
            detail_rows,
            col_widths=[80, 50, 175, 90, 100],
            total_row=[
                "Summe", "", "", f"{len(detail_rows)} Zeilen",
                f"{shown_sum:,.0f}",
            ],
            footer_note=(
                f"… und {remaining} weitere Treffer · Gesamtvolumen über alle "
                f"{data.total_count} Vorhaben: {data.total_amount_eur:,.0f} EUR "
                f"(im JSON-Bericht vollständig)."
                if remaining > 0
                else f"Anzeige vollständig · alle {data.total_count} Vorhaben enthalten."
            ),
        )

    if data.by_bundesland:
        state.cursor_y += 14
        state.write_h2("Verteilung nach Bundesland")
        rows = [
            [str(b["key"]), str(b["count"]), f"{b['total_eur']:,.2f}"]
            for b in data.by_bundesland
        ]
        sum_count = sum(int(b["count"]) for b in data.by_bundesland)
        sum_eur = sum(float(b["total_eur"]) for b in data.by_bundesland)
        state.write_table(
            ["Bundesland", "Anzahl", "Summe (EUR)"], rows,
            col_widths=[150, 80, 150],
            total_row=["Gesamt", str(sum_count), f"{sum_eur:,.2f}"],
        )

    if data.by_fonds:
        state.cursor_y += 14
        state.write_h2("Verteilung nach Fonds")
        rows = [
            [str(b["key"]), str(b["count"]), f"{b['total_eur']:,.2f}"]
            for b in data.by_fonds
        ]
        sum_count = sum(int(b["count"]) for b in data.by_fonds)
        sum_eur = sum(float(b["total_eur"]) for b in data.by_fonds)
        state.write_table(
            ["Fonds", "Anzahl", "Summe (EUR)"], rows,
            col_widths=[150, 80, 150],
            total_row=["Gesamt", str(sum_count), f"{sum_eur:,.2f}"],
        )


def _render_sanctions_section(state: _RenderState) -> None:
    """Sanctions: Treffer ja/nein, Liste, Score, Konfidenz — faktisch.

    Zeigt explizit, welche Identifikatoren (Organisation + Personen) gegen
    welche Sanktionslisten abgeglichen wurden, damit der Prüfer den Scope
    der Abfrage nachvollziehen kann.
    """
    data = state.data.sanctions
    state.write_h1("Sanktionslisten-Check")
    state.write_paragraph(
        "Abfrage gegen fünf konsolidierte Sanktionslisten (EU FSF nach "
        "Art. 215 AEUV, UN Security Council Consolidated, OFAC SDN, "
        "UK OFSI Consolidated, SECO Schweiz) — Multi-Source-Aggregation "
        "über OpenSanctions. Treffer werden mit Fuzzy-Score (0..100) und "
        "Konfidenzklasse aufgeführt — ohne Bewertung. Ein Treffer ist "
        "kein Beleg für Sanktionsbetroffenheit; der Prüfer entscheidet, "
        "ob der Treffer relevant ist.",
        size=9.5,
    )

    # ── Abgefragte Identifikatoren (Scope-Transparenz) ───────────────────────
    state.cursor_y += 6
    state.write_h2("Abgefragte Identifikatoren")
    query_name = state.data.query
    persons_check = getattr(state.data, "persons_check", None)
    person_count = (persons_check.total_persons if persons_check else 0)

    scope_rows: list[list[str]] = [
        ["Organisation", query_name, "—"],
    ]
    if persons_check and persons_check.entries:
        for entry in persons_check.entries[:20]:
            scope_rows.append([
                "Natürliche Person",
                entry.input_name,
                entry.input_role or "Sonstige",
            ])
    state.write_table(
        ["Typ", "Identifikator", "Rolle"],
        scope_rows,
        col_widths=[110, 280, 105],
        total_row=[
            "Summe abgefragt",
            f"1 Organisation + {person_count} Person(en)",
            "",
        ],
    )

    if person_count == 0:
        state.cursor_y += 4
        state.write_paragraph(
            "Hinweis: Es wurden keine natürlichen Personen eingegeben. "
            "Für einen vollständigen Sanktions-Check sollten Geschäftsführung, "
            "Gesellschafter und wirtschaftlich Berechtigte (UBO) im Frontend "
            "ergänzt werden — der Abschnitt zum Personen-Sanktionscheck "
            "wird sonst übersprungen.",
            size=8.5, color=COL_LIGHT,
        )

    state.cursor_y += 10

    if data.total_hits == 0:
        state.write_h2("Treffer Organisation")
        state.write_paragraph(
            "Keine Treffer für die Organisation „" + query_name
            + "“ in den fünf abgefragten Sanktionslisten.",
            size=10, bold=True,
        )
        return

    state.write_kv("Treffer:", str(data.total_hits))
    if data.listing_sources:
        state.write_kv("Quelle(n):", "; ".join(data.listing_sources))
    state.cursor_y += 8

    # ── Detail-Tabelle (Multi-Source: Quelle pro Treffer) ───────────────────
    state.write_h2(f"Detail-Treffer (max. {DETAIL_ROW_LIMIT})")
    # Kuerzel pro Source-Key für kompakte Tabelle (Spaltenbreite 50pt).
    _SOURCE_LABELS = {
        "eu_fsf": "EU FSF",
        "un_sc": "UN SC",
        "us_ofac_sdn": "OFAC",
        "gb_hmt_sanctions": "UK OFSI",
        "ch_seco": "SECO",
    }
    detail_rows = []
    for h in data.hits[:DETAIL_ROW_LIMIT]:
        # Quelle: aus source_key (Multi-Source) — Backward-Compat: alte
        # Reports ohne source_key fallen auf "EU FSF" zurueck.
        source_key = h.get("source_key") or "eu_fsf"
        source_label = _SOURCE_LABELS.get(source_key, source_key.upper()[:8])
        score_val = h.get("score") or 0
        score_str = f"{score_val:.1f}"
        confidence = h.get("confidence") or "—"
        # Aliases: max. 3, mit "..." wenn mehr
        aliases_full = h.get("aliases") or []
        aliases_visible = aliases_full[:3]
        aliases_str = "; ".join(str(a) for a in aliases_visible)
        if len(aliases_full) > 3:
            aliases_str = (aliases_str + " …") if aliases_str else "…"
        countries = h.get("countries") or "—"
        # Sanktions-Programm: nimm das erste sanctions-Element (Fallback program_ids)
        san_list = h.get("sanctions") or []
        prog_ids = h.get("program_ids") or []
        if isinstance(san_list, str):
            program = san_list
        elif isinstance(san_list, list) and san_list:
            program = "; ".join(str(s) for s in san_list[:2])
        elif isinstance(prog_ids, list) and prog_ids:
            program = "; ".join(str(s) for s in prog_ids[:2])
        else:
            program = "—"
        detail_rows.append([
            source_label,
            score_str,
            confidence,
            _truncate(aliases_str, 32),
            _truncate(str(countries), 16),
            _truncate(program, 32),
        ])
    remaining = max(0, len(data.hits) - DETAIL_ROW_LIMIT)
    state.write_table(
        ["Quelle", "Score", "Konfidenz", "Aliases (max. 3)",
         "Länder", "Sanktions-Programm"],
        detail_rows,
        col_widths=[55, 40, 55, 125, 55, 145],
        total_row=[
            f"{len(detail_rows)} Treffer", "", "", "", "", "",
        ],
        footer_note=(
            f"… und {remaining} weitere Treffer · Gesamt: {data.total_hits} "
            f"(im JSON-Bericht vollständig)."
            if remaining > 0
            else f"Anzeige vollständig · alle {data.total_hits} Treffer enthalten."
        ),
    )


_SEMANTIC_REF_TYPES = {
    "semantic_neighbor_state_aid",
    "semantic_neighbor_beneficiary",
    "semantic_neighbor_sanctions",
}


def _render_cross_references(state: _RenderState) -> None:
    """Querbezüge — neutrale Beobachtungen mit Evidenz.

    Layer A: Semantische Nachbarschaft (Embedding-Layer) wird in einer
    eigenen Sektion gerendert — siehe ``_render_semantic_neighbors``.

    Layer B: Cross-References mit ``filtered_by_llm=True`` (LLM-Verdict
    `match=no`) werden in der Tabelle ausgelassen, bleiben aber im JSON-
    Audit-Trail vollständig erhalten. Siehe ``_render_llm_verification``.
    """
    all_refs = state.data.cross_references or []
    refs = [
        r for r in all_refs
        if r.type not in _SEMANTIC_REF_TYPES
        and not getattr(r, "filtered_by_llm", False)
    ]

    state.write_h1("Querbezüge zwischen den Registern")
    state.write_paragraph(
        "Neutrale Beobachtungen: Datensaetze, die über gemeinsame Felder "
        "(Name, Identifier, SA-Referenz) miteinander in Verbindung stehen. "
        "Keine Bewertung und keine Severity-Klassifikation — die fachliche "
        "Einordnung obliegt dem Prüfer.",
        size=9.5,
    )

    if not refs:
        state.cursor_y += 6
        state.write_paragraph(
            "Es wurden keine Querbezüge zwischen den drei Registern "
            "festgestellt.",
            size=10, color=COL_LIGHT,
        )
        return

    state.cursor_y += 8

    # ── Tabellarische Übersicht ────────────────────────────────────────────
    table_rows: list[list[str]] = []
    for ref in refs[:DETAIL_ROW_LIMIT]:
        # Evidenz als kompakter Text
        ev_parts = []
        for k, v in (ref.evidence or {}).items():
            if isinstance(v, dict):
                inner = "; ".join(f"{k2}={_short(v2, 30)}" for k2, v2 in v.items())
                ev_parts.append(f"{k}: {{{inner}}}")
            elif isinstance(v, list):
                preview = "; ".join(str(x) for x in v[:3])
                if len(v) > 3:
                    preview += f" (+{len(v) - 3})"
                ev_parts.append(f"{k}: [{preview}]")
            else:
                ev_parts.append(f"{k}: {_short(v, 40)}")
        ev_text = " · ".join(ev_parts)
        table_rows.append([
            _pretty_type(ref.type),
            _truncate(ref.description or "—", 80),
            _truncate(ev_text, 80),
        ])
    state.write_table(
        ["Typ", "Beobachtung", "Evidenz"],
        table_rows,
        col_widths=[150, 175, 170],
    )
    if len(refs) > DETAIL_ROW_LIMIT:
        state.write_text(
            f"… und {len(refs) - DETAIL_ROW_LIMIT} weitere Querbezüge "
            f"(im JSON-Bericht vollständig enthalten).",
            size=8.5, color=COL_LIGHT, indent=4,
        )


def _render_semantic_neighbors(state: _RenderState) -> None:
    """Semantische Nachbarschaft (Layer A, Embedding-Layer).

    Strikt neutral — KEIN Identitäts-Beweis, KEIN Treffer-Score, sondern
    Hinweis auf möglicherweise verwandte Vorgaenge. Wird nur ausgewiesen,
    wenn ``include_semantic_neighbors=True`` an ``build_audit_report``
    übergeben wurde.
    """
    all_refs = state.data.cross_references or []
    refs = [r for r in all_refs if r.type in _SEMANTIC_REF_TYPES]
    if not refs:
        return

    state.write_h1("Semantische Nachbarschaft")
    state.write_paragraph(
        "Diese Records wurden vom KI-Embedding als aehnlich erkannt — kann "
        "Hinweis auf verwandte Vorgaenge sein, ist aber kein Identitäts-"
        "Beweis. Die fachliche Einordnung obliegt dem Prüfer. Modell: "
        "bge-m3 (1024 Dim).",
        size=9.5,
    )
    state.cursor_y += 6

    table_rows: list[list[str]] = []
    for ref in refs[:DETAIL_ROW_LIMIT]:
        ev = ref.evidence or {}
        module = ev.get("module") or "—"
        cos = ev.get("cosine_similarity")
        cos_str = f"{cos}" if cos is not None else "—"
        rid = ev.get("original_record_id") or "—"
        text_input = ev.get("text_input") or "—"
        table_rows.append([
            _pretty_type(ref.type),
            str(module),
            cos_str,
            _truncate(str(rid), 24),
            _truncate(str(text_input), 80),
        ])
    state.write_table(
        ["Typ", "Modul", "Cosine", "Record-ID", "Embedding-Text"],
        table_rows,
        col_widths=[140, 80, 50, 70, 155],
    )
    if len(refs) > DETAIL_ROW_LIMIT:
        state.write_text(
            f"… und {len(refs) - DETAIL_ROW_LIMIT} weitere semantische "
            f"Nachbarn (im JSON-Bericht vollständig enthalten).",
            size=8.5, color=COL_LIGHT, indent=4,
        )


# ── LLM-Verifikation (Layer B) ───────────────────────────────────────────────


def _verdict_glyph(match: str) -> str:
    """Liefert ein neutrales Schriftzeichen pro Verdict.

    KEINE Risiko-Symbole — bewusst zurueckhaltend (Plus / Minus / Frage).
    """
    if match == "yes":
        return "+"
    if match == "no":
        return "-"
    return "?"


def _render_llm_verification(state: _RenderState) -> None:
    """LLM-Verifikation (Layer B) — Re-Ranker für ambivalente Cross-Refs.

    Tabelle: Original-Score | LLM-Match | LLM-Confidence | Begruendung.
    Hinweistext oben: das LLM-Verdict ist eine Indikation, kein Beweis.
    """
    ver = state.data.llm_verification
    if ver is None:
        return

    state.write_h1("LLM-Verifikation der Querbezüge")
    state.write_paragraph(
        "Die heuristisch ermittelten Querbezüge im Score-Bereich 75 bis 89 "
        "wurden vom LLM (Qwen3-14B) gegen die jeweiligen Datensatz-Inhalte "
        "geprüft. Das LLM beantwortet pro Match eine einfache Frage: Bezeich-"
        "nen die zwei Datensaetze denselben Akteur? LLM-Begruendungen sind "
        "Hinweise, kein Beweis — die fachliche Einordnung obliegt dem Prüfer. "
        "Querbezüge mit LLM-Verdict 'no' werden in der vorigen Tabelle aus-"
        "geblendet, bleiben aber im JSON-Bericht erhalten.",
        size=9.5,
    )
    state.cursor_y += 4

    total = int(getattr(ver, "total_input", 0) or 0)
    verdicts = list(getattr(ver, "verdicts", []) or [])
    skipped = int(getattr(ver, "skipped_due_to_timeout", 0) or 0)
    elapsed_ms = int(getattr(ver, "elapsed_total_ms", 0) or 0)
    err = getattr(ver, "error", None)

    state.write_kv("Eingabe (ambivalente Refs):", str(total), key_width=210)
    state.write_kv("Vom LLM geprüft:", str(len(verdicts)), key_width=210)
    if skipped:
        state.write_kv(
            "Wegen Timeout übersprungen:", str(skipped), key_width=210,
        )
    secs = elapsed_ms / 1000.0 if elapsed_ms else 0.0
    state.write_kv(
        "Dauer gesamt:", f"{secs:,.1f} s".replace(",", "."), key_width=210,
    )
    if err:
        state.write_text(
            f"Fehler-Hinweis: {str(err)[:160]}",
            size=9, color=COL_LIGHT, indent=4,
        )

    state.cursor_y += 6

    if not verdicts:
        state.write_paragraph(
            "Keine ambivalenten Querbezüge im Score-Bereich 75..89 — das "
            "LLM hatte nichts zu pruefen.",
            size=10, color=COL_LIGHT,
        )
        return

    cross_refs = state.data.cross_references or []
    table_rows: list[list[str]] = []
    for v in verdicts[:DETAIL_ROW_LIMIT]:
        idx = int(getattr(v, "cross_ref_index", -1))
        if 0 <= idx < len(cross_refs):
            cr = cross_refs[idx]
            ev = getattr(cr, "evidence", {}) or {}
            if isinstance(ev, dict):
                orig_score = ev.get("name_similarity_score")
            else:
                orig_score = None
            cr_type = getattr(cr, "type", None) or "—"
        else:
            orig_score = None
            cr_type = "—"

        score_str = f"{orig_score:.0f}" if isinstance(orig_score, (int, float)) else "—"
        table_rows.append([
            _pretty_type(cr_type),
            score_str,
            f"{_verdict_glyph(v.match)} {v.match}",
            f"{int(v.confidence)}",
            _truncate(v.reason or "—", 70),
        ])

    state.write_table(
        ["Querbezug", "Original-Score", "LLM-Match", "LLM-Conf.", "Begruendung"],
        table_rows,
        col_widths=[150, 70, 70, 60, 145],
    )
    if len(verdicts) > DETAIL_ROW_LIMIT:
        state.write_text(
            f"… und {len(verdicts) - DETAIL_ROW_LIMIT} weitere Verdicts "
            f"(im JSON-Bericht vollständig enthalten).",
            size=8.5, color=COL_LIGHT, indent=4,
        )


def _render_corporate_group_section(state: _RenderState) -> None:
    """Konzernverbund-Erweiterung (Mai 2026, Item 2).

    Strikt faktisch: Anker-Firma + Mutter + Toechter aus GLEIF/Wikidata,
    plus eine Tabelle der ZUSAETZLICHEN State-Aid-/Beneficiary-Treffer aus
    Tochterfirmen. Quelle und Datenstand pro Eintrag werden sichtbar
    ausgewiesen.
    """
    cg = state.data.corporate_group
    if cg is None:
        return

    state.write_h1("Konzernverbund-Erweiterung")
    state.write_paragraph(
        "Diese Anwendung fuehrt KEINE eigene Konzern-Recherche durch. Die "
        "hier dargestellten Verbindungen stammen aus öffentlichen Dritt-"
        "Quellen (GLEIF / Wikidata) und sind je nach Eintragspflege bei der "
        "Quelle aktuell. Datenstand pro Eintrag in Spalte 'Datenstand'.",
        size=9.5,
    )
    state.cursor_y += 6

    # ── Sources / Cache-Stempel ──────────────────────────────────────────
    state.write_h3("Quellen und Lookup-Stand")
    state.write_kv(
        "Quellen:",
        ", ".join(cg.sources_used) if cg.sources_used else "(keine erreicht)",
        key_width=160,
    )
    fetched = cg.fetched_at
    if fetched:
        try:
            stamp = fetched.strftime("%Y-%m-%d %H:%M UTC")
        except Exception:  # noqa: BLE001
            stamp = str(fetched)
    else:
        stamp = "—"
    state.write_kv("Abgerufen am:", stamp, key_width=160)
    if cg.cache_meta:
        cache_state = cg.cache_meta.get("cache") or "—"
        state.write_kv(
            "Cache-Status:", str(cache_state), key_width=160,
        )
    state.cursor_y += 6

    # ── Anker / Mutter ───────────────────────────────────────────────────
    state.write_h3("Anker-Entity / Mutter")
    rows: list[list[str]] = []

    def _ent_row(label: str, e: dict | None) -> None:
        if not e:
            rows.append([label, "—", "—", "—", "—", "—"])
            return
        ds = e.get("data_freshness") or "—"
        if isinstance(ds, str) and len(ds) > 10:
            ds = ds[:10]
        rows.append([
            label,
            _truncate(str(e.get("name") or "—"), 38),
            str(e.get("country") or "—"),
            str(e.get("lei") or "—"),
            str(e.get("source") or "—"),
            str(ds),
        ])

    _ent_row("Anker (primaer)", cg.primary_entity)
    _ent_row("Direkte Mutter", cg.direct_parent)
    _ent_row("Ultimate Mutter", cg.ultimate_parent)
    state.write_table(
        ["Rolle", "Name", "Land", "LEI", "Quelle", "Datenstand"],
        rows,
        col_widths=[90, 165, 35, 80, 50, 75],
    )

    # ── Tochterfirmen ────────────────────────────────────────────────────
    state.cursor_y += 14
    state.write_h2(
        f"Tochterfirmen ({cg.children_count} gefunden, "
        f"hier max. {len(cg.children_top)})"
    )
    if not cg.children_top:
        state.write_paragraph(
            "Keine Tochterfirmen in den Quellen gefunden.",
            size=9.5, color=COL_LIGHT,
        )
    else:
        child_rows: list[list[str]] = []
        for c in cg.children_top:
            ds = c.get("data_freshness") or "—"
            if isinstance(ds, str) and len(ds) > 10:
                ds = ds[:10]
            child_rows.append([
                _truncate(str(c.get("name") or "—"), 50),
                str(c.get("country") or "—"),
                _truncate(str(c.get("lei") or "—"), 22),
                str(c.get("source") or "—"),
                str(ds),
            ])
        state.write_table(
            ["Name", "Land", "LEI", "Quelle", "Datenstand"],
            child_rows,
            col_widths=[225, 40, 100, 60, 70],
        )

    # ── Zusatztreffer State-Aid (über Toechter) ─────────────────────────
    state.cursor_y += 14
    state.write_h2(
        f"Zusaetzliche State-Aid-Treffer über Konzernfirmen "
        f"({cg.additional_state_aid_count} · "
        f"{cg.additional_state_aid_amount_eur:,.2f} EUR)"
    )
    state.write_paragraph(
        "Hinweis: Diese Treffer wurden NICHT über den ursprunglichen "
        "Suchbegriff gefunden, sondern über Tochterfirmen aus dem "
        "Konzernverbund. Sie sind hier separat ausgewiesen — nicht in der "
        "Direkt-Suche enthalten.",
        size=9, color=COL_LIGHT,
    )
    if cg.additional_state_aid_awards:
        rows_sa: list[list[str]] = []
        for a in cg.additional_state_aid_awards[:DETAIL_ROW_LIMIT]:
            via = (a.get("via_corporate_child") or {}).get("name") or "—"
            date_val = (a.get("granting_date") or "")[:10] or "—"
            ben = _truncate(a.get("beneficiary_name") or "—", 28)
            amt = a.get("aid_amount_eur") or 0.0
            amt_str = f"{amt:,.0f}"
            rows_sa.append([
                date_val,
                ben,
                _truncate(str(via), 28),
                str(a.get("country_code") or "—"),
                amt_str,
                str(a.get("sa_reference") or "—"),
            ])
        state.write_table(
            ["Datum", "Begünstigter", "über (Konzernfirma)", "Land",
             "Betrag EUR", "SA-Ref"],
            rows_sa,
            col_widths=[55, 110, 130, 35, 65, 100],
        )
        if len(cg.additional_state_aid_awards) > DETAIL_ROW_LIMIT:
            state.write_text(
                f"… und {len(cg.additional_state_aid_awards) - DETAIL_ROW_LIMIT} "
                f"weitere Treffer (im JSON-Bericht vollständig).",
                size=8.5, color=COL_LIGHT, indent=4,
            )
    else:
        state.write_paragraph(
            "Keine zusätzlichen State-Aid-Treffer über Konzernfirmen.",
            size=9.5, color=COL_LIGHT,
        )

    # ── Zusatztreffer Beneficiaries (über Toechter) ─────────────────────
    state.cursor_y += 14
    state.write_h2(
        f"Zusaetzliche Begünstigten-Treffer über Konzernfirmen "
        f"({cg.additional_beneficiaries_count} · "
        f"{cg.additional_beneficiaries_amount_eur:,.2f} EUR)"
    )
    if cg.additional_beneficiaries:
        rows_b: list[list[str]] = []
        for m in cg.additional_beneficiaries[:DETAIL_ROW_LIMIT]:
            via = (m.get("via_corporate_child") or {}).get("name") or "—"
            kosten = m.get("kosten") or 0.0
            rows_b.append([
                _truncate(str(m.get("company_name") or "—"), 28),
                _truncate(str(via), 28),
                _truncate(str(m.get("project_name") or "—"), 30),
                str(m.get("bundesland") or "—"),
                str(m.get("fonds") or "—"),
                f"{kosten:,.0f}",
            ])
        state.write_table(
            ["Beneficiary", "über (Konzernfirma)", "Vorhaben",
             "Bundesland", "Fonds", "Kosten EUR"],
            rows_b,
            col_widths=[110, 110, 130, 60, 35, 60],
        )
        if len(cg.additional_beneficiaries) > DETAIL_ROW_LIMIT:
            state.write_text(
                f"… und {len(cg.additional_beneficiaries) - DETAIL_ROW_LIMIT} "
                f"weitere Treffer (im JSON-Bericht vollständig).",
                size=8.5, color=COL_LIGHT, indent=4,
            )
    else:
        state.write_paragraph(
            "Keine zusätzlichen Begünstigten-Treffer über Konzernfirmen.",
            size=9.5, color=COL_LIGHT,
        )

    # ── Coverage-Note ────────────────────────────────────────────────────
    state.cursor_y += 14
    state.write_h3("Hinweis zur Datenabdeckung")
    state.write_paragraph(cg.coverage_note or "—", size=9, color=COL_LIGHT)


def _render_sources_explanation(state: _RenderState) -> None:
    """Quellen und Datenstand — eigene Sektion mit Texten + Daten.

    Wird sowohl im PDF als auch im JSON ausgeliefert (gleiche Inhalte).
    """
    data = state.data
    state.write_h1("Quellen und Datenstand")
    state.write_paragraph(
        "Der Bericht nutzt drei öffentliche Datenquellen. Für jede Quelle "
        "wird hier der lokale Datenstand und die Anzahl der lokal "
        "verfügbaren Records ausgewiesen.",
        size=9.5,
    )
    state.cursor_y += 6

    if not data.sources_explanation:
        state.write_paragraph(
            "Keine Quellen-Erlaeuterung verfügbar.",
            size=9.5, color=COL_LIGHT,
        )
        return

    for src in data.sources_explanation:
        state.ensure_space(60)
        state.write_h3(src.name)
        state.write_text(f"Quelle: {src.url}", size=9, color=COL_LIGHT, indent=4)
        state.write_paragraph(src.description, size=9.5, indent=4)
        # Lokaler Datenstand
        if src.last_data_update:
            try:
                stand = src.last_data_update.strftime("%Y-%m-%d %H:%M UTC")
            except Exception:  # noqa: BLE001
                stand = str(src.last_data_update)
        else:
            stand = "— (kein Datum hinterlegt)"
        state.write_kv("Lokaler Datenstand:", stand, key_width=160)
        state.write_kv("Records lokal:", f"{src.record_count:,}".replace(",", "."),
                       key_width=160)
        state.cursor_y += 6


# ── Personen-Sanctions-Sektion (Polish-Runde 3, Aufgabe 1) ──────────────────


# Kuerzel pro Source-Key — kompakte Tabellen-Spalte.
_PERSON_SOURCE_LABELS = {
    "eu_fsf": "EU FSF",
    "un_sc": "UN SC",
    "us_ofac_sdn": "OFAC",
    "gb_hmt_sanctions": "UK OFSI",
    "ch_seco": "SECO",
}


def _render_persons_check_section(state: _RenderState) -> None:
    """Personen-Sanctions-Check als eigene PDF-Sektion.

    Strikt neutral. Pro Person eine Tabellenzeile pro Treffer (oder eine
    Zeile mit "kein Treffer"). Bei 0 Treffern aller Personen schlichter Satz.
    """
    pc = state.data.persons_check
    if pc is None:
        return

    state.write_h1("Personen-Sanktionscheck")
    state.write_paragraph(
        "Sanctions-Check für die vom Prüfer eingegebenen Personen "
        "(Geschäftsführer, UBO, Gesellschafter o.ae.) gegen alle 5 "
        "Sanctions-Listen mit schema='Person'. Strikt faktisch, keine "
        "Bewertung. Ein Personen-Match ohne Geburtsdatum-Abgleich ist "
        "eine Indikation, kein Beweis.",
        size=9.5,
    )
    state.cursor_y += 4
    if pc.coverage_note:
        state.write_paragraph(pc.coverage_note, size=9, color=COL_LIGHT)
    state.cursor_y += 6

    state.write_kv("Personen geprüft:", str(pc.total_persons))
    state.write_kv("Mit Treffer (Score >= 80):", str(pc.persons_with_match))
    state.cursor_y += 8

    if pc.total_persons == 0:
        state.write_paragraph(
            "Keine Personen übergeben.",
            size=10, color=COL_LIGHT,
        )
        return

    # Globaler Kurztext, wenn 0 Treffer aller Personen.
    if pc.persons_with_match == 0:
        state.write_paragraph(
            "Keine der Personen erscheint in einer der 5 Sanktionslisten "
            "(Score-Schwelle 80).",
            size=10, bold=True,
        )
        state.cursor_y += 8

    # Detail-Tabelle: Eine Zeile pro Treffer, oder bei 0 Treffern eine
    # Zeile mit "kein Treffer".
    detail_rows: list[list[str]] = []
    for p in pc.persons_checked:
        if not p.hits:
            detail_rows.append([
                _truncate(p.name, 30),
                _truncate(p.role or "—", 18),
                "nein",
                "—", "—", "—", "—", "—", "—",
            ])
            continue
        # Ein Eintrag pro Treffer, max. 3 Treffer pro Person für die Tabelle.
        for h in p.hits[:3]:
            score_val = h.get("score") or 0
            score_str = f"{score_val:.1f}"
            confidence = h.get("confidence") or "—"
            source_key = h.get("source_key") or "—"
            source_label = _PERSON_SOURCE_LABELS.get(
                source_key, source_key.upper()[:8],
            )
            # Programm: erstes Element aus sanctions/program_ids
            san_list = h.get("sanctions") or []
            prog_ids = h.get("program_ids") or []
            if isinstance(san_list, str):
                program = san_list
            elif isinstance(san_list, list) and san_list:
                program = "; ".join(str(s) for s in san_list[:2])
            elif isinstance(prog_ids, list) and prog_ids:
                program = "; ".join(str(s) for s in prog_ids[:2])
            else:
                program = "—"
            aliases_full = h.get("aliases") or []
            aliases_short = "; ".join(str(a) for a in aliases_full[:2])
            if len(aliases_full) > 2:
                aliases_short = (aliases_short + " …") if aliases_short else "…"
            birth = (h.get("birth_date") or "—") or "—"
            countries = h.get("countries") or "—"
            detail_rows.append([
                _truncate(p.name, 30),
                _truncate(p.role or "—", 18),
                "ja",
                score_str,
                confidence,
                source_label,
                _truncate(aliases_short, 28),
                _truncate(str(birth), 12),
                _truncate(str(countries), 14),
            ])
            # Programm in eigene zweite Spalte? Wir zeigen Programm in der
            # `Aliases`-Spalte zusammen — Platz im A4 ist begrenzt.
        # Markierung weitere Treffer
        if len(p.hits) > 3:
            detail_rows.append([
                _truncate(p.name, 30),
                _truncate(p.role or "—", 18),
                f"+{len(p.hits) - 3} weitere",
                "—", "—", "—", "—", "—", "—",
            ])

    state.write_table(
        ["Name", "Rolle", "Treffer", "Score", "Konfidenz",
         "Liste", "Aliases (max. 2)", "Geburtsdatum", "Land"],
        detail_rows,
        col_widths=[80, 50, 40, 35, 50, 45, 90, 50, 55],
    )

    state.cursor_y += 6
    state.write_paragraph(
        "Hinweis: Russisch-/kyrillisch-Transliterationen erzeugen häufige "
        "Namensgleichheiten. Ein Treffer ohne Geburtsdatum-/Identifier-"
        "Abgleich ist eine Indikation, kein Beweis. Die fachliche "
        "Beurteilung obliegt dem Prüfer.",
        size=8.5, color=COL_LIGHT,
    )


# ── Coverage / Vollständigkeit (Polish-Runde 3, Aufgabe 3) ─────────────────


def _render_coverage_section(state: _RenderState) -> None:
    """Coverage-Sektion: Pro Quelle lokal/erwartet/Coverage% + Status.

    WARTUNGS-Aussage, KEINE Risiko-Bewertung. Die Status-Spalte
    (`vollständig`/`partiell`/`unbekannt`) sagt aus, ob der lokale
    Bestand der Prüfumgebung dem Stand der Quelle entspricht — nicht,
    ob die geprüften Firmen ein Risiko darstellen.
    """
    cov = state.data.coverage
    if cov is None:
        return

    state.write_h1("Coverage und Datenstand")
    state.write_paragraph(
        "Wartungs-Aussage über den lokalen Datenbestand. Pro Quelle wird "
        "angezeigt, wie viele Records lokal vorliegen und wie viele die "
        "externe Quelle (sofern bekannt) zum letzten Harvest gemeldet hat. "
        "Status `partiell` bedeutet: die lokale Kopie ist nicht vollständig "
        "— eine vollständige Prüfung erfordert zusätzliche Recherche im "
        "Original-Register. KEINE Risiko-Aussage über die geprüften Firmen.",
        size=9.5,
    )
    state.cursor_y += 6

    # Wartungs-Ampel
    overall_label = {
        "green": "vollständig (>=95% pro Quelle)",
        "yellow": "partiell oder unbekannt (mindestens eine Quelle)",
        "red": "unvollständig (mindestens eine Quelle <50%)",
    }.get(cov.overall_completeness, str(cov.overall_completeness))
    state.write_kv("Wartungs-Status:", overall_label, key_width=160)
    state.cursor_y += 6

    if not cov.entries:
        state.write_paragraph(
            "(keine Coverage-Daten verfügbar)",
            size=9, color=COL_LIGHT,
        )
        return

    # Tabelle pro Eintrag
    rows: list[list[str]] = []
    module_labels = {
        "state_aid": "State-Aid",
        "beneficiary": "Beneficiaries",
        "sanctions": "Sanctions",
    }
    for e in cov.entries:
        cov_str = (
            f"{e.coverage_percent:.1f}%"
            if e.coverage_percent is not None else "—"
        )
        last = "—"
        if e.last_harvest_at:
            try:
                last = e.last_harvest_at.strftime("%Y-%m-%d")
            except Exception:  # noqa: BLE001
                last = str(e.last_harvest_at)[:10]
        rows.append([
            module_labels.get(e.source_module, e.source_module),
            _truncate(e.display_name or e.source_key, 32),
            f"{e.local_count:,}".replace(",", "."),
            (
                f"{e.expected_count:,}".replace(",", ".")
                if e.expected_count is not None else "—"
            ),
            cov_str,
            last,
            e.completeness_note,
        ])
    state.write_table(
        ["Modul", "Quelle", "Lokal", "Erwartet",
         "Coverage", "Letzter Harvest", "Status"],
        rows,
        col_widths=[55, 130, 55, 55, 55, 70, 65],
    )

    # Hinweis bei partiell
    has_partial = any(
        e.completeness_note == "partiell" for e in cov.entries
    )
    if has_partial:
        state.cursor_y += 6
        state.write_paragraph(
            "Hinweis: Eine oder mehrere Quellen haben Coverage < 95 %. Der "
            "lokale Bestand deckt nur einen Teil der Quelle ab. Eine "
            "vollständige Prüfung erfordert zusätzliche Recherche im "
            "Original-Register.",
            size=9, color=COL_LIGHT,
        )


def _render_appendix(state: _RenderState) -> None:
    """Anhang: Datenstand-Tabelle + Pflichthinweis + Disclaimer-Block."""
    data = state.data
    state.write_h1("Anhang")

    # ── Datenstand-Tabelle (kompakt) ────────────────────────────────────────
    state.write_h2("Datenstand pro Quelle (Kurzform)")
    rows = []
    sa = data.data_freshness.get("state_aid") or {}
    rows.append([
        "EU-State-Aid (TAM + national)",
        sa.get("as_of") or "—",
        str(sa.get("record_count") or "—"),
        sa.get("note") or "—",
    ])
    bn = data.data_freshness.get("beneficiaries") or {}
    rows.append([
        "Begünstigtenverzeichnis (lokal)",
        bn.get("as_of") or "—",
        "—",
        bn.get("note") or "—",
    ])
    sn = data.data_freshness.get("sanctions") or {}
    rows.append([
        "EU FSF (OpenSanctions)",
        (sn.get("as_of") or "—")[:19],
        str(sn.get("record_count") or "—"),
        sn.get("note") or "—",
    ])
    state.write_table(
        ["Quelle", "Stand", "Records", "Hinweis"],
        rows,
        col_widths=[170, 110, 60, 155],
    )

    # ── Pflichthinweis (Plan §13) ───────────────────────────────────────────
    state.cursor_y += 18
    state.write_h2("Pflichthinweis (Plan §13)")
    from services.state_aid_audit_report import pflichthinweis
    state.write_paragraph(pflichthinweis(data), size=8.5, color=COL_LIGHT)

    # ── Disclaimer-Block ────────────────────────────────────────────────────
    state.cursor_y += 18
    state.write_h2("Hinweise zur Anwendung")
    _draw_disclaimer_box(state, data.disclaimer)

    state.cursor_y += 12
    state.write_paragraph(
        "Hinweis für den Anwender: Dieser Bericht enthält bewusst keine "
        "Bewertung und keine Empfehlung. Er listet die in den drei "
        "Registern aufgefundenen Datensaetze und neutralen Querbezüge auf. "
        "Die fachliche Einordnung — ob ein Treffer relevant oder redundant "
        "ist — erfolgt allein durch den Prüfer.",
        size=8.5, color=COL_LIGHT,
    )


def _draw_disclaimer_box(state: _RenderState, text: str) -> None:
    """Zeichnet den Disclaimer als eigene Box mit duenner Border.

    Helvetica 9pt, klar lesbar. Bricht bei Bedarf auf neue Seite und
    setzt die Box dort fort.
    """
    if not text:
        return

    # Box-Padding
    padding = 8.0
    text_size = 9.0
    line_h = text_size + 3

    # Wir berechnen die Höhe der Box durch einfaches Zaehlen der Zeilen
    # nach Word-Wrap. Damit kann die Border einigermassen passend
    # gezeichnet werden, auch wenn Page-Break passiert.
    chars_per_line = max(40, int((USABLE_WIDTH - 2 * padding) / (text_size * 0.52)))
    wrapped_lines: list[str] = []
    for raw_line in str(text).splitlines():
        words = raw_line.split()
        if not words:
            wrapped_lines.append("")
            continue
        line = ""
        for w in words:
            candidate = (line + " " + w).strip()
            if len(candidate) <= chars_per_line:
                line = candidate
            else:
                if line:
                    wrapped_lines.append(line)
                line = w
        if line:
            wrapped_lines.append(line)

    # Wenn die Box auf der aktuellen Seite nicht mehr ganz passt, brechen wir.
    box_h = padding * 2 + len(wrapped_lines) * line_h + 4
    if state.cursor_y + box_h > FOOTER_TOP - 10:
        state.new_page()

    box_top = state.cursor_y
    # Border
    try:
        state.page.draw_rect(
            (MARGIN, box_top, PAGE_WIDTH - MARGIN, box_top + box_h),
            color=COL_LINE, width=0.5,
        )
    except Exception:  # noqa: BLE001
        pass

    state.cursor_y = box_top + padding + text_size
    for line in wrapped_lines:
        # Wenn ein einzelnes Page-Break in der Mitte noetig wird, schliessen
        # wir die Box hier nicht erneut; das passiert in der Praxis nicht
        # bei der aktuellen Disclaimer-Laenge.
        if state.cursor_y + line_h > FOOTER_TOP - 10:
            state.new_page()
            state.cursor_y = MARGIN + 30
        try:
            state.page.insert_text(
                (MARGIN + padding, state.cursor_y), line,
                fontsize=text_size, fontname="helv", color=COL_TEXT,
            )
        except Exception:  # noqa: BLE001
            state.page.insert_text(
                (MARGIN + padding, state.cursor_y), line,
                fontsize=text_size,
            )
        state.cursor_y += line_h
    state.cursor_y = box_top + box_h + 4


# ── Helfer ────────────────────────────────────────────────────────────────────


def _pretty_type(t: str) -> str:
    return {
        "name_match_state_aid_beneficiary":
            "Name-Übereinstimmung State-Aid <-> Begünstigtenverzeichnis",
        "identifier_match":
            "Identifier-Übereinstimmung (HRB / Steuer-Nr.)",
        "sa_reference_kom_case_linked":
            "SA-Referenz mit verlinktem KOM-Fall",
        "duplicate_award_within_year":
            "Mehrere Awards innerhalb 12-Monats-Fenster",
        "address_match":
            "Adress-Übereinstimmung",
        # Layer A — Semantische Nachbarschaft (Embedding-Layer, bge-m3)
        "semantic_neighbor_state_aid":
            "Semantischer Nachbar (State-Aid)",
        "semantic_neighbor_beneficiary":
            "Semantischer Nachbar (Begünstigtenverzeichnis)",
        "semantic_neighbor_sanctions":
            "Semantischer Nachbar (Sanctions)",
    }.get(t, t)


def _short(value, n: int = 120) -> str:
    s = str(value or "")
    if len(s) > n:
        return s[:n - 1] + "…"
    return s


def _truncate(value: str, n: int) -> str:
    """Kuerzt einen String auf n Zeichen mit Suffix '…' bei Bedarf."""
    s = str(value or "")
    if len(s) <= n:
        return s
    return s[:max(1, n - 1)] + "…"
