"""Repariert zeichenweise rueckwaerts gespeicherte Knowledge-Chunks.

Einige Seiten von VO_2021_1060_DE wurden beim PDF-Parsing komplett
zeichen-reversiert extrahiert ("serhi gnufürP" statt "Prüfung ihres ...").
Die Embeddings dieser Chunks wurden auf dem rueckwaertigen Text berechnet,
daher liefert die semantische Suche dort Muell.

Erkennung: ein deutscher Stoppwort-Score. Enthaelt die *Umkehrung* eines
Chunks deutlich mehr Stoppwoerter als der gespeicherte Text, ist er reversiert.
Reparatur: Text zeichenweise zurueckdrehen und neu einbetten.

Aufruf im Backend-Container:
    python scripts/repair_reversed_chunks.py            # Dry-Run (nur Analyse)
    python scripts/repair_reversed_chunks.py --apply     # Reparatur ausfuehren
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.knowledge_service import _connect, _embed_texts  # noqa: E402

STOP = [
    " der ", " die ", " und ", " von ", " für ", " fuer ", " den ", " des ",
    " mit ", " auf ", " nach ", " eine ", " einen ", " im ", " zur ", " zum ",
    " das ", " ist ", " werden ", " bei ", " oder ", " sind ", " dem ", " als ",
]


def score(s: str) -> int:
    s2 = " " + s.lower() + " "
    return sum(s2.count(w) for w in STOP)


def is_reversed(text: str) -> bool:
    # Marge +1 schuetzt vor Rauschen bei stoppwortarmen (z. B. tabellarischen) Chunks.
    return score(text[::-1]) > score(text) + 1


def main(apply: bool) -> None:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, source, text FROM knowledge_chunks ORDER BY id;")
        rows = cur.fetchall()

    to_fix = [(cid, src, txt) for (cid, src, txt) in rows if is_reversed(txt)]
    print(f"Geprueft: {len(rows)} Chunks. Rueckwaerts erkannt: {len(to_fix)}")

    by_src: dict[str, int] = {}
    for _, src, _ in to_fix:
        by_src[src] = by_src.get(src, 0) + 1
    for src, n in sorted(by_src.items(), key=lambda x: -x[1]):
        print(f"  {src}: {n}")

    if to_fix:
        _, _, txt = to_fix[0]
        print("\n--- Beispiel VORHER ---\n" + txt[:180])
        print("\n--- NACHHER ---\n" + txt[::-1][:180])

    if not apply:
        print("\nDry-Run. Mit --apply ausfuehren.")
        return

    print(f"\nRepariere {len(to_fix)} Chunks (inkl. Re-Embedding) …")
    fixed = 0
    batch_size = 16
    for i in range(0, len(to_fix), batch_size):
        batch = to_fix[i:i + batch_size]
        new_texts = [t[::-1] for (_, _, t) in batch]
        embs = _embed_texts(new_texts)
        with _connect() as conn, conn.cursor() as cur:
            for (cid, _, _), new_text, emb in zip(batch, new_texts, embs):
                cur.execute(
                    "UPDATE knowledge_chunks "
                    "SET text=%s, char_count=%s, embedding=%s::vector, ingested_at=now() "
                    "WHERE id=%s",
                    (new_text, len(new_text), emb, cid),
                )
            conn.commit()
        fixed += len(batch)
        print(f"  … {fixed}/{len(to_fix)}")
    print(f"Fertig. {fixed} Chunks repariert und neu eingebettet.")


if __name__ == "__main__":
    main("--apply" in sys.argv)
