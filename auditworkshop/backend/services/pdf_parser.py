"""
flowworkshop · pdf_parser.py
Multi-Level PDF-Textextraktion.

Level 1: pdfplumber  — direkte Textschicht (schnell, <100 ms)
Level 2: PyMuPDF     — Layout-basiert, besser bei Tabellen
Level 3: Tesseract   — OCR-Fallback für Scans (langsam)
"""
from __future__ import annotations
import io
import logging

log = logging.getLogger(__name__)

MIN_CHARS = 80   # Schwelle: weniger → nächste Stufe versuchen


def extract(file_bytes: bytes, filename: str = "") -> dict:
    """
    Extrahiert Text aus einem PDF.

    Returns:
        {
          "text": str,
          "method": "pdfplumber" | "pymupdf" | "ocr",
          "pages": int,
          "char_count": int,
          "warnings": list[str]
        }
    """
    if len(file_bytes) > 50 * 1024 * 1024:
        raise ValueError("Datei zu groß (max. 50 MB).")

    warnings: list[str] = []

    # Level 1 — pdfplumber
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            pages = len(pdf.pages)
            text = "\n\n".join(p.extract_text() or "" for p in pdf.pages).strip()
        if len(text) >= MIN_CHARS:
            return {"text": text, "method": "pdfplumber",
                    "pages": pages, "char_count": len(text), "warnings": warnings}
        warnings.append("pdfplumber: zu wenig Text — weiter mit PyMuPDF")
    except Exception as e:
        warnings.append(f"pdfplumber: {e}")
        pages = 0

    # Level 2 — PyMuPDF
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        pages = doc.page_count
        text = "\n\n".join(page.get_text() for page in doc).strip()
        doc.close()
        if len(text) >= MIN_CHARS:
            return {"text": text, "method": "pymupdf",
                    "pages": pages, "char_count": len(text), "warnings": warnings}
        warnings.append("PyMuPDF: zu wenig Text — weiter mit OCR")
    except fitz.FileDataError:
        raise ValueError("PDF ist passwortgeschützt oder beschädigt.")
    except Exception as e:
        warnings.append(f"PyMuPDF: {e}")

    # Level 3 — Tesseract OCR
    try:
        import fitz
        import pytesseract
        from PIL import Image

        doc = fitz.open(stream=file_bytes, filetype="pdf")
        pages = doc.page_count
        texts = []
        for page in doc:
            pix = page.get_pixmap(dpi=200)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            texts.append(pytesseract.image_to_string(img, lang="deu+eng"))
        doc.close()
        text = "\n\n".join(texts).strip()
        return {"text": text, "method": "ocr",
                "pages": pages, "char_count": len(text), "warnings": warnings}
    except Exception as e:
        warnings.append(f"OCR: {e}")

    return {"text": "", "method": "failed",
            "pages": pages, "char_count": 0, "warnings": warnings}
