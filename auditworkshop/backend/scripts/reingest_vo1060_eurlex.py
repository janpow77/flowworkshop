"""Liest VO (EU) 2021/1060 neu aus der EUR-Lex-Konsolidierungsfassung ein.

Hintergrund: Die fruehere PDF-Extraktion (pdfplumber) lieferte fuer einen Teil
der Seiten zeichen-/run-reversierten Text. Saubere Quelle ist die konsolidierte
HTML-Fassung von EUR-Lex (CELEX 02021R1060-20251025), per Browser geladen und
als Text gespeichert.

Aufruf im Backend-Container:
    python scripts/reingest_vo1060_eurlex.py /app/data/vo1060_eurlex.txt
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import knowledge_service as ks  # noqa: E402

SOURCE = "VO_2021_1060_DE"
FILENAME = "celex_02021R1060-20251025_de.html"


def clean(text: str) -> str:
    # EUR-Lex-Konsolidierungsmarker entfernen: ▼B, ▼M1, ►C1, ►M2, ◄ …
    text = re.sub(r"[►▼◄][A-ZÄÖÜ]?\d*", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def main(path: str) -> None:
    raw = open(path, encoding="utf-8").read()
    try:
        text = json.loads(raw)  # evaluate-Ergebnis ist ein JSON-String
    except json.JSONDecodeError:
        text = raw
    text = clean(text)
    print(f"Textlänge nach Bereinigung: {len(text)} Zeichen")

    deleted = ks.delete_source(SOURCE)
    print(f"Alte Chunks gelöscht: {deleted}")

    res = ks.ingest(text, SOURCE, FILENAME)
    print(f"Ingest: {res}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/app/data/vo1060_eurlex.txt")
