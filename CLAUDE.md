# Workshop — CLAUDE.md

## Projektbeschreibung

**FlowWorkshop / Auditworkshop** ist eine standalone Webanwendung für den Workshop „KI und LLMs in der EFRE-Prüfbehörde". Sie demonstriert sechs praxisnahe Szenarien, in denen ein lokal betriebenes LLM (Qwen3-14B via Ollama) Prüfer bei der Verwaltungskontrolle von EFRE-geförderten Vorhaben unterstützt.

### Stack

| Komponente | Technologie |
|------------|-------------|
| Backend | FastAPI (Python 3.12), SQLAlchemy 2.0, uvicorn |
| Frontend | React 19, TypeScript 5.9, Tailwind CSS 4, Vite 8 |
| Datenbank | PostgreSQL 16 + pgvector |
| LLM | Ollama auf dem Host (qwen3:14b), Fallback: qwen3:8b |
| Embeddings | paraphrase-multilingual-mpnet-base-v2 (768 Dim., CPU) |
| Deployment | Docker Compose (3 Container: db, backend, frontend) |
| Karten | Leaflet + react-leaflet |
| Icons | lucide-react |

### Ports

| Service | Intern | Extern (docker-compose) |
|---------|--------|-------------------------|
| PostgreSQL | 5432 | 5434 |
| Backend (FastAPI) | 8000 | 8006 |
| Frontend (nginx) | 80 | 3004 |
| Ollama (Host) | 11434 | — |

## Architekturübersicht

