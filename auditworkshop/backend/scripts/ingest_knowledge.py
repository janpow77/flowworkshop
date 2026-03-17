#!/usr/bin/env python3
"""
flowworkshop · scripts/ingest_knowledge.py

Lädt öffentliche EU-Rechtsdokumente herunter und speichert sie
in der pgvector-Wissensdatenbank.

Aufruf (aus backend/):
    python scripts/ingest_knowledge.py

Für eigene Dokumente (lokal):
    python scripts/ingest_knowledge.py --file /pfad/zur/datei.pdf --source mein_bescheid
"""
import argparse
import sys
import os
import requests
from pathlib import Path

# Pfad zum Backend-Verzeichnis
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.knowledge_service import init_db, ingest, stats
from services.pdf_parser import extract

RAW_DIR = Path(__file__).parent.parent / "data" / "knowledge_raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

# Öffentlich zugängliche Quellen (EU-Recht, kein Urheberrecht)
SOURCES = [
    {
        "source":   "VO_2021_1060_DE",
        "filename": "vo_2021_1060_de.pdf",
        "url":      "https://eur-lex.europa.eu/legal-content/DE/TXT/PDF/?uri=CELEX:32021R1060",
        "label":    "Dachverordnung VO (EU) 2021/1060",
    },
    {
        "source":   "VO_2021_1058_DE",
        "filename": "vo_2021_1058_de.pdf",
        "url":      "https://eur-lex.europa.eu/legal-content/DE/TXT/PDF/?uri=CELEX:32021R1058",
        "label":    "EFRE-Verordnung VO (EU) 2021/1058",
    },
    {
        "source":   "EU_AI_ACT_DE",
        "filename": "eu_ai_act_2024_1689_de.pdf",
        "url":      "https://eur-lex.europa.eu/legal-content/DE/TXT/PDF/?uri=CELEX:32024R1689",
        "label":    "EU AI Act VO (EU) 2024/1689",
    },
]


def download(url: str, dest: Path) -> bytes:
    if dest.exists():
        print(f"  ✓ Bereits vorhanden: {dest.name}")
        return dest.read_bytes()
    print(f"  ↓ Lade herunter: {url}")
    r = requests.get(url, timeout=60, headers={"User-Agent": "flowworkshop/1.0"})
    r.raise_for_status()
    dest.write_bytes(r.content)
    print(f"  ✓ Gespeichert: {dest.name} ({len(r.content) // 1024} KB)")
    return r.content


def ingest_file(file_bytes: bytes, filename: str, source: str, label: str):
    print(f"  → Extrahiere Text …")
    parsed = extract(file_bytes, filename)
    if not parsed["text"]:
        print(f"  ✗ Kein Text extrahierbar. Warnungen: {parsed['warnings']}")
        return
    print(f"  → {parsed['pages']} Seiten, {parsed['char_count']} Zeichen ({parsed['method']})")
    result = ingest(parsed["text"], source=source, filename=filename)
    print(f"  ✓ {result['chunks_stored']} Chunks gespeichert → {label}")


def main():
    parser = argparse.ArgumentParser(description="Wissensdatenbank befüllen")
    parser.add_argument("--file", help="Lokale PDF-Datei einlesen")
    parser.add_argument("--source", help="Logischer Name für die Quelle")
    parser.add_argument("--all", action="store_true", help="Alle Standard-Quellen laden")
    args = parser.parse_args()

    print("\nflowworkshop · Wissensdatenbank-Ingest")
    print("=" * 50)

    init_db()

    if args.file and args.source:
        # Einzelne lokale Datei
        path = Path(args.file)
        if not path.exists():
            print(f"Datei nicht gefunden: {path}")
            sys.exit(1)
        print(f"\n[LOKAL] {path.name}")
        ingest_file(path.read_bytes(), path.name, args.source, args.source)

    elif args.all or not (args.file or args.source):
        # Alle Standard-Quellen (Online)
        for s in SOURCES:
            print(f"\n[{s['source']}] {s['label']}")
            try:
                content = download(s["url"], RAW_DIR / s["filename"])
                ingest_file(content, s["filename"], s["source"], s["label"])
            except Exception as e:
                print(f"  ✗ Fehler: {e}")

        # Alle lokalen PDFs die noch nicht geladen sind
        existing = {src["filename"] for src in stats()["sources"]}
        local_files = sorted(RAW_DIR.glob("*.pdf"))
        for path in local_files:
            if path.name in existing:
                continue
            source_name = path.stem.upper().replace("-", "_")
            print(f"\n[LOKAL] {path.name} → {source_name}")
            try:
                ingest_file(path.read_bytes(), path.name, source_name, source_name)
            except Exception as e:
                print(f"  ✗ Fehler: {e}")

    # Abschlussbericht
    s = stats()
    print(f"\n{'=' * 50}")
    print(f"Wissensdatenbank: {s['documents']} Dokumente · {s['chunks']} Chunks")
    for src in s["sources"]:
        print(f"  {src['source']:<30} {src['chunks']:>4} Chunks  ({src['filename']})")


if __name__ == "__main__":
    main()
