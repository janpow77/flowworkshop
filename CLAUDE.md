# Workshop

Standalone-Webanwendung **Auditworkshop** für den Workshop „KI und LLMs in der EFRE-Prüfbehörde". Demonstriert praxisnahe Szenarien, in denen ein lokal/zentral betriebenes LLM Prüfer bei der Verwaltungskontrolle (VerwK, Art. 74 VO 2021/1060) EFRE-geförderter Vorhaben unterstützt. Die Anwendung liegt im Unterverzeichnis `auditworkshop/`.

## Tech-Stack
- **Backend:** FastAPI (Python 3.12), SQLAlchemy 2.0 (`declarative_base()`), uvicorn — Container-Port 8000
- **Frontend:** React 19, TypeScript 5.9, Tailwind CSS 4 (`@tailwindcss/vite`, keine config.js), Vite — nginx-Container Port 80
- **Datenbank:** PostgreSQL 16 + pgvector, Schema-Verwaltung via **Alembic**
- **LLM:** `LLM_BACKEND=egpu-manager` → zentraler **ai-router-Gateway** (`:7849`, OpenAI-`/v1`); Default-Modell `qwen3:14b`. Lokales Ollama (`:11434`) nur als alternatives Backend (`LLM_BACKEND=ollama`)
- **Embeddings:** `bge-m3`, **1024 Dim.** über den Gateway (`EMBEDDING_BACKEND=gateway`); `mpnet/768` nur im lokalen Fallback
- **Knowledge/RAG:** lokal `pgvector` (IVFFlat-Index) plus zentrale audit_designer-RAG über `router_knowledge_service` (`AI_ROUTER_URL`)
- **Karten:** Leaflet + react-leaflet · **Icons:** lucide-react
- **Deployment:** Docker Compose (NUC-Dev: db, backend, frontend, cloudflared); Hetzner-Prod über `compose.yaml` + ghcr.io-Images

### Ports (NUC-Dev, docker-compose.yml)
| Service | Intern | Extern |
|---|---|---|
| PostgreSQL | 5432 | 5434 |
| Backend (FastAPI) | 8000 | 8006 |
| Frontend (nginx) | 80 | 3004 |
| ai-router-Gateway (Host) | 7849 | — |

## Befehle
Alle Befehle relativ zu `auditworkshop/`.

```bash
# Docker-Stack (NUC-Dev)
docker compose up -d
docker compose logs -f backend
docker exec auditworkshop-backend python scripts/ingest_knowledge.py --all   # Verordnungen einlesen (einmalig)
curl -X POST http://localhost:8006/api/demo/seed                              # Demo-Daten laden

# Smoke-Test (9 HTTP-Checks; einer prüft bewusst 401 ⇒ Auth-Gate aktiv)
bash scripts/workshop_smoke.sh
BACKEND_BASE=http://localhost:8006 FRONTEND_BASE=http://localhost:3004 bash scripts/workshop_smoke.sh

# Backend-Tests (27 test_*.py, pytest + conftest.py)
cd backend && pytest

# Frontend
cd frontend
npm run lint          # ESLint 9 Flat Config
npm run build         # tsc -b && vite build
npm run dev
npm test              # vitest run
npm run test:e2e      # playwright (e2e/*.spec.ts)
```

Manuelle Backend-Checks: `curl http://localhost:8006/health`, Swagger unter `http://localhost:8006/docs`, Ollama/Gateway-Status `…/api/system/profile`.