```
Workshop/
├── CLAUDE.md                                  # Diese Datei
├── docs/agents.md                             # Subagenten-Dokumentation
├── projektbeschreibung-anmeldung-tagesordnung.md  # Teilbereich Anmeldung/Agenda
├── workshop_demo_komplett.md                  # Vollständige Workshop-Demo-Beschreibung
└── auditworkshop/                             # Hauptanwendung
    ├── CLAUDE.md                              # Projektspezifische CLAUDE.md
    ├── PROJEKTBESCHREIBUNG.md                 # Detaillierte Projektbeschreibung
    ├── README.md                              # Quickstart-Anleitung
    ├── docker-compose.yml                     # 3-Container-Stack
    ├── scripts/
    │   └── workshop_smoke.sh                  # Smoke-Tests (8 HTTP-Checks)
    ├── backend/
    │   ├── main.py                            # FastAPI App, Lifespan, Router-Registrierung
    │   ├── config.py                          # ALLE System-Prompts, Env-Vars, Konstanten
    │   ├── database.py                        # SQLAlchemy Engine, Session, Base
    │   ├── Dockerfile                         # Python 3.12-slim + Tesseract + poppler
    │   ├── requirements.txt                   # Python-Abhängigkeiten
    │   ├── models/                            # SQLAlchemy-Modelle
    │   │   ├── project.py                     # WorkshopProject
    │   │   ├── checklist.py                   # WorkshopChecklist, WorkshopQuestion, WorkshopEvidence
    │   │   ├── document.py                    # Dokument-Modell
    │   │   ├── registration.py                # Teilnehmer-Registrierung
    │   │   └── audit_log.py                   # Audit-Log
    │   ├── routers/                           # FastAPI-Router (API-Endpunkte)
    │   │   ├── workshop.py                    # Szenarien 1-6, SSE-Streaming
    │   │   ├── knowledge.py                   # pgvector RAG: Ingest, Suche, Fragen
    │   │   ├── system.py                      # Ollama-Status, GPU-Metriken, System-Info
    │   │   ├── projects.py                    # Projekt-CRUD
    │   │   ├── checklists.py                  # Checklisten-CRUD
    │   │   ├── assessment.py                  # KI-Bewertung (Accept/Reject/Edit)
    │   │   ├── beneficiaries.py               # Begünstigtenverzeichnis + Geocoding
    │   │   ├── dataframes.py                  # XLSX → SQL-Tabellen
    │   │   ├── demo_data.py                   # Seed/Reset Demo-Daten
    │   │   ├── documents.py                   # Dokument-Upload
    │   │   ├── reference_data.py              # Referenzdaten-API
    │   │   ├── event.py                       # Event/Agenda-Verwaltung
    │   │   └── auth.py                        # Login (Token-basiert)
    │   ├── schemas/                           # Pydantic-Schemas
    │   │   ├── project.py
    │   │   └── checklist.py
    │   ├── services/                          # Business-Logik
    │   │   ├── ollama_service.py              # LLM-Streaming via httpx
    │   │   ├── knowledge_service.py           # pgvector RAG-Pipeline
    │   │   ├── pdf_parser.py                  # PDF-Parsing (PyMuPDF + pdfplumber + OCR)
    │   │   ├── file_parser.py                 # Multi-Format-Parser (PDF/XLSX/DOCX/HTML/RTF/TXT)
    │   │   ├── dataframe_service.py           # XLSX → PostgreSQL-Tabelle
    │   │   └── geocoding_service.py           # Nominatim-Geocoding mit Cache
    │   ├── scripts/                           # CLI-Skripte
    │   │   ├── ingest_knowledge.py            # Verordnungen in pgvector einlesen
    │   │   ├── ingest_all.py                  # Wissensdatenbank + Demo-Daten
    │   │   └── workshop_reset.py              # Workshop-Daten zurücksetzen
    │   └── data/                              # Demo-Dateien + Caches
    │       ├── transparenzliste_hessen.xlsx
    │       ├── transparenzliste_esf_hessen.xlsx
    │       ├── transparenzliste_jtf.xlsx
    │       ├── beguenstigten_analyse.xlsx
    │       └── geocode_cache.json             # Persistenter Geocoding-Cache
    └── frontend/
        ├── Dockerfile                         # Multi-Stage: node:20 Build → nginx:alpine
        ├── package.json                       # React 19, Vite 8, Tailwind 4
        ├── vite.config.ts                     # Dev-Proxy /api → localhost:8000
        ├── nginx.conf                         # Produktions-Reverse-Proxy
        ├── tsconfig.json
        ├── eslint.config.js                   # ESLint 9 Flat Config
        ├── index.html
        └── src/
            ├── main.tsx                       # React-Einstiegspunkt
            ├── App.tsx                        # Routing (BrowserRouter, Auth-Gate)
            ├── index.css                      # Tailwind-Imports
            ├── pages/                         # Seiten-Komponenten
            │   ├── HomePage.tsx               # Dashboard + PipelineWidget
            │   ├── ScenarioPage.tsx           # Szenarien 1-6
            │   ├── ProjectsPage.tsx           # Projektübersicht
            │   ├── ProjectDetailPage.tsx      # Einzelprojekt
            │   ├── ChecklistPage.tsx          # Checklisten-Editor
            │   ├── KnowledgePage.tsx          # Wissensdatenbank-UI
            │   ├── DataFramePage.tsx          # SQL-Abfrage-Interface
            │   ├── CompanySearchPage.tsx      # Firmensuche
            │   ├── AiActPage.tsx              # KI-Verordnung
            │   ├── AgendaPage.tsx             # Tagesordnung (öffentlich)
            │   ├── RegisterPage.tsx           # Teilnehmer-Anmeldung
            │   ├── AdminPage.tsx              # Admin-Bereich
            │   ├── LoginPage.tsx              # Login
            │   └── NotFoundPage.tsx           # 404
            └── components/
                ├── layout/                    # Layout-Komponenten
                │   ├── AppShell.tsx            # Sidebar + TopBar + Outlet
                │   ├── Sidebar.tsx             # Navigation (264px)
                │   ├── TopBar.tsx              # Ollama-Status + Dark-Mode-Toggle
                │   ├── MobileNav.tsx           # Mobile Navigation
                │   ├── Breadcrumb.tsx
                │   ├── CommandPalette.tsx      # Cmd+K Suche
                │   ├── EuLoader.tsx            # Lade-Animation
                │   ├── PresenterToolbar.tsx    # Präsentationsmodus
                │   └── SprechzettelPanel.tsx   # Moderationsnotizen
                ├── workshop/                  # Workshop-spezifische Komponenten
                │   ├── PipelineWidget.tsx      # KI-Pipeline (GPU-Stats, animiert)
                │   ├── LlmResponsePanel.tsx    # SSE-Streaming-Anzeige
                │   ├── DocumentDropzone.tsx    # Datei-Upload (Drag & Drop)
                │   ├── BeneficiaryMap.tsx      # Leaflet-Karte (Szenario 6)
                │   └── ScenarioCard.tsx        # Szenario-Vorschaukarte
                └── checklist/                 # Checklisten-Komponenten
                    ├── AiRemarkCard.tsx        # KI-Bemerkung (Accept/Reject/Edit)
                    ├── EvidenceCard.tsx         # Beleg-Anzeige
                    └── StatusBadge.tsx          # Status-Badge (draft/accepted/rejected/edited)
```

