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
from routers import projects, checklists, assessment, demo_data, dataframes, beneficiaries, reference_data, event, documents, auth, sanctions

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

    yield
    # ── Shutdown ───────────────────────────────────────────
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


@app.get("/health")
def health():
    return {"status": "ok", "service": "flowworkshop"}
