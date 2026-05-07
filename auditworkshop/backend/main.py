"""
flowworkshop · main.py
FastAPI-Anwendung — Startup, CORS, Router-Registrierung.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import engine, Base
from services.knowledge_service import init_db
from services.ollama_service import check_ollama, warmup_gateway_model
from routers import workshop, knowledge, system
from routers import projects, checklists, assessment, demo_data, dataframes, beneficiaries, reference_data, event, documents, auth, sanctions, forum, automation

# Modelle importieren damit Base.metadata sie kennt
import models  # noqa: F401

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ────────────────────────────────────────────
    log.info("flowworkshop startet …")

    # SQLAlchemy-Tabellen erstellen (workshop_*)
    try:
        Base.metadata.create_all(bind=engine)
        log.info("SQLAlchemy-Tabellen erstellt/geprueft.")
        # Uebergangsweise: fehlende Spalten fuer bestehende Workshop-DBs nachziehen.
        from sqlalchemy import text, inspect
        with engine.connect() as conn:
            inspector = inspect(engine)
            cols = [c["name"] for c in inspector.get_columns("workshop_agenda_items")]
            if "page_url" not in cols:
                conn.execute(text("ALTER TABLE workshop_agenda_items ADD COLUMN page_url VARCHAR(500)"))
                conn.commit()
                log.info("Spalte page_url zu workshop_agenda_items hinzugefuegt.")
            meta_cols = [c["name"] for c in inspector.get_columns("workshop_meta")]
            meta_migrations = {
                "phase": "ALTER TABLE workshop_meta ADD COLUMN phase VARCHAR(8) NOT NULL DEFAULT 'live'",
                "archive_started_at": "ALTER TABLE workshop_meta ADD COLUMN archive_started_at TIMESTAMP",
            }
            for col, ddl in meta_migrations.items():
                if col not in meta_cols:
                    conn.execute(text(ddl))
                    conn.commit()
                    log.info("Spalte %s zu workshop_meta hinzugefuegt.", col)
            reg_cols = [c["name"] for c in inspector.get_columns("workshop_registrations")]
            registration_migrations = {
                "password_hash": "ALTER TABLE workshop_registrations ADD COLUMN password_hash VARCHAR(255)",
                "password_updated_at": "ALTER TABLE workshop_registrations ADD COLUMN password_updated_at TIMESTAMP",
                "last_login_at": "ALTER TABLE workshop_registrations ADD COLUMN last_login_at TIMESTAMP",
                "qr_login_secret": "ALTER TABLE workshop_registrations ADD COLUMN qr_login_secret VARCHAR(128)",
                "qr_secret_rotated_at": "ALTER TABLE workshop_registrations ADD COLUMN qr_secret_rotated_at TIMESTAMP",
                # Phase-0-Erweiterung (Plan v3.2)
                "role": "ALTER TABLE workshop_registrations ADD COLUMN role VARCHAR(16) NOT NULL DEFAULT 'attendee'",
                "status": "ALTER TABLE workshop_registrations ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'active'",
                "bundesland": "ALTER TABLE workshop_registrations ADD COLUMN bundesland VARCHAR(64)",
                "function_role": "ALTER TABLE workshop_registrations ADD COLUMN function_role VARCHAR(80)",
                "signup_reason": "ALTER TABLE workshop_registrations ADD COLUMN signup_reason TEXT",
                "avatar_path": "ALTER TABLE workshop_registrations ADD COLUMN avatar_path VARCHAR(255)",
                "quota_bytes": "ALTER TABLE workshop_registrations ADD COLUMN quota_bytes BIGINT NOT NULL DEFAULT 209715200",
                "used_bytes": "ALTER TABLE workshop_registrations ADD COLUMN used_bytes BIGINT NOT NULL DEFAULT 0",
                "rejection_reason": "ALTER TABLE workshop_registrations ADD COLUMN rejection_reason TEXT",
                "approved_at": "ALTER TABLE workshop_registrations ADD COLUMN approved_at TIMESTAMP",
                "approved_by_id": "ALTER TABLE workshop_registrations ADD COLUMN approved_by_id VARCHAR(36)",
                "deleted_at": "ALTER TABLE workshop_registrations ADD COLUMN deleted_at TIMESTAMP",
            }
            for col, ddl in registration_migrations.items():
                if col not in reg_cols:
                    conn.execute(text(ddl))
                    conn.commit()
                    log.info("Spalte %s zu workshop_registrations hinzugefuegt.", col)

            # Spalte edit_count: Default-Backfill, falls Migration aus
            # früherem Run schon lief, aber server_default fehlte
            try:
                conn.execute(text("ALTER TABLE workshop_forum_posts ALTER COLUMN edit_count SET DEFAULT 0"))
                conn.execute(text("UPDATE workshop_forum_posts SET edit_count = 0 WHERE edit_count IS NULL"))
                conn.commit()
            except Exception:
                pass

            # Forum-Kategorien initial befüllen, wenn leer (Plan v3.2 §6)
            cat_count = conn.execute(text("SELECT COUNT(*) FROM workshop_forum_categories")).scalar()
            thread_count = conn.execute(text("SELECT COUNT(*) FROM workshop_forum_threads")).scalar()
            legacy_count = conn.execute(text("SELECT COUNT(*) FROM workshop_agenda_forum_posts")).scalar()
            need_migration = (thread_count == 0 and legacy_count > 0)
            if cat_count == 0:
                default_categories = [
                    ("allgemein", "Allgemein", "Themen ohne festen Programmpunkt", "MessagesSquare", "slate", 0),
                    ("workshop-2026", "Workshop 2026 (Live-Diskussionen)", "Beiträge der Veranstaltung im Mai 2026", "Calendar", "cyan", 10),
                    ("ki-pruefung", "KI in der Prüfung", "Erfahrungen, Use-Cases, offene Fragen", "Sparkles", "violet", 20),
                    ("methodik", "Methodik & Stichprobenprüfung", "MUS, SRS, Differenzenschätzung", "Calculator", "emerald", 30),
                    ("rechtsfragen", "Rechtsfragen", "VO, Förderrichtlinien, Auslegung", "Scale", "amber", 40),
                    ("plattform", "Plattform-Feedback", "Was funktioniert, was fehlt", "Wrench", "indigo", 50),
                ]
                for slug, name, desc, icon, color, sort in default_categories:
                    conn.execute(text(
                        "INSERT INTO workshop_forum_categories (id, slug, name, description, icon, color, sort_order, archived) "
                        "VALUES (gen_random_uuid()::text, :s, :n, :d, :i, :c, :o, false)"
                    ), {"s": slug, "n": name, "d": desc, "i": icon, "c": color, "o": sort})
                conn.commit()
                log.info("Forum: %d Default-Kategorien angelegt.", len(default_categories))
                need_migration = True

            if need_migration:
                # Migration: bestehende AgendaForumPost → forum_threads/forum_posts
                # in Kategorie 'workshop-2026', gruppiert nach agenda_item_id
                workshop_cat = conn.execute(text(
                    "SELECT id FROM workshop_forum_categories WHERE slug = 'workshop-2026'"
                )).scalar()
                if workshop_cat:
                    legacy_posts = conn.execute(text(
                        "SELECT p.id, p.agenda_item_id, p.title, p.body, "
                        "p.author_registration_id, p.author_name, p.author_organization, "
                        "p.created_at, a.title AS item_title "
                        "FROM workshop_agenda_forum_posts p "
                        "LEFT JOIN workshop_agenda_items a ON a.id = p.agenda_item_id "
                        "ORDER BY p.created_at ASC"
                    )).fetchall()
                    threads_by_item: dict = {}
                    for row in legacy_posts:
                        agenda_id = row.agenda_item_id
                        if agenda_id not in threads_by_item:
                            t_slug = "tag-" + agenda_id[:8]
                            t_title = row.item_title or "Workshop-Diskussion"
                            new_thread_id = conn.execute(text(
                                "INSERT INTO workshop_forum_threads "
                                "(id, slug, category_id, title, body_md, author_user_id, "
                                "author_name, author_organization, created_at, last_post_at, "
                                "post_count, view_count, pinned, locked, agenda_item_id) "
                                "VALUES (gen_random_uuid()::text, :s, :c, :t, :b, :u, :n, :o, :ts, :ts, 0, 0, false, false, :a) "
                                "RETURNING id"
                            ), {
                                "s": t_slug, "c": workshop_cat, "t": t_title,
                                "b": row.body or "", "u": row.author_registration_id,
                                "n": row.author_name, "o": row.author_organization,
                                "ts": row.created_at, "a": agenda_id,
                            }).scalar()
                            threads_by_item[agenda_id] = new_thread_id
                        thread_id = threads_by_item[agenda_id]
                        conn.execute(text(
                            "INSERT INTO workshop_forum_posts "
                            "(id, thread_id, author_user_id, author_name, author_organization, "
                            "body_md, created_at) "
                            "VALUES (gen_random_uuid()::text, :tid, :u, :n, :o, :b, :ts)"
                        ), {
                            "tid": thread_id, "u": row.author_registration_id,
                            "n": row.author_name, "o": row.author_organization,
                            "b": (row.title + "\n\n" + (row.body or "")) if row.title else (row.body or ""),
                            "ts": row.created_at,
                        })
                    # post_count + last_post_at je Thread aktualisieren
                    conn.execute(text("""
                        UPDATE workshop_forum_threads t
                           SET post_count = (SELECT COUNT(*) FROM workshop_forum_posts p WHERE p.thread_id = t.id),
                               last_post_at = COALESCE(
                                   (SELECT MAX(created_at) FROM workshop_forum_posts p WHERE p.thread_id = t.id),
                                   t.created_at
                               )
                    """))
                    conn.commit()
                    log.info(
                        "Forum-Migration: %d Threads aus %d AgendaForumPost erzeugt.",
                        len(threads_by_item), len(legacy_posts),
                    )

            # Initial-Admin: jan.riener@wirtschaft.hessen.de wird role=admin,
            # alle bestehenden mit Login werden status=active (= idempotent)
            conn.execute(text("""
                UPDATE workshop_registrations
                   SET role = 'admin', quota_bytes = 9223372036854775807
                 WHERE LOWER(email) = 'jan.riener@wirtschaft.hessen.de'
                   AND role <> 'admin'
            """))
            conn.commit()
            # bestehende Nutzer: status auf 'active' setzen wenn noch nicht
            conn.execute(text("""
                UPDATE workshop_registrations
                   SET approved_at = COALESCE(approved_at, created_at, now())
                 WHERE status = 'active' AND approved_at IS NULL
            """))
            conn.commit()
    except Exception as e:
        log.error("SQLAlchemy-Init fehlgeschlagen: %s", e)

    # pgvector-Tabelle initialisieren (knowledge_chunks)
    try:
        init_db()
        log.info("pgvector-Wissensdatenbank bereit.")
    except Exception as e:
        log.error("pgvector-Init fehlgeschlagen: %s", e)

    # Sanctions-Index in den Speicher laden
    try:
        from services.sanctions_service import warmup as sanctions_warmup
        sanctions_warmup()
    except Exception as e:
        log.warning("Sanctions-Warmup fehlgeschlagen: %s", e)

    # Ollama-Verbindung prüfen
    status = await check_ollama()
    if status["ok"]:
        log.info("Ollama erreichbar — Modelle: %s", status.get("models", []))
        await warmup_gateway_model()
    else:
        log.warning("Ollama nicht erreichbar: %s", status.get("error"))

    # Background-Scheduler für Auto-Harvest + Sanctions-Refresh (Plan v3.2 §16)
    import asyncio
    from services.scheduler import scheduler_loop
    scheduler_task = asyncio.create_task(scheduler_loop())

    yield
    # ── Shutdown ───────────────────────────────────────────
    scheduler_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass
    log.info("flowworkshop beendet.")


app = FastAPI(
    title="FlowWorkshop",
    description="KI-Workshop-Demo für EFRE-Prüfbehörden",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3004",
        "http://localhost:5173",
        "https://workshop.flowaudit.de",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Bestehende Router
app.include_router(workshop.router)
app.include_router(knowledge.router)
app.include_router(system.router)

# Neue CRUD + Assessment Router
app.include_router(projects.router)
app.include_router(checklists.router)
app.include_router(assessment.router)
app.include_router(demo_data.router)
app.include_router(dataframes.router)
app.include_router(beneficiaries.router)
app.include_router(reference_data.router)
app.include_router(event.router)
app.include_router(documents.router)
app.include_router(auth.router)
app.include_router(sanctions.router)
app.include_router(forum.router)
app.include_router(automation.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "flowworkshop"}