## Entwicklungsregeln

### Backend (Python / FastAPI)

- Python 3.12, kein `async def` für DB-Zugriffe (synchrone SQLAlchemy-Sessions)
- SQLAlchemy 2.0 mit `declarative_base()` (nicht mapped_column-Stil)
- Pydantic-Schemas in `schemas/`, SQLAlchemy-Modelle in `models/`
- Router-Prefix-Konvention: `/api/{resource}` (z.B. `/api/projects/`, `/api/knowledge/`)
- Umgebungsvariablen in `config.py` zentralisiert, nicht in einzelnen Dateien
- System-Prompts zentral in `config.py` Dikt `SYSTEM_PROMPTS`
- Logging via `logging` Modul, Format: `%(levelname)s  %(name)s  %(message)s`
- SSE-Streaming für LLM-Antworten (kein WebSocket)
- Ruff als Linter (`.ruff_cache/` vorhanden)
- `pool_pre_ping=True` für DB-Verbindungen

### Frontend (React / TypeScript)

- React 19 mit funktionalen Komponenten und Hooks
- TypeScript strict mode
- Tailwind CSS 4 (via `@tailwindcss/vite` Plugin, keine tailwind.config.js)
- Vite 8 als Bundler
- ESLint 9 Flat Config
- Dark Mode via Tailwind `dark:` Klassen + System-Preference-Detection
- Routing: `react-router-dom` v7 mit `BrowserRouter`
- Auth-Gate in `App.tsx`: öffentliche Routen (Agenda, Register) vs. geschützte Routen
- Keine State-Management-Bibliothek (useState/useEffect)
- Icons: `lucide-react`
- Kein Test-Framework konfiguriert

### Allgemein

- Deutsche Kommentare und Docstrings
- Kein Auth-System für die Hauptanwendung (lokale Demo), nur einfacher Token-Login
- DSGVO-konform: alle Daten lokal, kein Cloud-LLM
- `WORKSHOP_ADMIN=true` schaltet Ingest-Endpunkte frei

## VERBOTENE OPERATIONEN

- **Keine destruktiven Datenbankoperationen** ohne explizite Bestätigung (DROP TABLE, TRUNCATE, DELETE ohne WHERE)
- **Keine Löschung von Dateien** außerhalb von `/tmp`
- **Kein Überschreiben von `.env`-Dateien**
- **Keine git-Operationen ohne Bestätigung** — kein `force-push`, kein `reset --hard`, kein `checkout .`
- **Keine Installation von System-Paketen** ohne Rückfrage (`apt install`, `pip install` auf Systemebene)
- **System-Prompts in `config.py` nicht ohne Absprache verändern** — diese sind für den Workshop abgestimmt
- **Demo-Dokumente nicht mit echten personenbezogenen Daten befüllen**
- **WORKSHOP_ADMIN nicht auf false setzen** während des Workshops
- **pgvector IVFFlat-Index nicht entfernen**
- **Geocoding-Cache (`geocode_cache.json`) nicht löschen** — enthält 5.200+ gecachte Standorte

