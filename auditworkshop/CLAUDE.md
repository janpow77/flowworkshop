# Auditworkshop — CLAUDE.md

## Zweck
Standalone Workshop-Demo: „KI und LLMs in der EFRE-Prüfbehörde".
Sechs Live-Szenarien mit lokalem Qwen3-14B via Ollama auf RTX 5070 Ti (eGPU).
Das Projekt dient gleichzeitig als Optimierungsfeld — bewährte Verbesserungen
werden per Patch in flowinvoice und audit_designer zurückgespielt.

Seit Mai 2026 läuft die produktive Plattform auf einem Hetzner CCX23
(Frankfurt-Nürnberg, 4 vCPU AMD, 16 GB) hinter dem zentralen `llm-router`
auf demselben Host. NUC bleibt 7 Tage als Hot-Standby online (ohne
Cloudflared-Tunnel) und ist weiterhin der LLM-Spoke für den Router.

## Stack
- Backend:  FastAPI (Python 3.12), Container-Port 8000
- Frontend: React + TypeScript + Tailwind, nginx-Container Port 80
- Datenbank: PostgreSQL 16 + pgvector
  - **NUC-Dev**: eigener Container `auditworkshop-db`, Port 5434 extern
  - **CCX23-Prod**: shared Postgres auf dem Host, DB `workshop`, listen 172.18.0.1
- LLM:
  - **NUC-Dev**: direkter Aufruf `egpu-managerd` auf dem Host (Port 7842) bzw. Ollama (11434)
  - **CCX23-Prod**: über `llm-router` auf demselben Host (`http://llm-router:7842`, App-Id `auditworkshop`)
- Modell:   qwen3:14b (primär), Fallback: qwen3:8b
- Embeddings: **bge-m3 (1024 Dim.)** via Ollama. Frühere CLAUDE-Notiz mit
  paraphrase-multilingual-mpnet-base-v2 (768 Dim.) ist überholt — die
  Compose-ENV setzt seit langem `EMBEDDING_MODEL=bge-m3 / EMBEDDING_DIM=1024`.

