"""Generisches EUR-Lex-Reingest: liest eine als Text gespeicherte
EUR-Lex-Konsolidierungsfassung (per Browser geladen) in die Wissensbasis ein.

Aufruf im Backend-Container:
    python scripts/reingest_eurlex.py <textdatei> <SOURCE> <filename>

<textdatei> darf der rohe innerText sein ODER ein JSON-String (Playwright-
evaluate-Ergebnis mit literalen \\n) — beides wird erkannt.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import knowledge_service as ks  # noqa: E402


def clean(text: str) -> str:
    # EUR-Lex-Konsolidierungsmarker entfernen (▼B, ▼M1, ►C1, ◄ …) + Whitespace normalisieren.
    text = re.sub(r"[►▼◄][A-ZÄÖÜ]?\d*", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def main(path: str, source: str, filename: str) -> None:
    raw = open(path, encoding="utf-8").read()
    try:
        text = json.loads(raw)
    except json.JSONDecodeError:
        text = raw
    text = clean(text)
    print(f"{source}: {len(text)} Zeichen nach Bereinigung")
    deleted = ks.delete_source(source)
    print(f"  alte Chunks gelöscht: {deleted}")
    res = ks.ingest(text, source, filename)
    print(f"  Ingest: {res}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
