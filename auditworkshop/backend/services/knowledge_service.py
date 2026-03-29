"""
flowworkshop · knowledge_service.py
RAG-Wissensdatenbank auf Basis von PostgreSQL + pgvector.

Die Embeddings kommen bevorzugt aus dem egpu-manager Gateway (`bge-m3`),
damit der Backend-Container keinen lokalen SentenceTransformer laden muss.
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Generator

import httpx
import psycopg2
from psycopg2.extras import execute_values

from config import (
    CHUNK_OVERLAP,
    CHUNK_WORDS,
    DATABASE_URL,
    EMBEDDING_BACKEND,
    EMBEDDING_DIM,
    EMBEDDING_GATEWAY_APP_ID,
    EMBEDDING_GATEWAY_URL,
    EMBEDDING_MODEL,
)

log = logging.getLogger(__name__)

_local_model = None
_REGULATION_SOURCE_HINTS = {
    "2021/1060": "VO_2021_1060_DE",
    "2021/1058": "VO_2021_1058_DE",
}


def _connect():
    return psycopg2.connect(DATABASE_URL)


def _get_local_model():
    global _local_model
    if _local_model is None:
        log.info("Lade lokales Embedding-Modell %s …", EMBEDDING_MODEL)
        from sentence_transformers import SentenceTransformer

        _local_model = SentenceTransformer(EMBEDDING_MODEL)
    return _local_model


def _gateway_embed(texts: list[str]) -> list[list[float]]:
    with httpx.Client(timeout=httpx.Timeout(30, read=300)) as client:
        resp = client.post(
            f"{EMBEDDING_GATEWAY_URL}/api/llm/embeddings",
            json={"model": EMBEDDING_MODEL, "input": texts},
            headers={"X-App-Id": EMBEDDING_GATEWAY_APP_ID},
        )
        resp.raise_for_status()
        data = resp.json()

    if isinstance(data.get("data"), list):
        vectors = [item.get("embedding") for item in data["data"]]
    else:
        vectors = data.get("embeddings") or []

    if len(vectors) != len(texts):
        raise RuntimeError(
            f"Gateway lieferte {len(vectors)} Embeddings fuer {len(texts)} Texte."
        )
    return vectors


def _embed_texts(texts: list[str], batch_size: int = 8) -> list[list[float]]:
    if not texts:
        return []

    if EMBEDDING_BACKEND == "gateway":
        vectors: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start:start + batch_size]
            try:
                vectors.extend(_gateway_embed(batch))
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 502 or len(batch) == 1:
                    raise
                log.warning(
                    "Gateway-Embeddings Batch %d fehlgeschlagen, falle auf Einzelrequests zurueck.",
                    len(batch),
                )
                for item in batch:
                    vectors.extend(_gateway_embed([item]))
        return vectors

    model = _get_local_model()
    return model.encode(
        texts,
        show_progress_bar=False,
        normalize_embeddings=True,
    ).tolist()


def _embedding_column_type(cur) -> str | None:
    cur.execute(
        """
        SELECT format_type(a.atttypid, a.atttypmod)
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = 'knowledge_chunks'
          AND n.nspname = 'public'
          AND a.attname = 'embedding'
          AND a.attnum > 0
          AND NOT a.attisdropped
        """
    )
    row = cur.fetchone()
    return row[0] if row else None


def init_db() -> None:
    """Legt Tabelle und Index an und migriert bei Embedding-Dimensionswechsel."""
    expected_type = f"vector({EMBEDDING_DIM})"

    with _connect() as conn, conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge_chunks (
                id          SERIAL PRIMARY KEY,
                source      TEXT NOT NULL,
                filename    TEXT NOT NULL,
                chunk_index INT  NOT NULL,
                text        TEXT NOT NULL,
                char_count  INT  NOT NULL,
                embedding   vector(1),
                ingested_at TIMESTAMPTZ DEFAULT now(),
                UNIQUE (source, chunk_index)
            );
            """
        )

        current_type = _embedding_column_type(cur)
        if current_type != expected_type:
            log.warning(
                "Migriere knowledge_chunks.embedding von %s auf %s und markiere Embeddings fuer Rebuild.",
                current_type,
                expected_type,
            )
            cur.execute("DROP INDEX IF EXISTS knowledge_chunks_embedding_idx;")
            cur.execute(
                f"""
                ALTER TABLE knowledge_chunks
                ALTER COLUMN embedding TYPE {expected_type}
                USING NULL
                """
            )

        cur.execute(
            f"""
            CREATE INDEX IF NOT EXISTS knowledge_chunks_embedding_idx
            ON knowledge_chunks
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 50);
            """
        )
        conn.commit()

    log.info(
        "Wissensdatenbank initialisiert (%s, %s, %sd).",
        EMBEDDING_BACKEND,
        EMBEDDING_MODEL,
        EMBEDDING_DIM,
    )


