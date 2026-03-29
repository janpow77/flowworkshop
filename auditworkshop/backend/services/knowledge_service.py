"""
flowworkshop · knowledge_service.py
RAG-Wissensdatenbank auf Basis von PostgreSQL + pgvector.

Tabelle knowledge_chunks:
  id            SERIAL PRIMARY KEY
  source        TEXT            — logischer Name (z. B. "VO_2021_1060")
  filename      TEXT            — Originaldateiname
  chunk_index   INT             — Reihenfolge innerhalb des Dokuments
  text          TEXT            — Chunk-Inhalt
  char_count    INT
  embedding     vector(768)     — paraphrase-multilingual-mpnet-base-v2
  ingested_at   TIMESTAMPTZ
  UNIQUE(source, chunk_index)
"""
from __future__ import annotations
import logging
import re
from typing import Generator

import psycopg2
from psycopg2.extras import execute_values
from sentence_transformers import SentenceTransformer

from config import DATABASE_URL, EMBEDDING_MODEL, EMBEDDING_DIM, CHUNK_WORDS, CHUNK_OVERLAP

log = logging.getLogger(__name__)

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        log.info("Lade Embedding-Modell %s …", EMBEDDING_MODEL)
        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


# ── Datenbankverbindung ────────────────────────────────────────────────────

def _connect():
    return psycopg2.connect(DATABASE_URL)


def init_db() -> None:
    """Legt Tabelle und Index an, falls noch nicht vorhanden."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS knowledge_chunks (
                id          SERIAL PRIMARY KEY,
                source      TEXT NOT NULL,
                filename    TEXT NOT NULL,
                chunk_index INT  NOT NULL,
                text        TEXT NOT NULL,
                char_count  INT  NOT NULL,
                embedding   vector({EMBEDDING_DIM}),
                ingested_at TIMESTAMPTZ DEFAULT now(),
                UNIQUE (source, chunk_index)
            );
        """)
        # IVFFlat-Index — erst sinnvoll ab ~1000 Zeilen, schadet aber nicht
        cur.execute("""
            CREATE INDEX IF NOT EXISTS knowledge_chunks_embedding_idx
            ON knowledge_chunks
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 50);
        """)
        conn.commit()
    log.info("Wissensdatenbank initialisiert.")


# ── Chunking ───────────────────────────────────────────────────────────────

def _word_chunks(text: str, size: int = CHUNK_WORDS, overlap: int = CHUNK_OVERLAP) -> Generator[str, None, None]:
    """Teilt Text in Wort-Chunks mit Überlappung auf."""
    words = re.split(r"\s+", text.strip())
    start = 0
    while start < len(words):
        end = min(start + size, len(words))
        yield " ".join(words[start:end])
        if end == len(words):
            break
        start += size - overlap


# ── Ingest ─────────────────────────────────────────────────────────────────

def ingest(text: str, source: str, filename: str) -> dict:
    """
    Speichert einen Dokumenttext als Chunks in pgvector.
    Idempotent: UPSERT auf (source, chunk_index).

    Returns:
        {"chunks_stored": int, "source": str}
    """
    model = _get_model()
    chunks = list(_word_chunks(text))
    if not chunks:
        return {"chunks_stored": 0, "source": source}

    embeddings = model.encode(chunks, show_progress_bar=False, normalize_embeddings=True)

    rows = [
        (source, filename, idx, chunk, len(chunk), emb.tolist())
        for idx, (chunk, emb) in enumerate(zip(chunks, embeddings))
    ]

    with _connect() as conn, conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO knowledge_chunks (source, filename, chunk_index, text, char_count, embedding)
            VALUES %s
            ON CONFLICT (source, chunk_index)
            DO UPDATE SET text = EXCLUDED.text,
                          char_count = EXCLUDED.char_count,
                          embedding = EXCLUDED.embedding,
                          ingested_at = now()
            """,
            rows,
            template="(%s, %s, %s, %s, %s, %s::vector)",
        )
        conn.commit()

    log.info("Ingest %s: %d Chunks gespeichert.", source, len(rows))
    return {"chunks_stored": len(rows), "source": source}


# ── Suche ──────────────────────────────────────────────────────────────────

def search(query: str, top_k: int = 5, source_filter: str | None = None) -> list[dict]:
    """
    Semantische Ähnlichkeitssuche (cosine distance).

    Args:
        query:         Suchanfrage als natürlichsprachiger Text.
        top_k:         Anzahl der Treffer.
        source_filter: Optional — nur Chunks dieser Quelle durchsuchen.

    Returns:
        [{"text": str, "source": str, "filename": str,
          "chunk_index": int, "score": float}, ...]
    """
    article_match = re.search(r'[Aa]rt(?:ikel)?\.?\s*(\d+)', query)
    if article_match:
        article_num = article_match.group(1)
        keyword_results = _keyword_search(f"Artikel {article_num}", source_filter, top_k=top_k)
        if keyword_results:
            return keyword_results[:top_k]

    try:
        model = _get_model()
        vec = model.encode([query], normalize_embeddings=True)[0].tolist()
    except Exception:
        log.exception("Vektorsuche fehlgeschlagen, nutze Keyword-Fallback fuer Query: %s", query)
        return _keyword_search(query, source_filter, top_k=top_k)

    filter_clause = "WHERE source = %s" if source_filter else ""
    params: list = [str(vec)]
    if source_filter:
        params.append(source_filter)
    params.append(top_k)

    sql = f"""
        SELECT text, source, filename, chunk_index,
               1 - (embedding <=> %s::vector) AS score
        FROM knowledge_chunks
        {filter_clause}
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    params.insert(1 if not source_filter else 2, str(vec))

    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    results = [
        {"text": r[0], "source": r[1], "filename": r[2],
         "chunk_index": r[3], "score": round(float(r[4]), 4)}
        for r in rows
    ]

    if article_match:
        keyword_results = _keyword_search(f"Artikel {article_match.group(1)}", source_filter, top_k=2)
        # Merge: Keyword-Treffer vorne, dann Vektor-Treffer (ohne Duplikate)
        seen: set[tuple[str, int]] = set()
        merged: list[dict] = []
        for r in keyword_results + results:
            key = (r['source'], r['chunk_index'])
            if key not in seen:
                seen.add(key)
                merged.append(r)
        return merged[:top_k]

    return results


