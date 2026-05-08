"""
flowworkshop · routers/embeddings.py

Layer A — REST-API fuer den Embedding-Layer (bge-m3) ueber alle Module.

Public lesbar:
- ``GET /api/embeddings/search?q=...``: Top-N semantisch aehnliche Records.
- ``GET /api/embeddings/stats``: Pro Modul Anzahl, letztes Update, Coverage%.

Admin-only:
- ``POST /api/embeddings/rebuild?module=...&batch_size=50``: Triggert einen
  Rebuild SYNCHRON. Bei grossen Bestaenden besser ueber das CLI-Skript
  ``scripts/rebuild_embeddings.py`` im Hintergrund laufen lassen.
"""
from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from routers.auth import require_admin, require_session
from services.entity_embeddings import (
    VALID_MODULES,
    collect_stats,
    rebuild_module_embeddings,
    search_semantic,
)

log = logging.getLogger(__name__)


router = APIRouter(prefix="/api/embeddings", tags=["embeddings"])


# ── Search ────────────────────────────────────────────────────────────────────


@router.get("/search")
def embeddings_search(
    q: str = Query(..., min_length=1, max_length=500),
    module: Literal[
        "state_aid", "beneficiary", "sanctions", "company_entity", "all",
    ] = Query("all"),
    limit: int = Query(20, ge=1, le=100),
    min_similarity: float = Query(0.7, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
    _session: dict = Depends(require_session),
) -> dict:
    """Liefert top-N semantisch aehnliche Records inkl. cosine_similarity-Score.

    Empfehlung: kombiniert mit Fuzzy-Match — Embedding fuer "thematisch
    aehnlich" (z.B. "Klimaschutz in Bayern"), Fuzzy fuer Namensvarianten.
    """
    mod_filter = None if module == "all" else module
    results = search_semantic(
        db, q,
        module=mod_filter,
        limit=int(limit),
        min_similarity=float(min_similarity),
    )
    return {
        "query": q,
        "module": module,
        "min_similarity": float(min_similarity),
        "count": len(results),
        "results": results,
    }


# ── Stats ─────────────────────────────────────────────────────────────────────


@router.get("/stats")
def embeddings_stats(
    db: Session = Depends(get_db),
    _session: dict = Depends(require_session),
) -> dict:
    """Pro Modul: Anzahl Embeddings, letztes Update, Coverage%.

    Coverage = lokal vorhandene Embeddings / Quell-Records.
    """
    return collect_stats(db)


# ── Admin: Rebuild ────────────────────────────────────────────────────────────


@router.post("/rebuild")
def embeddings_rebuild(
    module: Literal[
        "state_aid", "beneficiary", "sanctions", "company_entity", "all",
    ] = Query("all"),
    batch_size: int = Query(50, ge=1, le=500),
    skip_existing: bool = Query(True),
    dry: bool = Query(False),
    limit: int | None = Query(
        None, ge=1,
        description="Maximale Records pro Modul — fuer schnelle Tests.",
    ),
    _session: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Triggert einen Rebuild SYNCHRON.

    Achtung: bei grossen Bestaenden (180k Records) dauert das ~30 min und
    blockiert den HTTP-Worker. Empfehlung fuer Initial-Build:
    ``docker exec -d <backend> python scripts/rebuild_embeddings.py --module all``
    """
    targets: list[str]
    if module == "all":
        targets = sorted(VALID_MODULES)
    else:
        targets = [module]

    out: dict = {
        "module": module,
        "batch_size": batch_size,
        "skip_existing": skip_existing,
        "dry": dry,
        "limit": limit,
        "results": {},
    }
    for mod in targets:
        log.info(
            "Embedding-Rebuild ausgeloest: module=%s batch_size=%d "
            "skip_existing=%s dry=%s limit=%s",
            mod, batch_size, skip_existing, dry, limit,
        )
        try:
            stats = rebuild_module_embeddings(
                db, mod,
                batch_size=int(batch_size),
                skip_existing=bool(skip_existing),
                dry=bool(dry),
                limit=limit,
            )
            out["results"][mod] = stats
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        except Exception as exc:  # noqa: BLE001
            log.exception("Rebuild fehlgeschlagen module=%s", mod)
            out["results"][mod] = {
                "status": "failed",
                "error": str(exc)[:500],
            }
    return out
