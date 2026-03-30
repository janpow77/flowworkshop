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
from routers import projects, checklists, assessment, demo_data, dataframes, beneficiaries, reference_data, event, documents, auth

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
        # Spalten-Migration: page_url fuer Agenda-Items (fuer bestehende DBs)
        from sqlalchemy import text, inspect
        with engine.connect() as conn:
            inspector = inspect(engine)
            cols = [c["name"] for c in inspector.get_columns("workshop_agenda_items")]
            if "page_url" not in cols:
                conn.execute(text("ALTER TABLE workshop_agenda_items ADD COLUMN page_url VARCHAR(500)"))
                conn.commit()
                log.info("Spalte page_url zu workshop_agenda_items hinzugefuegt.")
    except Exception as e:
        log.error("SQLAlchemy-Init fehlgeschlagen: %s", e)

    # pgvector-Tabelle initialisieren (knowledge_chunks)
    try:
        init_db()
        log.info("pgvector-Wissensdatenbank bereit.")
    except Exception as e:
        log.error("pgvector-Init fehlgeschlagen: %s", e)

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


@app.get("/health")
def health():
    return {"status": "ok", "service": "flowworkshop"}
