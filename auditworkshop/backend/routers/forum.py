"""
flowworkshop · routers/forum.py
Forum-API (Plan v3.2 §6) — Discourse-/CIRCABC-Stil.

Lesen ist öffentlich, Schreiben erfordert eingeloggten User mit
status='active'. Moderatoren-Aktionen (pin, lock, solved, delete fremde
Posts) erfordern Mod-Rolle.
"""
from __future__ import annotations
import logging
import re
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from database import get_db
from models.forum import (
    ForumCategory, ForumThread, ForumPost, ForumReaction,
    ForumTag, ForumThreadTag, ForumReadState,
)
from models.registration import Registration
from routers.auth import require_session, require_moderator

router = APIRouter(prefix="/api/forum", tags=["forum"])
log = logging.getLogger(__name__)


# ─── Schemas ────────────────────────────────────────────────────────────────

class CategoryOut(BaseModel):
    id: str
    slug: str
    name: str
    description: str | None = None
    icon: str | None = None
    color: str | None = None
    thread_count: int = 0
    post_count: int = 0
    last_post_at: datetime | None = None


class ThreadSummary(BaseModel):
    id: str
    slug: str
    category_slug: str
    category_name: str
    title: str
    author_name: str | None = None
    author_organization: str | None = None
    created_at: datetime | None = None
    last_post_at: datetime | None = None
    post_count: int = 0
    view_count: int = 0
    pinned: bool = False
    locked: bool = False
    solved: bool = False
    reactions: dict[str, int] = Field(default_factory=dict)


class PostOut(BaseModel):
    id: str
    thread_id: str
    parent_post_id: str | None = None
    author_name: str | None = None
    author_organization: str | None = None
    body_md: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    edit_count: int = 0
    reactions: dict[str, int] = Field(default_factory=dict)
    user_reactions: list[str] = Field(default_factory=list)
    is_solution: bool = False
    can_edit: bool = False


class ThreadDetailOut(BaseModel):
    id: str
    slug: str
    category: CategoryOut
    title: str
    pinned: bool
    locked: bool
    solved_post_id: str | None = None
    view_count: int
    posts: list[PostOut]


class CreateThread(BaseModel):
    category_slug: str
    title: str = Field(min_length=3, max_length=200)
    body_md: str = Field(min_length=3)


class CreatePost(BaseModel):
    body_md: str = Field(min_length=1)
    parent_post_id: str | None = None


# ─── Helpers ────────────────────────────────────────────────────────────────

def _slugify(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[äöüß]", lambda m: {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}[m.group(0)], s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:100] or uuid.uuid4().hex[:8]


def _reactions_for_posts(db: Session, post_ids: list[str], user_id: str | None = None) -> tuple[dict, dict]:
    """Gibt (counts_by_post[post_id][kind] = n, user_reactions_by_post[post_id] = [kind...]) zurück."""
    if not post_ids:
        return {}, {}
    rows = (
        db.query(ForumReaction.post_id, ForumReaction.kind, func.count())
        .filter(ForumReaction.post_id.in_(post_ids))
        .group_by(ForumReaction.post_id, ForumReaction.kind)
        .all()
    )
    counts: dict[str, dict[str, int]] = {}
    for pid, kind, n in rows:
        counts.setdefault(pid, {})[kind] = int(n)
    user_reactions: dict[str, list[str]] = {}
    if user_id:
        ur = (
            db.query(ForumReaction.post_id, ForumReaction.kind)
            .filter(ForumReaction.post_id.in_(post_ids), ForumReaction.user_id == user_id)
            .all()
        )
        for pid, kind in ur:
            user_reactions.setdefault(pid, []).append(kind)
    return counts, user_reactions


def _ensure_active_user(request: Request, db: Session) -> Registration:
    sess = require_session(request)
    user = db.query(Registration).filter(Registration.id == sess["user_id"]).first()
    if not user:
        raise HTTPException(401, "Nutzer nicht gefunden.")
    status = (getattr(user, "status", None) or "active").lower()
    if status != "active":
        raise HTTPException(403, "Konto nicht aktiv.")
    return user


# ─── Endpoints — Kategorien ─────────────────────────────────────────────────

@router.get("/categories", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db)):
    cats = (
        db.query(ForumCategory)
        .filter(ForumCategory.archived.is_(False))
        .order_by(ForumCategory.sort_order, ForumCategory.name)
        .all()
    )
    # Statistiken pro Kategorie
    out: list[CategoryOut] = []
    for c in cats:
        stats = (
            db.query(
                func.count(ForumThread.id),
                func.coalesce(func.sum(ForumThread.post_count), 0),
                func.max(ForumThread.last_post_at),
            )
            .filter(ForumThread.category_id == c.id)
            .one()
        )
        out.append(CategoryOut(
            id=c.id, slug=c.slug, name=c.name,
            description=c.description, icon=c.icon, color=c.color,
            thread_count=int(stats[0] or 0),
            post_count=int(stats[1] or 0),
            last_post_at=stats[2],
        ))
    return out


