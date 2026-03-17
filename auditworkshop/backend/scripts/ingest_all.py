#!/usr/bin/env python3
"""
flowworkshop · scripts/ingest_all.py
Liest alle OP-Dokumente und Begünstigtenverzeichnisse ein.

Nutzung:
  docker exec auditworkshop-backend python scripts/ingest_all.py --knowledge
  docker exec auditworkshop-backend python scripts/ingest_all.py --dataframes
  docker exec auditworkshop-backend python scripts/ingest_all.py --all
"""
import argparse
import sys
import os
from pathlib import Path

# Backend-Pfad einrichten
sys.path.insert(0, str(Path(__file__).parent.parent))

KNOWLEDGE_RAW = Path("/app/data/knowledge_raw")

# Source-Label-Mapping: Dateiname → logischer Name
PDF_SOURCES = {
    "efre_programm_2021_2027.pdf": "EFRE_PROGRAMM_HESSEN_2021_2027",
    "efre_foerderrichtlinie.pdf": "EFRE_FOERDERRICHTLINIE_21",
    "efre_foerderaufruf_1.pdf": "EFRE_FOERDERAUFRUF_1",
    "efre_foerderaufruf_2.pdf": "EFRE_FOERDERAUFRUF_2",
    "efre_foerderaufruf_3.pdf": "EFRE_FOERDERAUFRUF_3",
    "efre_foerderaufruf_4.pdf": "EFRE_FOERDERAUFRUF_4",
    "efre_merkblatt_gemeinkosten.pdf": "EFRE_MERKBLATT_GEMEINKOSTEN",
    "efre_merkblatt_sek_saetze.pdf": "EFRE_MERKBLATT_SEK_SAETZE",
    "efre_merkblatt_grundrechte.pdf": "EFRE_MERKBLATT_GRUNDRECHTE",
    "efre_merkblatt_gleichstellung.pdf": "EFRE_MERKBLATT_GLEICHSTELLUNG",
    "efre_merkblatt_nachhaltigkeit.pdf": "EFRE_MERKBLATT_NACHHALTIGKEIT",
    "efre_merkblatt_sachleistungen.pdf": "EFRE_MERKBLATT_SACHLEISTUNGEN",
    "efre_merkblatt_unternehmen_schwierigkeiten.pdf": "EFRE_MERKBLATT_UNTERNEHMEN",
    "efre_merkblatt_belegaufbewahrung.pdf": "EFRE_MERKBLATT_BELEGAUFBEWAHRUNG",
    "efre_merkblatt_vergabe_wertgrenzen.pdf": "EFRE_MERKBLATT_VERGABE_WERTGRENZEN",
    "efre_merkblatt_vergaberecht.pdf": "EFRE_MERKBLATT_VERGABERECHT",
    "efre_merkblatt_umwelt_auswahlkriterien.pdf": "EFRE_MERKBLATT_UMWELT_AUSWAHLKRITERIEN",
    "efre_zusammenfassende_erklaerung.pdf": "EFRE_ZUSAMMENFASSENDE_ERKLAERUNG",
    "efre_umweltbericht.pdf": "EFRE_UMWELTBERICHT",
    "efre_laenderbericht_2019.pdf": "LAENDERBERICHT_DE_2019",
    "efre_informationsbroschuere.pdf": "EFRE_INFORMATIONSBROSCHUERE",
    "efre_foerderaufruf_umwelt_2025.pdf": "EFRE_FOERDERAUFRUF_UMWELT_2025",
    "efre_aufruf_pius.pdf": "EFRE_AUFRUF_PIUS",
}

XLSX_SOURCES = {
    "efre_zeitplan_aufforderungen.xlsx": "EFRE_ZEITPLAN_AUFFORDERUNGEN",
}


def ingest_knowledge():
    """Liest alle PDFs und XLSX in die pgvector Knowledge-Base ein."""
    from services.knowledge_service import ingest, stats
    from services.file_parser import extract

    total_chunks = 0
    errors = []

    all_files = {**PDF_SOURCES, **XLSX_SOURCES}
    for filename, source in sorted(all_files.items()):
        filepath = KNOWLEDGE_RAW / filename
        if not filepath.exists():
            print(f"  SKIP  {filename} (nicht vorhanden)")
            continue

        print(f"  READ  {filename} → {source} ...", end="", flush=True)
        try:
            file_bytes = filepath.read_bytes()
            parsed = extract(file_bytes, filename)
            if not parsed["text"]:
                print(f" LEER ({parsed['warnings']})")
                errors.append(filename)
                continue

            result = ingest(parsed["text"], source=source, filename=filename)
            total_chunks += result["chunks_stored"]
            print(f" {result['chunks_stored']} Chunks ({parsed['method']}, {parsed['char_count']} Zeichen)")
        except Exception as e:
            print(f" FEHLER: {e}")
            errors.append(filename)

    st = stats()
    print(f"\n=== Knowledge-Base: {st['documents']} Dokumente, {st['chunks']} Chunks ===")
    if errors:
        print(f"Fehler bei: {', '.join(errors)}")


def ingest_dataframes():
    """Liest XLSX-Dateien als SQL-Tabellen ein."""
    from services.dataframe_service import ingest_dataframe, list_dataframe_tables

    # Transparenzliste und Begünstigtenanalyse
    xlsx_files = [
        # (Pfad, Source-Label, Sheet)
        # Zeitplan
        (KNOWLEDGE_RAW / "efre_zeitplan_aufforderungen.xlsx", "efre_zeitplan", 0),
    ]

    # Externe Begünstigtenverzeichnisse (falls vorhanden)
    ext_files = [
        "/app/data/transparenzliste_hessen.xlsx",
        "/app/data/beguenstigten_analyse.xlsx",
    ]
    for p in ext_files:
        if Path(p).exists():
            name = Path(p).stem
            xlsx_files.append((Path(p), name, 0))

    for filepath, source, sheet in xlsx_files:
        if not filepath.exists():
            print(f"  SKIP  {filepath} (nicht vorhanden)")
            continue

        print(f"  DF    {filepath.name} → {source} ...", end="", flush=True)
        try:
            result = ingest_dataframe(filepath.read_bytes(), filepath.name, source, sheet)
            print(f" {result['rows']} Zeilen, {len(result['columns'])} Spalten → {result['table_name']}")
        except Exception as e:
            print(f" FEHLER: {e}")

    tables = list_dataframe_tables()
    print(f"\n=== DataFrame-Tabellen: {len(tables)} ===")
    for t in tables:
        print(f"  {t['source']}: {t['rows']} Zeilen")


def main():
    parser = argparse.ArgumentParser(description="Alle Dokumente einlesen")
    parser.add_argument("--knowledge", action="store_true", help="PDFs → pgvector Knowledge-Base")
    parser.add_argument("--dataframes", action="store_true", help="XLSX → SQL DataFrames")
    parser.add_argument("--all", action="store_true", help="Beides")
    args = parser.parse_args()

    if not any([args.knowledge, args.dataframes, args.all]):
        args.all = True

    if args.knowledge or args.all:
        print("=== Knowledge-Base Ingest ===")
        ingest_knowledge()
        print()

    if args.dataframes or args.all:
        print("=== DataFrame Ingest ===")
        ingest_dataframes()


if __name__ == "__main__":
    main()
