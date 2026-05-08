"""
flowworkshop · services/entity_embeddings.py

Layer A — Embedding-Layer ueber alle drei Module via bge-m3-Gateway.

Plan: semantische Such-Schicht ZUSAETZLICH zu Fuzzy + LEI-Match. Findet
Records, die dieselbe Bedeutung tragen, auch wenn der Wortlaut nicht
deckungsgleich ist (z.B. "Klimaschutz-Projekte in Bayern" findet auch
Records ohne diese Keywords).

Architektur (additiv):
- Original-Records bleiben unveraendert.
- Pro Original-Record gibt es einen Eintrag in ``workshop_entity_embeddings``
  mit pgvector-Vector(1024) und dem Embedding-Text als ``text_input``
  (Audit/Debugging).
- Embeddings kommen aus dem egpu-manager Gateway (bge-m3).
- IVFFlat-Cosine-Index (lists=100) wird im Lifespan angelegt.

Performance-Anker:
- Initial-Build aller 180k Records: ~30 min auf der GPU.
- Pro Suche: <100 ms Cosine-Lookup mit IVFFlat.
- Speicher-Footprint: ~700 MB fuer 180k * 1024 floats (4 bytes) +
  IVFFlat-Overhead.

Modell-Wahl bge-m3:
- 1024 Dim, multilingual, gut fuer DE/EN-Mix.
- Wiederverwendet das Gateway, das schon fuer ``knowledge_service`` laeuft —
  kein lokales Modell im Backend-Container.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import (
    EMBEDDING_BACKEND,
    EMBEDDING_DIM,
    EMBEDDING_GATEWAY_APP_ID,
    EMBEDDING_GATEWAY_URL,
    EMBEDDING_MODEL,
)
from models.entity_embeddings import EntityEmbedding

log = logging.getLogger(__name__)


VALID_MODULES = {"state_aid", "beneficiary", "sanctions", "company_entity"}


# ── Embedding-Text-Builder ────────────────────────────────────────────────────


def build_embedding_text(*, module: str, record: Any) -> str:
    """Generiert den Text fuer das Embedding pro Modul.

    Kanonische Schemata:
      state_aid:      "{beneficiary_name} | {aid_objective} | {granting_authority}"
      beneficiary:    "{beneficiary_name} | {project_name} | {project_description}"
      sanctions:      "{name} | {aliases joined} | {sanctions_program}"
      company_entity: "{canonical_name} | {addresses[0].city if any}"

    ``record`` darf ein ORM-Modell-Objekt oder ein Dict sein. Leere
    Komponenten werden uebersprungen — die Funktion liefert nie ein leeres
    Resultat fuer einen Record mit gueltigem Namen, weil mindestens der
    Name oder canonical_name immer da ist.
    """
    def _get(key: str) -> str:
        if isinstance(record, dict):
            value = record.get(key)
        else:
            value = getattr(record, key, None)
        if value is None:
            return ""
        return str(value).strip()

    parts: list[str] = []

    if module == "state_aid":
        parts.append(_get("beneficiary_name"))
        parts.append(_get("aid_objective"))
        parts.append(_get("granting_authority"))
    elif module == "beneficiary":
        parts.append(_get("beneficiary_name"))
        parts.append(_get("project_name"))
        parts.append(_get("project_description"))
    elif module == "sanctions":
        parts.append(_get("name"))
        # Aliases: JSONB-Liste
        aliases = (
            record.get("aliases") if isinstance(record, dict)
            else getattr(record, "aliases", None)
        )
        if aliases:
            if isinstance(aliases, str):
                parts.append(aliases.strip())
            elif isinstance(aliases, (list, tuple)):
                joined = " ".join(str(a).strip() for a in aliases if a)
                if joined:
                    parts.append(joined)
        parts.append(_get("sanctions_program"))
    elif module == "company_entity":
        parts.append(_get("canonical_name"))
        # Erste Stadt aus addresses-JSONB
        addresses = (
            record.get("addresses") if isinstance(record, dict)
            else getattr(record, "addresses", None)
        )
        if isinstance(addresses, list) and addresses:
            first = addresses[0]
            if isinstance(first, dict):
                city = (first.get("city") or "").strip()
                if city:
                    parts.append(city)
    else:
        raise ValueError(f"Unbekanntes module: {module}")

    cleaned = [p for p in (s.strip() for s in parts) if p]
    return " | ".join(cleaned)


# ── Gateway-Embedding-Aufruf ──────────────────────────────────────────────────


def _gateway_embed(texts: list[str]) -> list[list[float]]:
    """Embedding via Gateway. Wiederverwendet das Setup aus knowledge_service.

    Erwartet bge-m3 (1024 Dim). Bei Status-Code 502 in einem Batch wird auf
    Einzelrequests heruntergebrochen.
    """
    if not texts:
        return []
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
            f"Gateway lieferte {len(vectors)} Embeddings fuer {len(texts)} Texte.",
        )
    return vectors


def get_embedding(text_value: str) -> list[float] | None:
    """Liefert ein einzelnes Embedding via Gateway. Wirft NICHT — bei Fehler
    wird ``None`` zurueckgegeben, damit Caller graceful weiterlaufen koennen.
    """
    if not text_value or not text_value.strip():
        return None
    if EMBEDDING_BACKEND != "gateway":
        log.debug(
            "EMBEDDING_BACKEND=%s — entity_embeddings nutzt nur Gateway.",
            EMBEDDING_BACKEND,
        )
    try:
        vectors = _gateway_embed([text_value])
        if vectors and len(vectors) == 1:
            return vectors[0]
        return None
    except Exception:  # noqa: BLE001
        log.exception("Gateway-Embedding fehlgeschlagen.")
        return None


def _batch_embed(texts: list[str], batch_size: int = 8) -> list[list[float]]:
    """Embeddet eine Liste in Batches. Wirft bei Gateway-Fehlern hoch — der
    Caller (rebuild) entscheidet, ob er die Batch ueberspringt oder abbricht.
    """
    if not texts:
        return []
    out: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        chunk = texts[start:start + batch_size]
        try:
            out.extend(_gateway_embed(chunk))
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 502 or len(chunk) == 1:
                raise
            log.warning(
                "Gateway-Embeddings Batch %d fehlgeschlagen, falle auf "
                "Einzelrequests zurueck.",
                len(chunk),
            )
            for item in chunk:
                out.extend(_gateway_embed([item]))
    return out


# ── Upsert ────────────────────────────────────────────────────────────────────


def upsert_embedding(
    db: Session,
    *,
    module: str,
    record_id: str,
    text_input: str,
    embedding: list[float] | None = None,
) -> EntityEmbedding | None:
    """Schreibt oder aktualisiert ein Embedding.

    ON CONFLICT (source_module, source_record_id) DO UPDATE SET
    embedding/text_input/model_name/updated_at — Idempotent. Wenn
    ``embedding`` None ist, wird es per Gateway frisch geholt; bei Gateway-
    Ausfall liefert die Funktion ``None`` (kein DB-Schreibvorgang).
    """
    if module not in VALID_MODULES:
        raise ValueError(f"Unbekanntes module: {module}")
    if not record_id:
        raise ValueError("record_id darf nicht leer sein")
    if not text_input or not text_input.strip():
        return None

    if embedding is None:
        embedding = get_embedding(text_input)
        if embedding is None:
            return None
    if len(embedding) != EMBEDDING_DIM:
        raise ValueError(
            f"Embedding-Dim {len(embedding)} != erwartet {EMBEDDING_DIM}",
        )

    # ON CONFLICT: PostgreSQL spezifisch. Wir nutzen rohes SQL, weil die
    # SQLAlchemy-pgvector-Integration mit `Vector(1024)` bei der Insert-
    # Statement-Konstruktion sauber mit dem Param-Format spielt.
    sql = text("""
        INSERT INTO workshop_entity_embeddings
        (source_module, source_record_id, text_input, embedding, model_name,
         created_at, updated_at)
        VALUES (:module, :rec, :txt, (:emb)::vector, :model, NOW(), NOW())
        ON CONFLICT (source_module, source_record_id)
        DO UPDATE SET
            text_input = EXCLUDED.text_input,
            embedding = EXCLUDED.embedding,
            model_name = EXCLUDED.model_name,
            updated_at = NOW()
        RETURNING id
    """)
    row = db.execute(
        sql,
        {
            "module": module,
            "rec": str(record_id)[:64],
            "txt": text_input,
            "emb": str(embedding),
            "model": EMBEDDING_MODEL[:80],
        },
    ).first()
    if row is None:
        return None
    db.flush()
    # Lade die ORM-Instanz fuer den Rueckgabewert (Audit/Tests).
    return db.get(EntityEmbedding, int(row[0]))


# ── Rebuild ───────────────────────────────────────────────────────────────────


def _empty_rebuild_stats() -> dict:
    return {
        "processed": 0,
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "failed": 0,
    }


_PAGE_SIZE = 500


def _module_query_spec(module: str):
    """Liefert (id_col, query_columns, record_builder) je Modul.

    ``id_col`` ist die SQLAlchemy-Spalte fuer die Pagination — bei State-Aid
    eine UUID-String-Spalte, bei den anderen ein BigInteger. Beide sortieren
    sich konsistent ueber ``ORDER BY id ASC``, daher Keyset-Pagination
    funktioniert in beiden Faellen.

    ``record_builder`` ist eine Funktion ``row -> dict``, die das normalisierte
    Record-Dict fuer ``build_embedding_text`` zusammensetzt.
    """
    if module == "state_aid":
        from models.state_aid import StateAidAward
        cols = (
            StateAidAward.id,
            StateAidAward.beneficiary_name,
            StateAidAward.aid_objective,
            StateAidAward.granting_authority,
        )
        def _builder(row):
            return {
                "beneficiary_name": row.beneficiary_name,
                "aid_objective": row.aid_objective,
                "granting_authority": row.granting_authority,
            }
        return StateAidAward.id, cols, _builder

    if module == "beneficiary":
        from models.beneficiary_records import BeneficiaryRecord
        cols = (
            BeneficiaryRecord.id,
            BeneficiaryRecord.beneficiary_name,
            BeneficiaryRecord.project_name,
            BeneficiaryRecord.project_description,
        )
        def _builder(row):
            return {
                "beneficiary_name": row.beneficiary_name,
                "project_name": row.project_name,
                "project_description": row.project_description,
            }
        return BeneficiaryRecord.id, cols, _builder

    if module == "sanctions":
        from models.sanctions_entries import SanctionsEntry
        cols = (
            SanctionsEntry.id,
            SanctionsEntry.name,
            SanctionsEntry.aliases,
            SanctionsEntry.sanctions_program,
        )
        def _builder(row):
            return {
                "name": row.name,
                "aliases": row.aliases,
                "sanctions_program": row.sanctions_program,
            }
        return SanctionsEntry.id, cols, _builder

    if module == "company_entity":
        from models.entities import CompanyEntity
        cols = (
            CompanyEntity.id,
            CompanyEntity.canonical_name,
            CompanyEntity.addresses,
        )
        def _builder(row):
            return {
                "canonical_name": row.canonical_name,
                "addresses": row.addresses,
            }
        return CompanyEntity.id, cols, _builder

    raise ValueError(f"Unbekanntes module: {module}")


def _record_iterator(
    db: Session, module: str, *, limit: int | None = None,
) -> Iterable[tuple[str, str, Any]]:
    """Generator: liefert (record_id_as_str, text_input, source_record).

    Wir paginieren ueber ID statt ``yield_per`` zu nutzen — yield_per haelt
    einen Server-Cursor offen, der nach einem ``commit()`` im Caller
    ungueltig wird (psycopg2: "named cursor isn't valid anymore"). Stattdessen:
    klassische Keyset-Pagination ueber ``id > last_id``. Funktioniert sowohl
    fuer BigInteger-IDs als auch fuer UUID-String-IDs (lexikografisch).
    """
    id_col, cols, build_record = _module_query_spec(module)

    last_id: Any = None
    produced = 0
    while True:
        q = db.query(*cols).order_by(id_col)
        if last_id is not None:
            q = q.filter(id_col > last_id)
        page_size = _PAGE_SIZE
        if limit is not None:
            remaining = int(limit) - produced
            if remaining <= 0:
                return
            page_size = min(page_size, remaining)
        rows = q.limit(page_size).all()
        if not rows:
            return
        for row in rows:
            record = build_record(row)
            yield str(row.id), build_embedding_text(
                module=module, record=record,
            ), record
            last_id = row.id
            produced += 1
            if limit is not None and produced >= int(limit):
                return


def rebuild_module_embeddings(
    db: Session,
    module: str,
    *,
    batch_size: int = 50,
    skip_existing: bool = True,
    dry: bool = False,
    limit: int | None = None,
) -> dict:
    """Iteriert alle Records eines Moduls, baut Embeddings.

    Liefert ``{processed, inserted, updated, skipped, failed}``.

    ``skip_existing`` (Default True): bestehende Embeddings werden NICHT neu
    gerechnet. Mit ``--force-update`` (= ``skip_existing=False``) wird jeder
    Eintrag ueberschrieben — das kostet beim ersten Einsatz nach Modell-
    Wechsel den vollen Build.

    ``dry``: keine DB-Schreibvorgaenge, kein Gateway-Aufruf — nur Zaehler.
    """
    if module not in VALID_MODULES:
        raise ValueError(f"Unbekanntes module: {module}")

    stats = _empty_rebuild_stats()

    # Vorab existierende Records einsammeln (fuer skip_existing-Pfad).
    existing_ids: set[str] = set()
    if skip_existing and not dry:
        rows = (
            db.query(EntityEmbedding.source_record_id)
            .filter(EntityEmbedding.source_module == module)
            .all()
        )
        existing_ids = {str(r[0]) for r in rows}

    pending: list[tuple[str, str]] = []  # (record_id_str, text_input)

    def _flush() -> None:
        """Nimmt den aktuellen Pending-Batch, holt Embeddings, schreibt sie."""
        if not pending:
            return
        nonlocal stats
        if dry:
            stats["inserted"] += len(pending)
            pending.clear()
            return
        try:
            embeddings = _batch_embed(
                [t for _, t in pending], batch_size=batch_size,
            )
        except Exception:  # noqa: BLE001
            log.exception(
                "Embedding-Batch fehlgeschlagen (module=%s, batch=%d).",
                module, len(pending),
            )
            stats["failed"] += len(pending)
            pending.clear()
            return
        # Existenz vor Upsert pruefen, damit wir inserted/updated korrekt
        # zaehlen koennen (nur wenn skip_existing=False, weil sonst keiner
        # vorhanden ist).
        if not skip_existing:
            id_set = {rid for rid, _ in pending}
            ex_rows = (
                db.query(EntityEmbedding.source_record_id)
                .filter(
                    EntityEmbedding.source_module == module,
                    EntityEmbedding.source_record_id.in_(id_set),
                )
                .all()
            )
            existing_now = {str(r[0]) for r in ex_rows}
        else:
            existing_now = set()

        for (record_id_str, text_input), emb in zip(pending, embeddings):
            try:
                upsert_embedding(
                    db,
                    module=module,
                    record_id=record_id_str,
                    text_input=text_input,
                    embedding=emb,
                )
                if record_id_str in existing_now:
                    stats["updated"] += 1
                else:
                    stats["inserted"] += 1
            except Exception:  # noqa: BLE001
                log.exception(
                    "Upsert fehlgeschlagen module=%s record_id=%s",
                    module, record_id_str,
                )
                stats["failed"] += 1
        try:
            db.commit()
        except Exception:  # noqa: BLE001
            log.exception("Commit fehlgeschlagen — rollback.")
            db.rollback()
        pending.clear()

    for record_id_str, embedding_text, _record in _record_iterator(
        db, module, limit=limit,
    ):
        stats["processed"] += 1
        if not embedding_text or not embedding_text.strip():
            stats["skipped"] += 1
            continue
        if skip_existing and record_id_str in existing_ids:
            stats["skipped"] += 1
            continue
        pending.append((record_id_str, embedding_text))
        if len(pending) >= batch_size:
            _flush()

    _flush()
    return stats


# ── Search ────────────────────────────────────────────────────────────────────


def search_semantic(
    db: Session,
    query: str,
    *,
    module: str | None = None,
    limit: int = 50,
    min_similarity: float = 0.7,
) -> list[dict]:
    """Cosine-Similarity-Suche.

    ``module``: optional auf 'state_aid' | 'beneficiary' | 'sanctions' |
    'company_entity' filtern; ``None`` oder ``'all'`` ergibt eine globale
    Suche ueber alle Module.

    ``min_similarity``: Records mit cos_sim < min werden weggelassen. cos_sim
    in [0..1], Berechnung: ``1 - (embedding <=> query)``.

    Rueckgabe: Liste von Dicts mit
      - source_module, source_record_id
      - cosine_similarity (float, 4 Nachkommastellen)
      - text_input (was war embeddet)
      - model_name
    sortiert nach Aehnlichkeit.

    Brueck fuer "Klimaschutz-Projekte in Bayern" — semantisch, nicht
    string-matchend.
    """
    if not query or not query.strip():
        return []

    if module is not None and module not in (*VALID_MODULES, "all"):
        raise ValueError(f"Unbekanntes module: {module}")

    qvec = get_embedding(query)
    if qvec is None:
        return []

    where = ""
    params: dict = {"qvec": str(qvec), "lim": int(limit)}
    if module and module != "all":
        where = "WHERE source_module = :module"
        params["module"] = module

    sql = text(f"""
        SELECT
            id,
            source_module,
            source_record_id,
            text_input,
            model_name,
            1 - (embedding <=> (:qvec)::vector) AS cosine_similarity
        FROM workshop_entity_embeddings
        {where}
        ORDER BY embedding <=> (:qvec)::vector
        LIMIT :lim
    """)

    try:
        rows = db.execute(sql, params).fetchall()
    except Exception:  # noqa: BLE001
        log.exception("Semantic-Search fehlgeschlagen (query=%r)", query[:80])
        return []

    out: list[dict] = []
    for r in rows:
        cos = float(r.cosine_similarity) if r.cosine_similarity is not None else 0.0
        if cos < min_similarity:
            continue
        out.append({
            "id": int(r.id),
            "source_module": r.source_module,
            "source_record_id": r.source_record_id,
            "text_input": r.text_input,
            "model_name": r.model_name,
            "cosine_similarity": round(cos, 4),
        })
    return out


# ── Stats ─────────────────────────────────────────────────────────────────────


def collect_stats(db: Session) -> dict:
    """Pro Modul: Anzahl Embeddings, letztes Update, Coverage.

    Coverage = lokale Embeddings / Quell-Records (in %).
    """
    out: dict[str, dict] = {}
    for mod in sorted(VALID_MODULES):
        cnt = (
            db.query(EntityEmbedding)
            .filter(EntityEmbedding.source_module == mod)
            .count()
        )
        last = (
            db.query(EntityEmbedding.updated_at)
            .filter(EntityEmbedding.source_module == mod)
            .order_by(EntityEmbedding.updated_at.desc())
            .first()
        )
        last_iso = None
        if last and last[0]:
            try:
                last_iso = last[0].isoformat()
            except Exception:  # noqa: BLE001
                last_iso = str(last[0])

        # Quell-Anzahl je Modul
        try:
            if mod == "state_aid":
                from models.state_aid import StateAidAward
                source_count = db.query(StateAidAward).count()
            elif mod == "beneficiary":
                from models.beneficiary_records import BeneficiaryRecord
                source_count = db.query(BeneficiaryRecord).count()
            elif mod == "sanctions":
                from models.sanctions_entries import SanctionsEntry
                source_count = db.query(SanctionsEntry).count()
            elif mod == "company_entity":
                from models.entities import CompanyEntity
                source_count = db.query(CompanyEntity).count()
            else:
                source_count = 0
        except Exception:  # noqa: BLE001
            log.exception("Source-Count fuer module=%s fehlgeschlagen.", mod)
            source_count = 0

        coverage_percent: float | None = None
        if source_count > 0:
            coverage_percent = round(100.0 * cnt / source_count, 1)

        out[mod] = {
            "embeddings": cnt,
            "source_records": source_count,
            "coverage_percent": coverage_percent,
            "last_update": last_iso,
        }

    out["_meta"] = {
        "model_name": EMBEDDING_MODEL,
        "embedding_dim": EMBEDDING_DIM,
        "backend": EMBEDDING_BACKEND,
    }
    return out


__all__ = [
    "VALID_MODULES",
    "build_embedding_text",
    "collect_stats",
    "get_embedding",
    "rebuild_module_embeddings",
    "search_semantic",
    "upsert_embedding",
]
