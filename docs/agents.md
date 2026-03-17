# Workshop — Subagenten-Dokumentation

## Übersicht

Dieses Dokument beschreibt die empfohlenen Subagenten für die Entwicklung am Auditworkshop-Projekt, ihre Zuständigkeiten und Dateibereiche.

## Empfohlene Agenten

### 1. Test-Agent

**Zweck:** Smoke-Tests ausführen, HTTP-Endpunkte prüfen, TypeScript-Checks und Lint durchführen.

**Aufruf:**
```
subagent_type: test-runner
```

**Zuständige Dateien:**
- `auditworkshop/scripts/workshop_smoke.sh`
- `auditworkshop/frontend/eslint.config.js`
- `auditworkshop/frontend/tsconfig*.json`

**Typische Aufgaben:**
- `bash auditworkshop/scripts/workshop_smoke.sh` (8 HTTP-Checks)
- `cd auditworkshop/frontend && npm run lint`
- `cd auditworkshop/frontend && npx tsc -b`
- `curl http://localhost:8006/health`

---

### 2. Backend-Agent

**Zweck:** FastAPI-Router, Services, Models und Schemas bearbeiten. API-Endpunkte implementieren, Datenbank-Modelle erweitern.

**Aufruf:**
```
subagent_type: implementer
```

**Zuständige Dateien:**
- `auditworkshop/backend/routers/*.py`
- `auditworkshop/backend/models/*.py`
- `auditworkshop/backend/schemas/*.py`
- `auditworkshop/backend/services/*.py`
- `auditworkshop/backend/database.py`

**Gesperrte Dateien (nur nach expliziter Freigabe):**
- `auditworkshop/backend/config.py` — System-Prompts, Workshop-kritisch

---

### 3. Frontend-Agent

**Zweck:** React-Komponenten, Pages und Styling bearbeiten. Neue UI-Features implementieren.

**Aufruf:**
```
subagent_type: implementer
```

**Zuständige Dateien:**
- `auditworkshop/frontend/src/pages/*.tsx`
- `auditworkshop/frontend/src/components/**/*.tsx`
- `auditworkshop/frontend/src/App.tsx`
- `auditworkshop/frontend/src/index.css`
- `auditworkshop/frontend/src/main.tsx`

**Gesperrte Dateien:**
- `auditworkshop/frontend/package.json` — nur nach Absprache ändern
- `auditworkshop/frontend/vite.config.ts` — Build-Konfiguration

---

### 4. Docker / DevOps-Agent

**Zweck:** Docker-Compose-Konfiguration, Dockerfiles, nginx-Config, Container-Debugging.

**Aufruf:**
```
subagent_type: docker-health
```

**Zuständige Dateien:**
- `auditworkshop/docker-compose.yml`
- `auditworkshop/backend/Dockerfile`
- `auditworkshop/frontend/Dockerfile`
- `auditworkshop/frontend/nginx.conf`

---

### 5. Code-Review-Agent

**Zweck:** Code-Qualität prüfen, Security-Audit, API-Verträge validieren.

**Aufruf:**
```
subagent_type: code-api-checker
```

**Zuständige Dateien:** Lesezugriff auf alle Dateien, kein Schreibzugriff.

---

### 6. RAG / Knowledge-Agent

**Zweck:** pgvector-Konfiguration, Embedding-Pipeline, Chunking-Strategie, Ingest-Skripte.

**Aufruf:**
```
subagent_type: general-purpose
```

**Zuständige Dateien:**
- `auditworkshop/backend/services/knowledge_service.py`
- `auditworkshop/backend/services/file_parser.py`
- `auditworkshop/backend/services/pdf_parser.py`
- `auditworkshop/backend/routers/knowledge.py`
- `auditworkshop/backend/scripts/ingest_knowledge.py`
- `auditworkshop/backend/scripts/ingest_all.py`
- `auditworkshop/backend/data/`

---

### 7. Dokumentations-Agent

**Zweck:** README, CLAUDE.md, Projektbeschreibung aktuell halten.

**Aufruf:**
```
subagent_type: doc-generator
```

**Zuständige Dateien:**
- `CLAUDE.md`
- `docs/agents.md`
- `auditworkshop/README.md`
- `auditworkshop/CLAUDE.md`
- `auditworkshop/PROJEKTBESCHREIBUNG.md`

---

## Dateibereiche und Konfliktvermeidung

| Dateibereich | Primärer Agent | Sekundär erlaubt |
|---|---|---|
| `backend/routers/` | Backend | Code-Review (nur lesen) |
| `backend/models/`, `backend/schemas/` | Backend | — |
| `backend/services/knowledge_service.py`, `file_parser.py`, `pdf_parser.py` | RAG/Knowledge | Backend |
| `backend/services/ollama_service.py` | Backend | — |
| `backend/config.py` | **Keiner ohne Freigabe** | — |
| `frontend/src/pages/` | Frontend | — |
| `frontend/src/components/` | Frontend | — |
| `docker-compose.yml`, `Dockerfile*` | Docker/DevOps | — |
| `scripts/` | Test / Docker | — |
| `*.md` (Dokumentation) | Dokumentation | Alle (lesend) |

## Parallele Nutzung

Backend- und Frontend-Agent können parallel arbeiten, da ihre Dateibereiche disjunkt sind. Der Test-Agent sollte **nach** Änderungen durch Backend- oder Frontend-Agent laufen, nicht gleichzeitig.

**Empfohlener Workflow:**
1. Backend- und Frontend-Agent parallel starten
2. Nach Abschluss: Test-Agent starten
3. Bei Problemen: Code-Review-Agent für Analyse
4. Abschließend: Dokumentations-Agent für Updates
