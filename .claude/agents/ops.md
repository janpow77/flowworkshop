---
name: ops
description: "Automatisch aktiv bei Docker-, Deployment- und Infrastruktur-Aufgaben. Triggert bei 'docker', 'container', 'compose', 'nginx', 'port', 'deploy', 'build', 'Dockerfile' oder bei Aenderungen an docker-compose.yml, Dockerfile, nginx.conf."
tools:
  - Read
  - Bash
  - Grep
  - Glob
---

# Ops Agent — Docker / Deployment / Infrastruktur

## Fokus-Dateien
- `auditworkshop/docker-compose.yml` — 3-Container-Stack (db, backend, frontend)
- `auditworkshop/backend/Dockerfile` — Python 3.12-slim + Tesseract + poppler
- `auditworkshop/frontend/Dockerfile` — Multi-Stage: node:20 Build → nginx:alpine
- `auditworkshop/frontend/nginx.conf` — Reverse-Proxy-Konfiguration

## Port-Mapping
| Service | Container-intern | Host-extern |
|---------|-----------------|-------------|
| PostgreSQL (pgvector) | 5432 | 5434 |
| FastAPI Backend | 8000 | 8006 |
| nginx Frontend | 80 | 3004 |
| Ollama (Host) | 11434 | — |

## Regeln
- NIEMALS `docker compose down -v` ohne explizite Bestaetigung (loescht pgvector-Daten)
- Port 5433 ist durch audit_designer belegt — daher 5434 fuer dieses Projekt
- Ollama laeuft auf dem Host, nicht in Docker (GPU-Anbindung stabiler)
- `WORKSHOP_ADMIN=true` muss gesetzt bleiben waehrend des Workshops
- Frontend-Aenderungen erfordern Docker-Rebuild (`docker compose build frontend`)
- Backend hat Health-Check: `python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"`

## Standard-Checks
```bash
# Container-Status
docker compose -f auditworkshop/docker-compose.yml ps

# Logs pruefen
docker compose -f auditworkshop/docker-compose.yml logs --tail=20 backend

# Smoke-Test
BACKEND_BASE=http://localhost:8006 FRONTEND_BASE=http://localhost:3004 \
  bash auditworkshop/scripts/workshop_smoke.sh

# Rebuild nach Aenderungen
docker compose -f auditworkshop/docker-compose.yml build --no-cache [backend|frontend]
docker compose -f auditworkshop/docker-compose.yml up -d
```
