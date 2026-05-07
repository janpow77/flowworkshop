"""
flowworkshop · routers/notifications.py
Notification-Center (Plan v3.2 Phase 6) — internes Bell-Icon.
"""
from __future__ import annotations
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import desc
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from models.automation import Notification
from routers.auth import require_session

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def push_notification(
    user_id: str, kind: str, title: str,
    body: str | None = None, link: str | None = None,
) -> None:
    """Standalone-Helper: schreibt eine Notification in die DB.
    Non-blocking — bei Fehler nur loggen.
    """
    if not user_id:
        return
    db = SessionLocal()
    try:
        db.add(Notification(
            user_id=user_id, kind=kind, title=title,
            body=body, link=link,
        ))
        db.commit()
    except Exception:
        import logging
        logging.getLogger(__name__).exception("push_notification fehlgeschlagen")
    finally:
        db.close()


@router.get("")
def list_notifications(
    request: Request,
    only_unread: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    sess = require_session(request)
    q = db.query(Notification).filter(Notification.user_id == sess["user_id"])
    if only_unread:
        q = q.filter(Notification.read_at.is_(None))
    rows = q.order_by(desc(Notification.created_at)).limit(limit).all()
    unread = (
        db.query(Notification)
        .filter(Notification.user_id == sess["user_id"], Notification.read_at.is_(None))
        .count()
    )
    return {
        "unread_count": unread,
        "items": [
            {
                "id": n.id,
                "kind": n.kind,
                "title": n.title,
                "body": n.body,
                "link": n.link,
                "created_at": n.created_at.isoformat() if n.created_at else None,
                "read_at": n.read_at.isoformat() if n.read_at else None,
            }
            for n in rows
        ],
    }


@router.post("/{nid}/mark-read")
def mark_read(nid: int, request: Request, db: Session = Depends(get_db)):
    sess = require_session(request)
    n = db.query(Notification).filter(
        Notification.id == nid, Notification.user_id == sess["user_id"],
    ).first()
    if not n:
        raise HTTPException(404)
    if not n.read_at:
        n.read_at = datetime.utcnow()
        db.commit()
    return {"status": "ok"}


@router.post("/mark-all-read")
def mark_all_read(request: Request, db: Session = Depends(get_db)):
    sess = require_session(request)
    db.query(Notification).filter(
        Notification.user_id == sess["user_id"],
        Notification.read_at.is_(None),
    ).update({Notification.read_at: datetime.utcnow()})
    db.commit()
    return {"status": "ok"}
