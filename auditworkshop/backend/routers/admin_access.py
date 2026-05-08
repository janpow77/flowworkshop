"""
flowworkshop · routers/admin_access.py
Admin-Auswertungen ueber das ``workshop_access_log``.

Alle Endpoints unterhalb ``/api/admin/access`` setzen ``require_admin``
voraus. Sie liefern aggregierte Statistiken aus dem Access-Log fuer den
Admin-Dashboard-Report.

Endpoints:
- GET /summary       — Kennzahlen fuer ein Zeitfenster (Default 24h)
- GET /timeseries    — Zeitreihe je Bucket fuer Charts
- GET /top-paths     — meist genutzte Routen (sortiert)
- GET /top-users     — aktivste Nutzer (mit Name/Org via JOIN auf
                        workshop_registrations)
- GET /recent        — letzte N Eintraege (Drilldown, mit Filter)
- GET /stats/state-aid — speziell fuer State-Aid-Endpoints
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import desc, func as sql_func
from sqlalchemy.orm import Session

from database import get_db
from models.access_log import AccessLog
from models.registration import Registration
from routers.auth import require_admin

router = APIRouter(prefix="/api/admin/access", tags=["admin-access"])
log = logging.getLogger(__name__)


# ── Helper ────────────────────────────────────────────────────────────────────


def _utcnow_naive() -> datetime:
    """UTC-Zeit ohne Timezone-Info — passt zum DB-Spaltentyp DateTime."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _since_until(since_hours: int) -> tuple[datetime, datetime]:
    until = _utcnow_naive()
    since = until - timedelta(hours=max(1, int(since_hours)))
    return since, until