# ─── Endpoints — Threads ────────────────────────────────────────────────────

@router.get("/threads", response_model=list[ThreadSummary])
def list_threads(
    category: str | None = Query(None, description="category slug"),
    sort: str = Query("latest", description="latest|top|unanswered"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = (
        db.query(ForumThread, ForumCategory)
        .join(ForumCategory, ForumCategory.id == ForumThread.category_id)
    )
    if category:
        q = q.filter(ForumCategory.slug == category)
    if sort == "top":
        q = q.order_by(desc(ForumThread.pinned), desc(ForumThread.post_count), desc(ForumThread.last_post_at))
    elif sort == "unanswered":
        q = q.filter(ForumThread.post_count == 0).order_by(desc(ForumThread.created_at))
    else:  # latest
        q = q.order_by(desc(ForumThread.pinned), desc(ForumThread.last_post_at))
    rows = q.limit(limit).all()
    return [
        ThreadSummary(
            id=t.id, slug=t.slug,
            category_slug=c.slug, category_name=c.name,
            title=t.title,
            author_name=t.author_name, author_organization=t.author_organization,
            created_at=t.created_at, last_post_at=t.last_post_at,
            post_count=t.post_count, view_count=t.view_count,
            pinned=t.pinned, locked=t.locked,
            solved=bool(t.solved_post_id),
        )
        for t, c in rows
    ]


@router.get("/threads/{thread_id}", response_model=ThreadDetailOut)
def get_thread(thread_id: str, request: Request, db: Session = Depends(get_db)):
    t = db.query(ForumThread).filter(ForumThread.id == thread_id).first()
    if not t:
        raise HTTPException(404, "Thread nicht gefunden.")
    c = db.query(ForumCategory).filter(ForumCategory.id == t.category_id).first()
    posts = (
        db.query(ForumPost)
        .filter(ForumPost.thread_id == t.id, ForumPost.deleted_at.is_(None))
        .order_by(ForumPost.created_at.asc())
        .all()
    )
    # View-Count erhöhen (best-effort, nicht authentifiziert)
    t.view_count = (t.view_count or 0) + 1
    db.commit()

    # Reactions sammeln
    sess = None
    try:
        sess = require_session(request)
    except Exception:
        pass
    user_id = sess.get("user_id") if sess else None

    post_ids = [p.id for p in posts]
    counts, user_reactions = _reactions_for_posts(db, post_ids, user_id=user_id)

    cat_summary = (
        db.query(func.count(ForumThread.id), func.coalesce(func.sum(ForumThread.post_count), 0))
        .filter(ForumThread.category_id == c.id)
        .one()
    )
    cat_out = CategoryOut(
        id=c.id, slug=c.slug, name=c.name, description=c.description,
        icon=c.icon, color=c.color,
        thread_count=int(cat_summary[0] or 0),
        post_count=int(cat_summary[1] or 0),
    )

    return ThreadDetailOut(
        id=t.id, slug=t.slug, category=cat_out, title=t.title,
        pinned=t.pinned, locked=t.locked,
        solved_post_id=t.solved_post_id,
        view_count=t.view_count,
        posts=[
            PostOut(
                id=p.id, thread_id=p.thread_id,
                parent_post_id=p.parent_post_id,
                author_name=p.author_name, author_organization=p.author_organization,
                body_md=p.body_md,
                created_at=p.created_at, updated_at=p.updated_at,
                edit_count=p.edit_count,
                reactions=counts.get(p.id, {}),
                user_reactions=user_reactions.get(p.id, []),
                is_solution=(p.id == t.solved_post_id),
                can_edit=(user_id is not None and p.author_user_id == user_id),
            )
            for p in posts
        ],
    )


@router.post("/threads", response_model=ThreadDetailOut, status_code=201)
def create_thread(body: CreateThread, request: Request, db: Session = Depends(get_db)):
    user = _ensure_active_user(request, db)
    cat = db.query(ForumCategory).filter(ForumCategory.slug == body.category_slug).first()
    if not cat or cat.archived:
        raise HTTPException(404, "Kategorie nicht gefunden.")
    slug = _slugify(body.title)
    thread = ForumThread(
        slug=slug,
        category_id=cat.id,
        title=body.title.strip(),
        body_md=body.body_md.strip(),
        author_user_id=user.id,
        author_name=f"{user.first_name} {user.last_name}",
        author_organization=user.organization,
        post_count=1, view_count=0,
    )
    db.add(thread)
    db.flush()
    # Top-Post als ForumPost anlegen (für einheitliche Anzeige)
    top_post = ForumPost(
        thread_id=thread.id,
        author_user_id=user.id,
        author_name=thread.author_name,
        author_organization=thread.author_organization,
        body_md=body.body_md.strip(),
    )
    db.add(top_post)
    db.commit()
    return get_thread(thread.id, request, db)


@router.post("/threads/{thread_id}/posts", response_model=PostOut, status_code=201)
def create_post(thread_id: str, body: CreatePost, request: Request, db: Session = Depends(get_db)):
    user = _ensure_active_user(request, db)
    thread = db.query(ForumThread).filter(ForumThread.id == thread_id).first()
    if not thread:
        raise HTTPException(404, "Thread nicht gefunden.")
    if thread.locked:
        raise HTTPException(403, "Thread ist gesperrt.")
    post = ForumPost(
        thread_id=thread_id,
        parent_post_id=body.parent_post_id,
        author_user_id=user.id,
        author_name=f"{user.first_name} {user.last_name}",
        author_organization=user.organization,
        body_md=body.body_md.strip(),
    )
    db.add(post)
    thread.post_count = (thread.post_count or 0) + 1
    thread.last_post_at = func.now()
    db.commit()
    db.refresh(post)
    return PostOut(
        id=post.id, thread_id=post.thread_id, parent_post_id=post.parent_post_id,
        author_name=post.author_name, author_organization=post.author_organization,
        body_md=post.body_md,
        created_at=post.created_at, updated_at=post.updated_at,
        edit_count=post.edit_count,
        can_edit=True,
    )


# ─── Mod-Aktionen ────────────────────────────────────────────────────────────

@router.post("/threads/{thread_id}/pin")
def pin_thread(thread_id: str, request: Request, db: Session = Depends(get_db)):
    require_moderator(request)
    t = db.query(ForumThread).filter(ForumThread.id == thread_id).first()
    if not t: raise HTTPException(404, "Thread nicht gefunden.")
    t.pinned = not t.pinned
    db.commit()
    return {"pinned": t.pinned}


@router.post("/threads/{thread_id}/lock")
def lock_thread(thread_id: str, request: Request, db: Session = Depends(get_db)):
    require_moderator(request)
    t = db.query(ForumThread).filter(ForumThread.id == thread_id).first()
    if not t: raise HTTPException(404, "Thread nicht gefunden.")
    t.locked = not t.locked
    db.commit()
    return {"locked": t.locked}


@router.post("/threads/{thread_id}/solve")
def mark_solution(thread_id: str, post_id: str, request: Request, db: Session = Depends(get_db)):
    """Markiert einen Post als Lösung. Threadstarter oder Mod können das."""
    sess = require_session(request)
    t = db.query(ForumThread).filter(ForumThread.id == thread_id).first()
    if not t: raise HTTPException(404, "Thread nicht gefunden.")
    is_mod = sess.get("role") in ("moderator", "admin")
    if not is_mod and t.author_user_id != sess.get("user_id"):
        raise HTTPException(403, "Nur Threadstarter oder Moderator.")
    post = db.query(ForumPost).filter(ForumPost.id == post_id, ForumPost.thread_id == thread_id).first()
    if not post: raise HTTPException(404, "Post nicht gefunden.")
    t.solved_post_id = None if t.solved_post_id == post_id else post_id
    db.commit()
    return {"solved_post_id": t.solved_post_id}


# ─── Reactions ───────────────────────────────────────────────────────────────

VALID_REACTIONS = {"helpful", "aha", "question", "thanks"}


@router.post("/posts/{post_id}/react")
def toggle_reaction(post_id: str, kind: str, request: Request, db: Session = Depends(get_db)):
    user = _ensure_active_user(request, db)
    if kind not in VALID_REACTIONS:
        raise HTTPException(422, f"Reaktion muss {VALID_REACTIONS} sein.")
    post = db.query(ForumPost).filter(ForumPost.id == post_id, ForumPost.deleted_at.is_(None)).first()
    if not post:
        raise HTTPException(404, "Post nicht gefunden.")
    existing = db.query(ForumReaction).filter(
        ForumReaction.post_id == post_id,
        ForumReaction.user_id == user.id,
        ForumReaction.kind == kind,
    ).first()
    if existing:
        db.delete(existing)
        db.commit()
        return {"toggled": "off", "kind": kind}
    db.add(ForumReaction(post_id=post_id, user_id=user.id, kind=kind))
    db.commit()
    return {"toggled": "on", "kind": kind}


@router.patch("/posts/{post_id}")
def edit_post(post_id: str, body: CreatePost, request: Request, db: Session = Depends(get_db)):
    user = _ensure_active_user(request, db)
    post = db.query(ForumPost).filter(ForumPost.id == post_id, ForumPost.deleted_at.is_(None)).first()
    if not post: raise HTTPException(404, "Post nicht gefunden.")
    is_mod = (user.role in ("moderator", "admin"))
    if post.author_user_id != user.id and not is_mod:
        raise HTTPException(403, "Nicht erlaubt.")
    post.body_md = body.body_md.strip()
    post.updated_at = datetime.utcnow()
    post.edit_count = (post.edit_count or 0) + 1
    db.commit()
    return {"status": "ok"}


@router.delete("/posts/{post_id}")
def delete_post(post_id: str, request: Request, db: Session = Depends(get_db)):
    user = _ensure_active_user(request, db)
    post = db.query(ForumPost).filter(ForumPost.id == post_id, ForumPost.deleted_at.is_(None)).first()
    if not post: raise HTTPException(404, "Post nicht gefunden.")
    is_mod = (user.role in ("moderator", "admin"))
    if post.author_user_id != user.id and not is_mod:
        raise HTTPException(403, "Nicht erlaubt.")
    post.deleted_at = datetime.utcnow()
    # post_count am Thread anpassen
    thread = db.query(ForumThread).filter(ForumThread.id == post.thread_id).first()
    if thread:
        thread.post_count = max(0, (thread.post_count or 1) - 1)
    db.commit()
    return {"status": "deleted"}
