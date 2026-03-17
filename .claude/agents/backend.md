---
name: backend
description: "Automatisch aktiv bei Aenderungen an FastAPI-Backend: Routes, Models, Schemas, Services, Config. Triggert bei Python-Dateien in auditworkshop/backend/, bei 'router', 'endpoint', 'model', 'schema', 'service', 'API' im Kontext."
tools:
  - Read
  - Write
  - Edit
  - Bash
  - Grep
  - Glob
---

# Backend Agent — FastAPI / Python

## Fokus-Verzeichnisse
- `auditworkshop/backend/routers/` — API-Endpunkte (FastAPI Router)
- `auditworkshop/backend/models/` — SQLAlchemy-Modelle
- `auditworkshop/backend/schemas/` — Pydantic-Schemas
- `auditworkshop/backend/services/` — Business-Logik
- `auditworkshop/backend/database.py` — Engine, Session
- `auditworkshop/backend/main.py` — App-Setup, Router-Registrierung

## Gesperrte Dateien (nur nach expliziter Freigabe)
- `auditworkshop/backend/config.py` — System-Prompts sind Workshop-kritisch
- `auditworkshop/backend/data/geocode_cache.json` — 5.200+ gecachte Standorte

## Regeln
- Python 3.12, synchrone SQLAlchemy-Sessions (kein `async def` fuer DB)
- SQLAlchemy 2.0 mit `declarative_base()` (nicht mapped_column-Stil)
- Router-Prefix: `/api/{resource}` (z.B. `/api/projects/`)
- Umgebungsvariablen NUR in `config.py` zentralisiert
- Deutsche Kommentare und Docstrings
- Logging: `logging` Modul, Format `%(levelname)s  %(name)s  %(message)s`
- SSE-Streaming fuer LLM-Antworten (kein WebSocket)
- Neue Router muessen in `main.py` registriert werden

## Standard-Checks nach Aenderungen
```bash
# Smoke-Test (8 Endpunkte)
BACKEND_BASE=http://localhost:8006 FRONTEND_BASE=http://localhost:3004 \
  bash auditworkshop/scripts/workshop_smoke.sh

# Einzelner Health-Check
curl -s http://localhost:8006/health | python3 -m json.tool

# Swagger pruefen
curl -s http://localhost:8006/openapi.json | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'{len(d[\"paths\"])} Endpunkte')"
```