def _percentile_pg(column, p: float):
    """PostgreSQL ``percentile_cont(p) WITHIN GROUP (ORDER BY column)`` als
    SQLAlchemy-Ausdruck.
    """
    return sql_func.percentile_cont(p).within_group(column.asc())


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/summary")
def access_summary(
    request: Request,
    since_hours: int = Query(24, ge=1, le=24 * 30),
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    """Gesamtkennzahlen fuer das angegebene Zeitfenster."""
    since, until = _since_until(since_hours)
    base = db.query(AccessLog).filter(AccessLog.created_at >= since)

    total_requests = base.count()
    unique_users = (
        db.query(sql_func.count(sql_func.distinct(AccessLog.user_id)))
        .filter(AccessLog.created_at >= since, AccessLog.user_id.isnot(None))
        .scalar() or 0
    )
    unique_ips = (
        db.query(sql_func.count(sql_func.distinct(AccessLog.ip_hash)))
        .filter(AccessLog.created_at >= since, AccessLog.ip_hash.isnot(None))
        .scalar() or 0
    )

    # Status-Klassen (2xx/3xx/4xx/5xx)
    status_rows = (
        db.query(
            (AccessLog.status_code / 100).label("klass"),
            sql_func.count().label("c"),
        )
        .filter(AccessLog.created_at >= since)
        .group_by("klass")
        .all()
    )
    by_status: dict[str, int] = {"2xx": 0, "3xx": 0, "4xx": 0, "5xx": 0}
    for row in status_rows:
        klass = int(row.klass or 0)
        key = f"{klass}xx"
        if key in by_status:
            by_status[key] += int(row.c)

    avg_p95 = (
        db.query(
            sql_func.coalesce(sql_func.avg(AccessLog.duration_ms), 0).label("avg_ms"),
            sql_func.coalesce(_percentile_pg(AccessLog.duration_ms, 0.95), 0).label("p95_ms"),
        )
        .filter(AccessLog.created_at >= since)
        .first()
    )
    avg_ms = float(avg_p95.avg_ms or 0)
    p95_ms = float(avg_p95.p95_ms or 0)

    # RPS: pro 60-Sekunden-Bucket
    rps_rows = (
        db.query(
            sql_func.date_trunc("minute", AccessLog.created_at).label("ts"),
            sql_func.count().label("c"),
        )
        .filter(AccessLog.created_at >= since)
        .group_by("ts")
        .all()
    )
    rps_peak = max((int(r.c) for r in rps_rows), default=0) / 60.0
    elapsed_minutes = max(1, int((until - since).total_seconds() / 60))
    rps_avg = total_requests / (elapsed_minutes * 60)

    return {
        "since": since.isoformat() + "Z",
        "until": until.isoformat() + "Z",
        "since_hours": int(since_hours),
        "total_requests": int(total_requests),
        "unique_users": int(unique_users),
        "unique_ips": int(unique_ips),
        "by_status": by_status,
        "avg_duration_ms": round(avg_ms, 1),
        "p95_duration_ms": round(p95_ms, 1),
        "rps_peak": round(rps_peak, 3),
        "rps_avg": round(rps_avg, 3),
    }


@router.get("/timeseries")
def access_timeseries(
    request: Request,
    since_hours: int = Query(24, ge=1, le=24 * 30),
    bucket_minutes: int = Query(10, ge=1, le=240),
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    """Zeitreihe (Buckets) fuer Charts: requests, unique_users, avg_ms."""
    since, until = _since_until(since_hours)
    bucket = int(bucket_minutes)

    # PostgreSQL-spezifisch: floor(epoch / bucket_seconds) * bucket_seconds
    bucket_secs = bucket * 60
    bucket_expr = sql_func.to_timestamp(
        sql_func.floor(
            sql_func.extract("epoch", AccessLog.created_at) / bucket_secs
        ) * bucket_secs
    ).label("ts")

    rows = (
        db.query(
            bucket_expr,
            sql_func.count().label("requests"),
            sql_func.count(sql_func.distinct(AccessLog.user_id)).label("unique_users"),
            sql_func.coalesce(sql_func.avg(AccessLog.duration_ms), 0).label("avg_ms"),
        )
        .filter(AccessLog.created_at >= since)
        .group_by("ts")
        .order_by("ts")
        .all()
    )
    return {
        "since": since.isoformat() + "Z",
        "until": until.isoformat() + "Z",
        "bucket_minutes": bucket,
        "buckets": [
            {
                "ts": (row.ts.isoformat() if row.ts else None),
                "requests": int(row.requests or 0),
                "unique_users": int(row.unique_users or 0),
                "avg_ms": round(float(row.avg_ms or 0), 1),
            }
            for row in rows
        ],
    }


@router.get("/top-paths")
def access_top_paths(
    request: Request,
    since_hours: int = Query(24, ge=1, le=24 * 30),
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    """Top-N Pfad-Templates nach Request-Anzahl."""
    since, _until = _since_until(since_hours)
    rows = (
        db.query(
            AccessLog.path_template,
            sql_func.count().label("requests"),
            sql_func.count(sql_func.distinct(AccessLog.user_id)).label("unique_users"),
            sql_func.coalesce(sql_func.avg(AccessLog.duration_ms), 0).label("avg_ms"),
            sql_func.coalesce(_percentile_pg(AccessLog.duration_ms, 0.95), 0).label("p95_ms"),
        )
        .filter(AccessLog.created_at >= since)
        .group_by(AccessLog.path_template)
        .order_by(desc("requests"))
        .limit(limit)
        .all()
    )
    return {
        "since_hours": int(since_hours),
        "items": [
            {
                "path_template": row.path_template,
                "requests": int(row.requests or 0),
                "unique_users": int(row.unique_users or 0),
                "avg_ms": round(float(row.avg_ms or 0), 1),
                "p95_ms": round(float(row.p95_ms or 0), 1),
            }
            for row in rows
        ],
    }


@router.get("/top-users")
def access_top_users(
    request: Request,
    since_hours: int = Query(24, ge=1, le=24 * 30),
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    """Top-N Nutzer (mit Name/Org via Registration-JOIN)."""
    since, _until = _since_until(since_hours)
    rows = (
        db.query(
            AccessLog.user_id,
            AccessLog.role,
            sql_func.count().label("requests"),
            sql_func.max(AccessLog.created_at).label("last_seen_at"),
            sql_func.count(sql_func.distinct(AccessLog.path_template)).label("paths_distinct"),
        )
        .filter(AccessLog.created_at >= since, AccessLog.user_id.isnot(None))
        .group_by(AccessLog.user_id, AccessLog.role)
        .order_by(desc("requests"))
        .limit(limit)
        .all()
    )
    user_ids = [r.user_id for r in rows if r.user_id]
    name_lookup: dict[str, tuple[str, str]] = {}
    if user_ids:
        regs = (
            db.query(
                Registration.id, Registration.first_name, Registration.last_name,
                Registration.organization,
            )
            .filter(Registration.id.in_(user_ids))
            .all()
        )
        for r in regs:
            full = f"{(r.first_name or '').strip()} {(r.last_name or '').strip()}".strip()
            name_lookup[r.id] = (full or "—", r.organization or "")

    items = []
    for row in rows:
        name, org = name_lookup.get(row.user_id or "", ("—", ""))
        items.append({
            "user_id": row.user_id,
            "name": name,
            "organization": org,
            "role": row.role or "anon",
            "requests": int(row.requests or 0),
            "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
            "paths_distinct": int(row.paths_distinct or 0),
        })
    return {
        "since_hours": int(since_hours),
        "items": items,
    }


@router.get("/recent")
def access_recent(
    request: Request,
    limit: int = Query(200, ge=1, le=1000),
    user_id: str | None = Query(None),
    path: str | None = Query(None, description="Substring-Filter auf path/path_template"),
    before_id: int | None = Query(None, description="Cursor: nur Eintraege mit id < before_id"),
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    """Letzte N Eintraege (Drilldown). Filterbar nach user_id und Pfad."""
    q = db.query(AccessLog).order_by(desc(AccessLog.id))
    if user_id:
        q = q.filter(AccessLog.user_id == user_id)
    if path:
        like = f"%{path}%"
        q = q.filter(
            (AccessLog.path.ilike(like)) | (AccessLog.path_template.ilike(like))
        )
    if before_id:
        q = q.filter(AccessLog.id < int(before_id))
    rows = q.limit(limit).all()
    return {
        "count": len(rows),
        "next_before_id": rows[-1].id if rows else None,
        "items": [
            {
                "id": row.id,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "method": row.method,
                "path": row.path,
                "path_template": row.path_template,
                "query_string": row.query_string,
                "status_code": row.status_code,
                "duration_ms": row.duration_ms,
                "user_id": row.user_id,
                "role": row.role,
                "ip_hash": row.ip_hash,
                "ua_short": row.ua_short,
                "referer_path": row.referer_path,
                "response_size": row.response_size,
            }
            for row in rows
        ],
    }


@router.get("/stats/state-aid")
def access_stats_state_aid(
    request: Request,
    since_hours: int = Query(24, ge=1, le=24 * 30),
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    """Spezialauswertung: alle ``/api/state-aid/*`` Endpoints aggregiert.

    Liefert Counts fuer search-Anfragen, ask-Anfragen (mit/ohne LLM),
    Karten-Aufrufe und Export-Downloads. Grundlage ist der Pfad-Template.
    """
    since, until = _since_until(since_hours)

    base = (
        db.query(
            AccessLog.path_template,
            sql_func.count().label("requests"),
            sql_func.count(sql_func.distinct(AccessLog.user_id)).label("unique_users"),
            sql_func.coalesce(sql_func.avg(AccessLog.duration_ms), 0).label("avg_ms"),
            sql_func.coalesce(_percentile_pg(AccessLog.duration_ms, 0.95), 0).label("p95_ms"),
        )
        .filter(
            AccessLog.created_at >= since,
            AccessLog.path_template.like("/api/state-aid/%"),
        )
        .group_by(AccessLog.path_template)
        .order_by(desc("requests"))
    )
    rows = base.all()

    # Buckets — sind ueberlappend, das ist gewollt (z.B. /search vs. /search/{id})
    buckets = {
        "search": ("/api/state-aid/search",),
        "ask": ("/api/state-aid/ask",),
        "map": ("/api/state-aid/map",),
        "export": ("/api/state-aid/export",),
        "status": ("/api/state-aid/status",),
        "harvest": ("/api/state-aid/harvest",),
        "sources": ("/api/state-aid/sources",),
    }

    aggregated: dict[str, dict] = {
        key: {"requests": 0, "unique_users": 0, "avg_ms": 0.0, "p95_ms": 0.0}
        for key in buckets
    }
    # detaillierte Liste aller Templates mit Praefix
    items = []
    for row in rows:
        item = {
            "path_template": row.path_template,
            "requests": int(row.requests or 0),
            "unique_users": int(row.unique_users or 0),
            "avg_ms": round(float(row.avg_ms or 0), 1),
            "p95_ms": round(float(row.p95_ms or 0), 1),
        }
        items.append(item)
        for key, prefixes in buckets.items():
            if any(row.path_template and row.path_template.startswith(p) for p in prefixes):
                bucket = aggregated[key]
                bucket["requests"] += item["requests"]
                bucket["unique_users"] = max(bucket["unique_users"], item["unique_users"])
                # gewichteter Mittelwert ist nicht 100% exakt, reicht aber als KPI
                if item["requests"] > 0:
                    total_old = bucket["requests"] - item["requests"]
                    if total_old > 0:
                        bucket["avg_ms"] = (
                            (bucket["avg_ms"] * total_old + item["avg_ms"] * item["requests"])
                            / bucket["requests"]
                        )
                    else:
                        bucket["avg_ms"] = item["avg_ms"]
                    bucket["p95_ms"] = max(bucket["p95_ms"], item["p95_ms"])

    total_requests = sum(int(r.requests or 0) for r in rows)
    return {
        "since": since.isoformat() + "Z",
        "until": until.isoformat() + "Z",
        "since_hours": int(since_hours),
        "total_requests": total_requests,
        "by_bucket": {
            k: {
                "requests": int(v["requests"]),
                "unique_users": int(v["unique_users"]),
                "avg_ms": round(float(v["avg_ms"]), 1),
                "p95_ms": round(float(v["p95_ms"]), 1),
            }
            for k, v in aggregated.items()
        },
        "items": items,
    }
