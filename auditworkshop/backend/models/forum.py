"""
flowworkshop · models/forum.py
Forum-Datenmodell (Plan v3.2 §6) — Discourse-/CIRCABC-Stil.

Bestehende AgendaForumPost (forum_per_agenda_item) bleibt als Migrations-
Quelle und wird in eine Default-Kategorie überführt.
"""
from sqlalchemy import (
    Column, String, Text, Integer, Boolean, DateTime, ForeignKey,
    BigInteger, JSON, UniqueConstraint, Index, func,
)
import uuid

from database import Base


class ForumCategory(Base):
    __tablename__ = "workshop_forum_categories"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    slug = Column(String(80), unique=True, nullable=False, index=True)
    name = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)
    icon = Column(String(40), nullable=True)        # Lucide icon name
    color = Column(String(40), nullable=True)        # Tailwind color (cyan, rose, …)
    sort_order = Column(Integer, default=0, nullable=False)
    archived = Column(Boolean, default=False, nullable=False)
    parent_id = Column(String(36), nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class ForumThread(Base):
    __tablename__ = "workshop_forum_threads"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    slug = Column(String(120), nullable=False)
    category_id = Column(
        String(36),
        ForeignKey("workshop_forum_categories.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    title = Column(String(200), nullable=False)
    body_md = Column(Text, nullable=False, server_default="")
    author_user_id = Column(String(36), nullable=True, index=True)  # NULL bei Migration
    author_name = Column(String(160), nullable=True)
    author_organization = Column(String(255), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    last_post_at = Column(DateTime, server_default=func.now(), index=True)
    post_count = Column(Integer, default=1, nullable=False)
    view_count = Column(Integer, default=0, nullable=False)
    pinned = Column(Boolean, default=False, nullable=False)
    locked = Column(Boolean, default=False, nullable=False)
    solved_post_id = Column(String(36), nullable=True)  # FK auf forum_posts (lazy)
    # Optional: Bezug auf ein Tagesordnungs-Item (Migration-Quelle)
    agenda_item_id = Column(String(36), nullable=True, index=True)

    __table_args__ = (
        Index("ix_forum_threads_category_lastpost", "category_id", "last_post_at"),
    )


class ForumPost(Base):
    __tablename__ = "workshop_forum_posts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    thread_id = Column(
        String(36),
        ForeignKey("workshop_forum_threads.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    parent_post_id = Column(String(36), nullable=True)  # für Quote/Reply
    author_user_id = Column(String(36), nullable=True, index=True)
    author_name = Column(String(160), nullable=True)
    author_organization = Column(String(255), nullable=True)
    body_md = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), index=True)
    updated_at = Column(DateTime, nullable=True)
    edit_count = Column(Integer, server_default="0", nullable=False)
    deleted_at = Column(DateTime, nullable=True)


class ForumReaction(Base):
    __tablename__ = "workshop_forum_reactions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    post_id = Column(
        String(36),
        ForeignKey("workshop_forum_posts.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id = Column(String(36), nullable=False, index=True)
    kind = Column(String(20), nullable=False)  # 'helpful' | 'aha' | 'question' | 'thanks'
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("post_id", "user_id", "kind", name="uq_reaction_post_user_kind"),
    )


class ForumTag(Base):
    __tablename__ = "workshop_forum_tags"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    slug = Column(String(60), unique=True, nullable=False, index=True)
    name = Column(String(80), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class ForumThreadTag(Base):
    __tablename__ = "workshop_forum_thread_tags"

    thread_id = Column(
        String(36),
        ForeignKey("workshop_forum_threads.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id = Column(
        String(36),
        ForeignKey("workshop_forum_tags.id", ondelete="CASCADE"),
        primary_key=True,
    )


class ForumReadState(Base):
    __tablename__ = "workshop_forum_read_state"

    user_id = Column(String(36), primary_key=True)
    thread_id = Column(
        String(36),
        ForeignKey("workshop_forum_threads.id", ondelete="CASCADE"),
        primary_key=True,
    )
    last_read_post_id = Column(String(36), nullable=True)
    last_read_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
