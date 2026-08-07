"""
flowworkshop · services/pdf_vorhabenliste.py

Liest eine „Liste der Vorhaben" aus einem PDF.

Das Saarland veröffentlicht seine Liste ausschließlich als PDF, andere
Länder könnten folgen. Die Datei enthält echten Text — die Tabelle lässt
sich also direkt auslesen, ohne Texterkennung.

Für gescannte PDFs steht eine OCR-Rückfallebene bereit. Sie ist bewusst
abgeschaltet, solange sie niemand braucht: Zahlen aus einer Texterkennung
sind nicht ohne Weiteres beweistauglich, und ein stillschweigend
OCR-gelesener Förderbetrag hat in einem Prüfdatenbestand nichts verloren.
Einschalten über ``BENEFICIARY_PDF_OCR=true``; die betroffenen Läufe
protokollieren dann eine Warnung.
"""
from __future__ import annotations

import io
import logging
import os
import re
from typing import Any

log = logging.getLogger(__name__)

# Texterkennung als Rückfallebene für gescannte PDFs — standardmäßig aus.
PDF_OCR_AKTIV = os.environ.get("BENEFICIARY_PDF_OCR", "false").lower() == "true"

# Unterhalb dieser Zeichenzahl je Seite gilt ein PDF als gescannt.
MIN_ZEICHEN_JE_SEITE = 100

# Woran die Kopfzeile der Tabelle erkannt wird.
KOPF_MARKER = (
    "name des begünstigten", "name des beguenstigten", "beneficiary name",
    "zuwendungsempfänger", "begünstigter",
)


def _saeubere(zelle: Any) -> str:
    """Zellentext glätten: Zeilenumbrüche innerhalb einer Zelle sind Layout,
    keine Bedeutung."""
    if zelle is None:
        return ""
    return re.sub(r"\s+", " ", str(zelle)).strip()


def ist_gescannt(inhalt: bytes) -> bool:
    """True, wenn das PDF praktisch keinen auslesbaren Text enthält."""
    import fitz

    with fitz.open(stream=inhalt, filetype="pdf") as doc:
        if doc.page_count == 0:
            return True
        zeichen = sum(len(doc[i].get_text()) for i in range(doc.page_count))
        return zeichen < MIN_ZEICHEN_JE_SEITE * doc.page_count


def _ist_kopfzeile(zeile: list[str]) -> bool:
    verbunden = " | ".join(zeile).lower()
    return any(marker in verbunden for marker in KOPF_MARKER)


def lies_tabelle(inhalt: bytes) -> list[list[str]]:
    """Sammelt die Tabellenzeilen aller Seiten.

    Liefert eine Liste von Zeilen, die erste ist die Kopfzeile.

    Zwei Eigenheiten mehrseitiger Behörden-PDFs werden dabei behandelt: die
    Kopfzeile wiederholt sich auf jeder Seite, und über der Tabelle steht
    oft noch eine Titelzeile, die über die gesamte Breite verbunden ist.
    """
    import pdfplumber

    kopf: list[str] | None = None
    zeilen: list[list[str]] = []

    with pdfplumber.open(io.BytesIO(inhalt)) as pdf:
        for seite in pdf.pages:
            for tabelle in seite.extract_tables():
                for roh in tabelle:
                    zeile = [_saeubere(z) for z in roh]
                    if not any(zeile):
                        continue
                    # Titelzeile: nur die erste Spalte gefüllt.
                    if sum(1 for z in zeile if z) < 2:
                        continue
                    if _ist_kopfzeile(zeile):
                        if kopf is None:
                            kopf = zeile
                        # Wiederholung auf Folgeseiten überspringen.
                        continue
                    if kopf is None:
                        continue
                    zeilen.append(zeile)

    if kopf is None:
        raise ValueError(
            "Im PDF wurde keine Kopfzeile mit einer Begünstigtenspalte gefunden."
        )
    return [kopf, *zeilen]


def _ocr_tabelle(inhalt: bytes) -> list[list[str]]:
    """Rückfallebene für gescannte PDFs.

    Bewusst schlicht: die Seiten werden als Text erkannt und zeilenweise an
    zwei oder mehr Leerzeichen getrennt. Das trifft einfache Tabellen, ist
    aber keine verlässliche Spaltenerkennung — deshalb die Warnung.
    """
    import fitz
    import pytesseract
    from PIL import Image

    log.warning(
        "PDF wird per Texterkennung gelesen. Die Ergebnisse sind NICHT "
        "beweistauglich und müssen fachlich geprüft werden."
    )
    zeilen: list[list[str]] = []
    with fitz.open(stream=inhalt, filetype="pdf") as doc:
        for nr in range(doc.page_count):
            bild = doc[nr].get_pixmap(dpi=300)
            text = pytesseract.image_to_string(
                Image.open(io.BytesIO(bild.tobytes("png"))), lang="deu",
            )
            for roh in text.splitlines():
                felder = [f.strip() for f in re.split(r"\s{2,}", roh) if f.strip()]
                if len(felder) >= 3:
                    zeilen.append(felder)
    if not zeilen:
        raise ValueError("Texterkennung lieferte keine verwertbaren Zeilen.")

    kopf_index = next(
        (i for i, z in enumerate(zeilen) if _ist_kopfzeile(z)), None,
    )
    if kopf_index is None:
        raise ValueError(
            "Texterkennung fand keine Kopfzeile mit einer Begünstigtenspalte."
        )
    return zeilen[kopf_index:]


def lies_vorhabenliste(inhalt: bytes) -> Any:
    """Liest die Liste der Vorhaben aus einem PDF und liefert einen DataFrame.

    Die Rückgabe hat dieselbe Form wie bei XLSX und CSV, damit Spalten-
    erkennung, Validierung und Hashing unverändert weiterarbeiten.
    """
    import pandas as pd

    if ist_gescannt(inhalt):
        if not PDF_OCR_AKTIV:
            raise ValueError(
                "PDF enthält keinen auslesbaren Text (Scan). Texterkennung ist "
                "abgeschaltet — mit BENEFICIARY_PDF_OCR=true aktivierbar, die "
                "Ergebnisse sind dann fachlich zu prüfen."
            )
        zeilen = _ocr_tabelle(inhalt)
    else:
        zeilen = lies_tabelle(inhalt)

    kopf, *daten = zeilen
    breite = len(kopf)
    # Zeilen auf die Kopfbreite bringen: kürzere auffüllen, längere kappen.
    normiert = [(z + [""] * breite)[:breite] for z in daten]
    return pd.DataFrame(normiert, columns=kopf)
