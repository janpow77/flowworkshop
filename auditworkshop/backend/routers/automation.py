"""
flowworkshop · routers/automation.py
Admin-Endpoints für Auto-Harvest, Sanktions-Refresh und LLM-Logs
(Plan v3.2 §16).
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from database import get_db
from models.automation import (
    HarvestRun, HarvestSourceUpdate, SanctionsRefreshRun, LlmQuestionLog,
)
from routers.auth import require_admin

router = APIRouter(prefix="/api/admin", tags=["automation"])
log = logging.getLogger(__name__)


# ─── Begünstigten-Harvest ────────────────────────────────────────────────────

@router.get("/harvest/runs")
def list_harvest_runs(request: Request, limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    require_admin(request)
    rows = (
        db.query(HarvestRun)
        .order_by(desc(HarvestRun.started_at))
        .limit(limit).all()
    )
    return [
        {
            "id": r.id,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "triggered_by": r.triggered_by,
            "status": r.status,
            "sources_total": r.sources_total or 0,
            "sources_ok": r.sources_ok or 0,
            "sources_skipped": r.sources_skipped or 0,
            "sources_failed": r.sources_failed or 0,
        }
        for r in rows
    ]


@router.post("/harvest/run")
async def trigger_harvest(request: Request):
    sess = require_admin(request)
    import asyncio
    from services.scheduler import run_beneficiary_harvest
    actor = f"admin:{sess.get('user_id')}"
    # asynchron starten — Subprozess kann mehrere Minuten laufen
    asyncio.create_task(asyncio.to_thread(run_beneficiary_harvest, actor))
    return {"status": "started", "message": "Harvest läuft im Hintergrund."}


# ─── Sanktionen ───────────────────────────────────────────────────────────────

@router.get("/sanctions/runs")
def list_sanctions_runs(request: Request, limit: int = Query(30, ge=1, le=120), db: Session = Depends(get_db)):
    require_admin(request)
    rows = (
        db.query(SanctionsRefreshRun)
        .order_by(desc(SanctionsRefreshRun.started_at))
        .limit(limit).all()
    )
    return [
        {
            "id": r.id,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "triggered_by": r.triggered_by,
            "status": r.status,
            "rows_before": r.rows_before, "rows_after": r.rows_after,
            "persons_before": r.persons_before, "persons_after": r.persons_after,
            "organizations_before": r.organizations_before,
            "organizations_after": r.organizations_after,
            "file_size_bytes": r.file_size_bytes,
            "error": r.error,
            # Multi-Source-Felder (Multi-Sanctions-Refresh, Mai 2026)
            "sources": r.sources,
            "parameters": r.parameters,
        }
        for r in rows
    ]


@router.post("/sanctions/refresh")
def trigger_sanctions(request: Request):
    sess = require_admin(request)
    from services.scheduler import run_sanctions_refresh
    return run_sanctions_refresh(triggered_by=f"admin:{sess.get('user_id')}")


# ─── LLM-Logs ────────────────────────────────────────────────────────────────

@router.get("/llm/stats")
def llm_stats(request: Request, scenario: int | None = None, days: int = 30, db: Session = Depends(get_db)):
    require_admin(request)
    since = datetime.utcnow() - timedelta(days=days)
    q = db.query(LlmQuestionLog).filter(LlmQuestionLog.created_at >= since)
    if scenario:
        q = q.filter(LlmQuestionLog.scenario == scenario)
    rows = q.all()
    total = len(rows)
    paths: dict[str, int] = {}
    avg_elapsed: dict[str, list[int]] = {}
    unique_users = set()
    for r in rows:
        p = r.answer_path or "unknown"
        paths[p] = paths.get(p, 0) + 1
        if r.elapsed_ms is not None:
            avg_elapsed.setdefault(p, []).append(r.elapsed_ms)
        if r.user_id:
            unique_users.add(r.user_id)
    avg_by_path = {p: round(sum(v) / len(v)) for p, v in avg_elapsed.items() if v}

    # Top-Fragen (normalisiert)
    top_q: dict[str, int] = {}
    for r in rows:
        key = (r.prompt_normalized or r.prompt or "")[:120]
        if key:
            top_q[key] = top_q.get(key, 0) + 1
    top = sorted(top_q.items(), key=lambda x: -x[1])[:20]

    # Slow queries
    slow = (
        q.filter(LlmQuestionLog.elapsed_ms != None, LlmQuestionLog.elapsed_ms > 30000)  # noqa: E711
        .order_by(desc(LlmQuestionLog.elapsed_ms)).limit(10).all()
    )
    failed = (
        q.filter(LlmQuestionLog.items_returned == 0)
        .order_by(desc(LlmQuestionLog.created_at)).limit(20).all()
    )
    return {
        "total": total,
        "unique_users": len(unique_users),
        "paths": paths,
        "avg_elapsed_ms_by_path": avg_by_path,
        "top_questions": [{"prompt": k, "count": v} for k, v in top],
        "slow_queries": [
            {
                "prompt": r.prompt[:200],
                "answer_path": r.answer_path,
                "elapsed_ms": r.elapsed_ms,
                "model": r.model_name,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in slow
        ],
        "failed_queries": [
            {
                "prompt": r.prompt[:200],
                "answer_path": r.answer_path,
                "matched_mode": r.matched_mode,
                "name_filter_label": r.name_filter_label,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in failed
        ],
    }


@router.get("/llm/logs")
def llm_logs(
    request: Request,
    scenario: int | None = None,
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    require_admin(request)
    q = db.query(LlmQuestionLog)
    if scenario:
        q = q.filter(LlmQuestionLog.scenario == scenario)
    rows = q.order_by(desc(LlmQuestionLog.created_at)).limit(limit).all()
    return [
        {
            "id": r.id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "scenario": r.scenario,
            "user_id": r.user_id,
            "prompt": r.prompt,
            "answer_path": r.answer_path,
            "matched_mode": r.matched_mode,
            "items_returned": r.items_returned,
            "elapsed_ms": r.elapsed_ms,
            "model_name": r.model_name,
            "response_excerpt": r.response_excerpt,
            "error_message": r.error_message,
        }
        for r in rows
    ]