# ── Keyword-Suche (Ergaenzung zur Vektorsuche) ────────────────────────────

def _keyword_search(keyword: str, source_filter: str | None = None, top_k: int = 2) -> list[dict]:
    """Volltextsuche als Ergaenzung zur Vektorsuche — findet exakte Artikelverweise."""
    filter_clause = "AND source = %s" if source_filter else ""
    params: list = [f"%{keyword}%"]
    if source_filter:
        params.append(source_filter)
    params.append(top_k)

    sql = f"""
        SELECT text, source, filename, chunk_index, 0.8 AS score
        FROM knowledge_chunks
        WHERE text ILIKE %s {filter_clause}
        ORDER BY chunk_index
        LIMIT %s
    """

    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    return [
        {"text": r[0], "source": r[1], "filename": r[2],
         "chunk_index": r[3], "score": round(float(r[4]), 4)}
        for r in rows
    ]


# ── Statistiken ────────────────────────────────────────────────────────────

def stats() -> dict:
    """
    Returns:
        {"documents": int, "chunks": int,
         "sources": [{"source": str, "filename": str, "chunks": int}]}
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT source, filename, COUNT(*) AS chunks
            FROM knowledge_chunks
            GROUP BY source, filename
            ORDER BY source
        """)
        rows = cur.fetchall()

    sources = [{"source": r[0], "filename": r[1], "chunks": r[2]} for r in rows]
    return {
        "documents": len(sources),
        "chunks": sum(s["chunks"] for s in sources),
        "sources": sources,
    }


# ── Chunks einer Quelle abrufen ────────────────────────────────────────────

def get_chunks(source: str, offset: int = 0, limit: int = 20) -> dict:
    """
    Gibt Chunks einer Quelle paginiert zurueck.

    Returns:
        {"source": str, "total": int, "offset": int, "limit": int,
         "chunks": [{"chunk_index": int, "text": str, "char_count": int}]}
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM knowledge_chunks WHERE source = %s",
            (source,),
        )
        total = cur.fetchone()[0]

        cur.execute(
            """
            SELECT chunk_index, text, char_count
            FROM knowledge_chunks
            WHERE source = %s
            ORDER BY chunk_index
            OFFSET %s LIMIT %s
            """,
            (source, offset, limit),
        )
        rows = cur.fetchall()

    return {
        "source": source,
        "total": total,
        "offset": offset,
        "limit": limit,
        "chunks": [
            {"chunk_index": r[0], "text": r[1], "char_count": r[2]}
            for r in rows
        ],
    }


# ── Quelle löschen ─────────────────────────────────────────────────────────

def delete_source(source: str) -> int:
    """Löscht alle Chunks einer Quelle. Gibt Anzahl gelöschter Zeilen zurück."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM knowledge_chunks WHERE source = %s", (source,))
        deleted = cur.rowcount
        conn.commit()
    log.info("Quelle %s gelöscht: %d Chunks entfernt.", source, deleted)
    return deleted