def _word_chunks(
    text: str,
    size: int = CHUNK_WORDS,
    overlap: int = CHUNK_OVERLAP,
) -> Generator[str, None, None]:
    words = re.split(r"\s+", text.strip())
    start = 0
    while start < len(words):
        end = min(start + size, len(words))
        yield " ".join(words[start:end])
        if end == len(words):
            break
        start += size - overlap


def ingest(text: str, source: str, filename: str) -> dict:
    """Speichert einen Dokumenttext als Chunks in pgvector."""
    chunks = list(_word_chunks(text))
    if not chunks:
        return {"chunks_stored": 0, "source": source}

    embeddings = _embed_texts(chunks)
    rows = [
        (source, filename, idx, chunk, len(chunk), emb)
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


def reembed_all() -> dict:
    """Berechnet fehlende Embeddings fuer vorhandene Chunks neu."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT source, filename, chunk_index, text, char_count
            FROM knowledge_chunks
            WHERE embedding IS NULL
            ORDER BY source, chunk_index
            """
        )
        rows = cur.fetchall()

    grouped: dict[str, list[tuple[str, int, str, int]]] = defaultdict(list)
    for source, filename, chunk_index, text, char_count in rows:
        grouped[source].append((filename, chunk_index, text, char_count))

    total = 0
    for source, items in grouped.items():
        texts = [item[2] for item in items]
        embeddings = _embed_texts(texts)
        upsert_rows = [
            (source, filename, chunk_index, text, char_count, emb)
            for (filename, chunk_index, text, char_count), emb in zip(items, embeddings)
        ]
        with _connect() as conn, conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO knowledge_chunks (source, filename, chunk_index, text, char_count, embedding)
                VALUES %s
                ON CONFLICT (source, chunk_index)
                DO UPDATE SET embedding = EXCLUDED.embedding,
                              ingested_at = now()
                """,
                upsert_rows,
                template="(%s, %s, %s, %s, %s, %s::vector)",
            )
            conn.commit()
        total += len(items)
        log.info("Re-Embed %s: %d Chunks aktualisiert.", source, len(items))

    return {"reembedded_chunks": total, "sources": len(grouped)}


def search(query: str, top_k: int = 5, source_filter: str | None = None) -> list[dict]:
    """Semantische Ähnlichkeitssuche (cosine distance) mit Keyword-Fallback."""
    article_match = re.search(r"[Aa]rt(?:ikel)?\.?\s*(\d+)", query)
    hinted_source = source_filter or _detect_regulation_source(query)
    if article_match:
        article_num = article_match.group(1)
        keyword_results = _article_search(query, article_num, hinted_source, top_k=top_k)
        if keyword_results:
            return keyword_results[:top_k]
        keyword_results = _keyword_search(f"Artikel {article_num}", hinted_source, top_k=top_k)
        if keyword_results:
            return keyword_results[:top_k]

    try:
        vec = _embed_texts([query])[0]
    except Exception:
        log.exception("Vektorsuche fehlgeschlagen, nutze Keyword-Fallback fuer Query: %s", query)
        return _keyword_search(query, hinted_source, top_k=top_k)

    filter_clause = "WHERE source = %s AND embedding IS NOT NULL" if hinted_source else "WHERE embedding IS NOT NULL"
    params: list = [str(vec)]
    if hinted_source:
        params.append(hinted_source)
    params.append(str(vec))
    params.append(top_k)

    sql = f"""
        SELECT text, source, filename, chunk_index,
               1 - (embedding <=> %s::vector) AS score
        FROM knowledge_chunks
        {filter_clause}
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """

    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    results = [
        {
            "text": row[0],
            "source": row[1],
            "filename": row[2],
            "chunk_index": row[3],
            "score": round(float(row[4]), 4),
        }
        for row in rows
    ]

    if article_match:
        keyword_results = _article_search(query, article_match.group(1), hinted_source, top_k=2)
        if not keyword_results:
            keyword_results = _keyword_search(f"Artikel {article_match.group(1)}", hinted_source, top_k=2)
        seen: set[tuple[str, int]] = set()
        merged: list[dict] = []
        for result in keyword_results + results:
            key = (result["source"], result["chunk_index"])
            if key not in seen:
                seen.add(key)
                merged.append(result)
        return merged[:top_k]

    return results


def _detect_regulation_source(query: str) -> str | None:
    normalized_query = query.replace(" ", "")
    for regulation, source in _REGULATION_SOURCE_HINTS.items():
        if regulation.replace(" ", "") in normalized_query:
            return source
    return None


def _article_search(
    query: str,
    article_num: str,
    source_filter: str | None = None,
    top_k: int = 2,
) -> list[dict]:
    article_phrase = f"Artikel {article_num}"
    filter_clause = "AND source = %s" if source_filter else ""
    params: list = [f"%{article_phrase}%"]
    if source_filter:
        params.append(source_filter)
    params.append(max(top_k * 8, 12))

    sql = f"""
        SELECT text, source, filename, chunk_index
        FROM knowledge_chunks
        WHERE text ILIKE %s
          {filter_clause}
        ORDER BY chunk_index
        LIMIT %s
    """

    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    query_keywords = [
        token
        for token in re.findall(r"[a-zäöüß]{5,}", query.lower())
        if token not in {"artikel", "vo", "verwaltung", "durch", "fuer", "fonds"}
    ]

    scored_results: list[dict] = []
    for row in rows:
        text_value = row[0]
        lower_text = text_value.lower()
        article_mentions = len(re.findall(r"artikel\s+\d+", lower_text))
        hit_pos = lower_text.find(article_phrase.lower())
        keyword_hits = sum(
            1
            for token in query_keywords
            if token in lower_text or token[:8] in lower_text
        )

        score = 1.0
        if "inhaltsverzeichnis" in lower_text:
            score -= 0.35
        if hit_pos >= 0:
            score -= min(hit_pos, 1200) / 10000
        if article_mentions > 4:
            score -= min(article_mentions - 4, 8) * 0.04
        if keyword_hits:
            score += min(keyword_hits, 3) * 0.05
        if article_phrase.lower() in lower_text[:220]:
            score += 0.08

        scored_results.append(
            {
                "text": text_value,
                "source": row[1],
                "filename": row[2],
                "chunk_index": row[3],
                "score": round(score, 4),
            }
        )

    scored_results.sort(
        key=lambda item: (
            -float(item["score"]),
            item["chunk_index"],
        )
    )
    return scored_results[:top_k]


def _keyword_search(keyword: str, source_filter: str | None = None, top_k: int = 2) -> list[dict]:
    filter_clause = "AND source = %s" if source_filter else ""
    params: list = [f"%{keyword}%"]
    if source_filter:
        params.append(source_filter)
    params.append(top_k)

    sql = f"""
        SELECT text, source, filename, chunk_index, 0.8 AS score
        FROM knowledge_chunks
        WHERE text ILIKE %s {filter_clause}
        ORDER BY
            CASE WHEN text ILIKE '%%inhaltsverzeichnis%%' THEN 1 ELSE 0 END,
            chunk_index
        LIMIT %s
    """

    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    return [
        {
            "text": row[0],
            "source": row[1],
            "filename": row[2],
            "chunk_index": row[3],
            "score": round(float(row[4]), 4),
        }
        for row in rows
    ]


def stats() -> dict:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT source, filename, COUNT(*) AS chunks
            FROM knowledge_chunks
            GROUP BY source, filename
            ORDER BY source
            """
        )
        rows = cur.fetchall()

    sources = [{"source": row[0], "filename": row[1], "chunks": row[2]} for row in rows]
    return {
        "documents": len(sources),
        "chunks": sum(item["chunks"] for item in sources),
        "sources": sources,
    }


def get_chunks(source: str, offset: int = 0, limit: int = 20) -> dict:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM knowledge_chunks WHERE source = %s", (source,))
        total = cur.fetchone()[0]
        cur.execute(
            """
            SELECT chunk_index, text, char_count
            FROM knowledge_chunks
            WHERE source = %s
            ORDER BY chunk_index
            OFFSET %s
            LIMIT %s
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
            {"chunk_index": row[0], "text": row[1], "char_count": row[2]}
            for row in rows
        ],
    }


def delete_source(source: str) -> int:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM knowledge_chunks WHERE source = %s", (source,))
        deleted = cur.rowcount
        conn.commit()
    return deleted