## Pflichtverhalten

- **Vor jeder Änderung an Produktionsdateien:** kurze Zusammenfassung was geändert wird und warum
- **Bei unklaren Anforderungen:** nachfragen statt annehmen
- **Vor Änderungen an `config.py`:** explizit bestätigen lassen, da System-Prompts Workshop-kritisch sind
- **Vor Docker-Operationen:** prüfen ob Container laufen (`docker ps`)
- **Nach Backend-Änderungen:** Smoke-Test empfehlen (`scripts/workshop_smoke.sh`)

## Testanweisungen

### Smoke-Tests (HTTP-Endpunkt-Checks)

```bash
# Smoke-Test-Skript (prüft 8 Endpunkte)
bash auditworkshop/scripts/workshop_smoke.sh

# Oder mit benutzerdefinierten URLs:
BACKEND_BASE=http://localhost:8006 FRONTEND_BASE=http://localhost:3004 \
  bash auditworkshop/scripts/workshop_smoke.sh
```

### Backend manuell testen

```bash
# Health-Check
curl http://localhost:8006/health

# Swagger-UI
open http://localhost:8006/docs

# Wissensdatenbank-Status
curl http://localhost:8006/api/knowledge/stats

# Ollama-Verbindung
curl http://localhost:8006/api/system/ollama

# GPU-Metriken
curl http://localhost:8006/api/system/gpu
```

### Frontend

```bash
cd auditworkshop/frontend

# Lint
npm run lint

# TypeScript-Check
npx tsc -b

# Build (Produktions-Build)
npm run build

# Dev-Server
npm run dev
```

### Docker-Stack

```bash
cd auditworkshop

# Stack starten
docker compose up -d

# Logs prüfen
docker compose logs -f backend

# Wissensdatenbank einlesen (einmalig)
docker exec auditworkshop-backend python scripts/ingest_knowledge.py --all

# Demo-Daten laden
curl -X POST http://localhost:8006/api/demo/seed
```

### Automatisierte Tests

Es gibt derzeit **keine E2E-Tests und keine Unit-Tests**. Dies ist als offener Punkt dokumentiert.

## Bekannte Fallstricke

### Hardware / Infrastruktur
- **Thunderbolt 4 eGPU:** Braucht ~2 Min. zum Initialisieren nach Kaltstart
- **VRAM-Limit:** Qwen3-14B Q8 belegt ~15 GB der 16 GB RTX 5070 Ti
- **Nominatim-API:** Max 1 Request/s für Geocoding (Szenario 6), daher Cache-Nutzung zwingend

### Architektur
- **Zwei DB-Zugriffsmuster koexistieren:** SQLAlchemy (für Checklisten/Projekte) und raw psycopg2 (für pgvector/knowledge). Siehe Kommentar in `database.py`
- **CORS-Origins:** Nur `localhost:3000` und `localhost:5173` erlaubt — bei Portwechsel anpassen in `main.py`
- **Docker-Ports weichen von README ab:** README sagt Port 3000/8000, docker-compose mapped auf 3004/8006 — bei externem Zugriff die docker-compose-Ports verwenden
- **Frontend-Build wird in Docker als statische Dateien via nginx ausgeliefert** — Änderungen am Frontend erfordern Docker-Rebuild

### Offene Punkte (aus PROJEKTBESCHREIBUNG.md)
- Projekt bearbeiten: nur API vorhanden, kein Frontend-UI
- E2E-Tests: keine vorhanden
- Checklisten-Export (PDF/CSV): nicht implementiert
