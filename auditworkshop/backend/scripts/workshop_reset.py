#!/usr/bin/env python3
"""
auditworkshop · scripts/workshop_reset.py
Setzt das System fuer den Workshop-Start zurueck.

Ablauf:
  1. Alle Begünstigtenverzeichnisse loeschen
  2. Alle Projekte/Checklisten loeschen
  3. Knowledge Base: Nur EU-Verordnungen behalten (landesspezifische Docs entfernen)
  4. EU-Verordnungen von EUR-Lex laden (falls nicht vorhanden)
  5. Registrierungen und Themen zuruecksetzen

Danach ist das System bereit fuer den Live-Workshop:
  - Moderator laedt OP-Dokumente des Ziel-Bundeslandes hoch (Wissensbasis)
  - Moderator laedt Beguenstigtenverzeichnis hoch (Szenario 6)
  - Moderator legt Demo-Projekt + Checkliste live an (Szenario 2)

Aufruf:
  docker exec auditworkshop-backend python scripts/workshop_reset.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.knowledge_service import init_db, ingest, stats, delete_source
from services.pdf_parser import extract
from database import engine, Base, SessionLocal
from models.project import WorkshopProject
from models.registration import Registration, TopicSubmission, AgendaItem, WorkshopMeta
from sqlalchemy import text
import requests

RAW_DIR = Path(__file__).parent.parent / "data" / "knowledge_raw"

# EU-Verordnungen (bundesland-neutral, oeffentlich zugaenglich)
EU_SOURCES = [
    {
        "source": "VO_2021_1060_DE",
        "filename": "vo_2021_1060_de.pdf",
        "url": "https://eur-lex.europa.eu/legal-content/DE/TXT/PDF/?uri=CELEX:32021R1060",
        "label": "Dachverordnung VO (EU) 2021/1060",
    },
    {
        "source": "VO_2021_1058_DE",
        "filename": "vo_2021_1058_de.pdf",
        "url": "https://eur-lex.europa.eu/legal-content/DE/TXT/PDF/?uri=CELEX:32021R1058",
        "label": "EFRE-Verordnung VO (EU) 2021/1058",
    },
    {
        "source": "EU_AI_ACT_DE",
        "filename": "eu_ai_act_2024_1689_de.pdf",
        "url": "https://eur-lex.europa.eu/legal-content/DE/TXT/PDF/?uri=CELEX:32024R1689",
        "label": "EU AI Act VO (EU) 2024/1689",
    },
]


def download(url: str, dest: Path) -> bytes:
    if dest.exists():
        return dest.read_bytes()
    print(f"    Lade herunter: {url[:80]}...")
    r = requests.get(url, timeout=60, headers={"User-Agent": "auditworkshop/1.0"})
    r.raise_for_status()
    dest.write_bytes(r.content)
    return r.content


def main():
    print("\n╔══════════════════════════════════════════════╗")
    print("║     AUDITWORKSHOP — Workshop-Reset           ║")
    print("╚══════════════════════════════════════════════╝\n")

    init_db()
    db = SessionLocal()

    # 1. Projekte + Checklisten loeschen
    print("[1/5] Projekte und Checklisten loeschen...")
    count = db.query(WorkshopProject).count()
    db.query(WorkshopProject).delete()
    db.commit()
    print(f"      {count} Projekte geloescht.")

    # 2. Beguenstigtenverzeichnisse loeschen
    print("[2/5] Beguenstigtenverzeichnisse loeschen...")
    tables = []
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name LIKE 'workshop_df_%'
            """))
            tables = [r[0] for r in result]
            for t in tables:
                conn.execute(text(f'DROP TABLE IF EXISTS "{t}"'))
            try:
                conn.execute(text("DELETE FROM workshop_df_metadata WHERE TRUE"))
            except Exception:
                pass
            conn.commit()
    except Exception as e:
        print(f"      Warnung: {e}")
    print(f"      {len(tables)} DataFrame-Tabellen geloescht.")

    # 3. Knowledge Base: alles loeschen
    print("[3/5] Knowledge Base bereinigen...")
    st = stats()
    for src in st["sources"]:
        delete_source(src["source"])
    print(f"      {st['documents']} Quellen geloescht.")

    # 4. EU-Verordnungen einlesen
    print("[4/5] EU-Verordnungen einlesen...")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for s in EU_SOURCES:
        print(f"    {s['label']}...")
        try:
            content = download(s["url"], RAW_DIR / s["filename"])
            parsed = extract(content, s["filename"])
            if parsed["text"]:
                result = ingest(parsed["text"], source=s["source"], filename=s["filename"])
                print(f"      {result['chunks_stored']} Chunks ({parsed['char_count']} Zeichen)")
            else:
                print(f"      LEER: {parsed['warnings']}")
        except Exception as e:
            print(f"      FEHLER: {e}")

    # 5. Registrierungen + Themen zuruecksetzen (optional)
    print("[5/5] Registrierungen und Themen zuruecksetzen...")
    reg_count = db.query(Registration).count()
    topic_count = db.query(TopicSubmission).count()
    db.query(TopicSubmission).delete()
    db.query(Registration).delete()
    db.commit()
    print(f"      {reg_count} Registrierungen, {topic_count} Themen geloescht.")

    # Ergebnis
    st = stats()
    print(f"\n{'═' * 48}")
    print(f"Workshop-System bereit!")
    print(f"  Knowledge Base: {st['documents']} Dokumente, {st['chunks']} Chunks")
    print(f"  (nur EU-Verordnungen — OP-Dokumente werden live hochgeladen)")
    print(f"  Beguenstigte: 0 (werden live hochgeladen)")
    print(f"  Projekte: 0 (werden live angelegt)")
    print(f"\nWorkshop-Ablauf:")
    print(f"  1. OP-Dokumente des Ziel-Bundeslandes hochladen (Wissensbasis)")
    print(f"  2. Beguenstigtenverzeichnis hochladen (Szenario 6)")
    print(f"  3. Demo-Projekt + Checkliste live anlegen (Szenario 2)")
    print(f"{'═' * 48}")

    db.close()


if __name__ == "__main__":
    main()