## Wichtige Pfade
| Pfad | Inhalt |
|---|---|
| backend/config.py | ALLE System-Prompts und Einstellungen |
| backend/services/knowledge_service.py | pgvector RAG |
| backend/services/ollama_service.py | LLM-Streaming |
| backend/routers/workshop.py | Szenarien 1–6 |
| backend/routers/knowledge.py | Ingest + Suche |
| backend/scripts/ingest_knowledge.py | Verordnungen einlesen |
| backend/scripts/backfill_state_aid_identifiers.py | Backfill der nationalen Kennungen aus dem TAM-Detail-Scrape |
| backend/data/knowledge_raw/ | Heruntergeladene PDFs |
| backend/data/geocode_cache.json | Nominatim-Cache, **3.177 Einträge** (frühere Notiz mit „5.200+" war eine Schätzung). Cache nicht löschen. |
| frontend/src/pages/ImpressumPage.tsx | Impressum nach § 5 DDG, eigene Page-Komponente |
| frontend/src/pages/DatenschutzPage.tsx | DSGVO-Erklärung, eigene Page-Komponente |
| **../migration-plan.md** (Branch `claude/workshop-hetzner-migration-95SDB`) | 7-Stufen-Cutover-Plan auf CCX23 |

## Szenarien
1. Dokumentenanalyse — Auflagen aus Förderbescheid extrahieren
2. Checklisten-Unterstützung — VKO-Einschätzung als JSON
3. Halluzinationsdemonstration — mit/ohne RAG-Kontext
4. Berichtsentwurf — Feststellungen → Berichtpassage
5. Vorab-Upload — eigene Dokumente der Prüfer (pgvector)
6. Begünstigtenverzeichnis — XLSX + LLM + Leaflet-Karte

## Start

### NUC-Dev (lokal)
```bash
docker compose up -d
# Verordnungen einlesen (einmalig):
docker exec auditworkshop-backend python scripts/ingest_knowledge.py --all
```

### CCX23-Prod
Stack liegt unter `/opt/auditworkshop/auditworkshop/`. Verwaltung über die
Lifecycle-Skripte aus dem Migrations-Branch:
```bash
ssh deploy@cockpit-nbg1-1.tailec75b1.ts.net
cd /opt/auditworkshop/auditworkshop
docker compose -f compose.yaml ps
docker compose -f compose.yaml logs --tail 50 auditworkshop-backend
```
Konfiguration unter `/etc/auditworkshop/env` (chmod 600).

## Smoke-Tests

```bash
# Local-NUC
bash scripts/workshop_smoke.sh
# Tailscale-internal (CCX23)
BACKEND_BASE=https://cockpit-nbg1-1.tailec75b1.ts.net \
FRONTEND_BASE=https://cockpit-nbg1-1.tailec75b1.ts.net \
  bash scripts/workshop_smoke.sh
# Public-Domain (CCX23, nach DNS-Flip)
BACKEND_BASE=https://workshop.flowaudit.de \
FRONTEND_BASE=https://workshop.flowaudit.de \
  bash scripts/workshop_smoke.sh
```

## Was NICHT geändert werden soll
- System-Prompts in config.py ohne Absprache verändern
- Demo-Dokumente mit echten personenbezogenen Daten befüllen
- WORKSHOP_ADMIN auf false setzen während des Workshops
- Den pgvector IVFFlat-Index entfernen
- NUC-Stack stoppen während der 7-Tage-Hot-Standby-Phase nach Cutover
- Die 6 Backfill-Sidecar-Container (`backfill-{de,at}-N`) auf NUC anhalten —
  sie kontextlos restarten ist nicht idempotent (mit Sharding korrekt schon)

## Architektur-Entscheidungen
- Kein Auth — lokale Demo-Anwendung, kein Internetzugang im Workshop
- Kein persistenter Session-State — alle Daten sind request-basiert
- Streaming via Server-Sent-Events (kein WebSocket)
- pgvector statt ChromaDB — ein Dienst weniger, SQL-auditierbar
- Ollama läuft auf dem Host (nicht in Docker) — GPU-Anbindung stabiler
- WORKSHOP_ADMIN steuert Ingest-Endpunkt — kein separates Auth-System
- **CCX23-Prod redet via `llm-router`** mit dem NUC-Spoke, nicht direkt — Stats,
  Quotas, Audit-Log, künftiges Multi-Spoke (NUC + evo + Desktop) zentral

## Bekannte Constraints
- Thunderbolt 4 eGPU braucht ~2 Min. zum Initialisieren nach Kaltstart
- Qwen3-14B Q8 belegt ~15 GB VRAM der RTX 5070 Ti (16 GB)
- Nominatim-API: max. 1 Request/s (Szenario 6 Geocoding)
- LLM-Router-Auth: Workshop schickt `X-App-Id: auditworkshop` mit jedem
  Gateway-Call; `X-Api-Key` wird nur angehängt, wenn `AI_ROUTER_API_KEY`
  gesetzt ist (Helper `config.gateway_headers`). Der Router erzwingt aktuell
  keinen Key — der Live-Betrieb läuft mit reinem `X-App-Id`.
- Backfill-Tempo: ~5–10 k Updates/h gesamt mit 6 Workern (sleep 0.2s, HTTP-Bound)

## Zusammenhang mit anderen Projekten
- Aus flowinvoice übernommen: pdf_parser.py (Multi-Level), Ollama-Streaming-Muster
- Aus audit_designer übernommen: Checklisten-Schema, pgvector-Nutzung, System-Prompt-Struktur
- An llm-router gekoppelt: erste Konsumenten-App, Test-Bench für Capability-Routing
- Optimierungen fließen per Patch zurück (Prompts J + K im Planungsdokument).