## Architektur
```
Workshop/
├── CLAUDE.md                  # Diese Datei (Repo-Root)
├── auditworkshop/             # Hauptanwendung — siehe @auditworkshop/CLAUDE.md (Hetzner-Prod, Lifecycle, Szenarien)
│   ├── docker-compose.yml     # NUC-Dev-Stack (4 Services inkl. cloudflared)
│   ├── compose.yaml           # Hetzner-CCX23-Prod (ghcr.io-Images)
│   ├── backend/
│   │   ├── config.py          # ALLE System-Prompts (SYSTEM_PROMPTS), Env-Vars, LLM-/Embedding-Konstanten
│   │   ├── database.py        # SQLAlchemy-Engine (pool_pre_ping); koexistiert mit raw-psycopg2 für pgvector
│   │   ├── entrypoint.sh      # läuft `alembic upgrade head` vor dem App-Start
│   │   ├── routers/           # 31 FastAPI-Router, Prefix /api/{resource}: workshop (Szenarien 1-6), knowledge,
│   │   │                      #   auth, state_aid, sanctions, entities, checklist_* , forum, …
│   │   ├── services/          # 30 Services: ollama_service, router_knowledge_service, knowledge_service,
│   │   │                      #   pdf_parser, geocoding_service, state_aid_*, entity_resolution, harvester …
│   │   ├── models/ schemas/   # SQLAlchemy-Modelle bzw. Pydantic-Schemas
│   │   └── scripts/           # ingest_knowledge.py, workshop_reset.py, …
│   ├── frontend/src/          # 36 Pages (pages/), Komponenten (components/layout|workshop|checklist)
│   └── scripts/               # workshop_smoke.sh, state_aid_smoke.sh, *_hetzner_*.sh
```

## Konventionen
- Backend: synchrone SQLAlchemy-Sessions (kein `async def` für DB-Zugriffe); alle Env-Vars und System-Prompts zentral in `config.py`
- LLM-Antworten via **Server-Sent-Events** (kein WebSocket)
- Zwei DB-Zugriffsmuster koexistieren bewusst: SQLAlchemy (Checklisten/Projekte) und raw-psycopg2 (pgvector/knowledge)
- Frontend: funktionale Komponenten + Hooks, kein State-Management-Lib (useState/useEffect); Auth-Gate in `App.tsx` (öffentliche Routen Agenda/Register vs. geschützte)
- Deutsche Kommentare/Docstrings, echte Umlaute
- **Auth ist echt**, nicht nur ein Token-Login: PBKDF2-Hashing, Server-Sessions, QR-Login-Token (HMAC) und Worker-Token in `routers/auth.py`. Geschützte Endpunkte liefern ohne `Authorization: Bearer …` ein 401
- DSGVO: alle Daten lokal verarbeitbar, kein Cloud-LLM-Zwang (Gateway läuft auf eigener Infrastruktur)
- `WORKSHOP_ADMIN=true` schaltet Ingest-Endpunkte frei

## Verbotene Operationen
- Keine destruktiven DB-Operationen ohne Bestätigung (DROP/TRUNCATE, DELETE ohne WHERE)
- System-Prompts in `config.py` nicht ohne Absprache ändern — für den Workshop abgestimmt
- pgvector-IVFFlat-Index nicht entfernen
- `geocode_cache.json` nicht löschen (3.177 gecachte Standorte); Nominatim erlaubt nur 1 Req/s
- Demo-Dokumente nicht mit echten personenbezogenen Daten befüllen
- `WORKSHOP_ADMIN` während des Workshops nicht auf false setzen
- Keine git-Force-Operationen, kein Überschreiben von `.env`

## Bekannte Fallstricke
- **CORS:** `main.py` erlaubt nur `localhost:3000/3004/5173` — bei Portwechsel anpassen
- **Frontend wird in Docker als statische nginx-Dateien ausgeliefert** — Frontend-Änderungen erfordern Docker-Rebuild
- **Thunderbolt-4-eGPU** (NUC): ~2 Min. Init nach Kaltstart; qwen3:14b Q8 belegt ~15 GB VRAM der RTX 5070 Ti
- **ai-router-Auth:** Workshop sendet `X-App-Id: auditworkshop` mit jedem Gateway-Call; `X-Api-Key` wird **nur** angehängt, wenn `AI_ROUTER_API_KEY` gesetzt ist (Helper `config.gateway_headers`). Der Router erzwingt aktuell keinen Key — der Live-Betrieb läuft mit reinem `X-App-Id`.

Detaillierte Szenarien-Übersicht, Hetzner-CCX23-Prod-Betrieb, Lifecycle-Skripte und Architektur-Entscheidungen: siehe @auditworkshop/CLAUDE.md, `auditworkshop/PROJEKTBESCHREIBUNG.md` und `auditworkshop/SZENARIEN_UEBERSICHT.md`.
