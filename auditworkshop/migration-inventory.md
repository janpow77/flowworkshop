# Migration Inventory — auditworkshop

Bestandsaufnahme des Quell-Stacks vor der Migration auf den Hetzner CCX23.
Erstellt im Rahmen von Workstream D (Repository-Konventionen) des
freigegebenen Plans `und-inherited-matsumoto.md`.

## 1. Compose-Stack (`docker-compose.yml`)

Vier Services:

| Service | Image | Container-Name | Externe Ports | Volume |
|---|---|---|---|---|
| db | `pgvector/pgvector:pg16` | `auditworkshop-db` | `5434:5432` | benanntes Volume `db_data` |
| backend | `./backend` (Build) | `auditworkshop-backend` | `8006:8000` | Bind-Mount `./backend/data:/app/data` |
| frontend | `./frontend` (Build, nginx) | `auditworkshop-frontend` | `3004:80` | — |
| cloudflared | `cloudflare/cloudflared:latest` | `auditworkshop-cloudflared` | — | — |

Restart-Policy `unless-stopped` für db, backend, frontend; `always` für
cloudflared. Healthchecks für db (`pg_isready`) und backend
(Inline-Python gegen `/health`).

## 2. Backend-Env-Variablen

Aktueller Stand aus `docker-compose.yml`:

- `DATABASE_URL=postgresql://workshop:workshop@db:5432/workshop`
- `OLLAMA_URL=http://host.docker.internal:11434`
- `LLM_BACKEND=egpu-manager`
- `EGPU_GATEWAY_URL=http://host.docker.internal:7842`
- `EGPU_GATEWAY_APP_ID=auditworkshop`
- `EGPU_WORKLOAD_TYPE=llm`
- `EMBEDDING_BACKEND=gateway`
- `EMBEDDING_GATEWAY_URL=http://host.docker.internal:7842`
- `EMBEDDING_GATEWAY_APP_ID=auditworkshop`
- `EMBEDDING_MODEL=bge-m3`
- `EMBEDDING_DIM=1024`
- `MODEL_NAME=qwen3:14b`
- `WORKSHOP_ADMIN=true`
- `ALLOW_REMOTE_GEOCODING=false`
- `ALLOW_REMOTE_TILES=true`

Externe Konfiguration: `${CLOUDFLARE_TUNNEL_TOKEN}` aus `.env` am
Quell-Host. Nicht im Repository sichtbar.

Der dokumentierte Wert in `auditworkshop/CLAUDE.md`
(`paraphrase-multilingual-mpnet-base-v2`, 768 Dim.) stimmt nicht mit dem
zur Laufzeit aktiven Wert (`bge-m3`, 1024 Dim.) überein. Maßgeblich ist
die Compose-ENV.

## 3. Backend-Codebasis

Umfang ist deutlich größer als die README/CLAUDE.md suggerieren. Inventur
des `backend/`-Verzeichnisses:

- `main.py` (≈ 1.000 Zeilen) — FastAPI-App, Lifespan, Router-Registrierung,
  Inline-Migrations-Logik mit `ALTER TABLE`-Anweisungen für Workshop-
  Tabellen.
- `config.py` — System-Prompts und Einstellungen
  (Workshop-Constraint: nicht ohne Absprache verändern).
- `database.py` — SQLAlchemy Engine, Session, Base.
- 22 Modelle in `models/` — u.a. `access_log`, `audit_log`, `automation`,
  `beneficiary_records`, `beneficiary_sources_config`, `checklist`,
  `corporate_lookup_cache`, `docs`, `document`, `entities`,
  `entity_embeddings`, `entity_match_llm_run`, `forum`, `project`,
  `registration`, `sanctions_entries`, `session`, `state_aid`,
  `state_aid_audit`, `state_aid_validation`.
- 23 Router in `routers/` — u.a. `admin_access`, `assessment`, `auth`,
  `automation`, `beneficiaries`, `beneficiaries_sources`, `checklists`,
  `dataframes`, `demo_data`, `docs`, `documents`, `embeddings`,
  `entities`, `event`, `forum`, `knowledge`, `notifications`, `projects`,
  `reference_data`, `sanctions`, `state_aid`, `system`, `workshop`.
- 23 Services in `services/` — darunter `access_log_middleware`,
  `audit_match_verifier`, `beneficiary_harvester`, `company_aliases`,
  `corporate_registry`, `country_profiles`, `dataframe_service`,
  `entity_embeddings`, `entity_match_llm_verifier`, `entity_resolution`,
  `excel_export`, `file_parser`, `geocoding_service`, `knowledge_service`,
  `ollama_service`, `pdf_parser`, `sanctions_service`, `scheduler`,
  `state_aid_audit_pdf`, `state_aid_audit_report`, `state_aid_harvester`,
  `state_aid_llm`, `state_aid_service`, `state_aid_validator`.

Health-Endpoint aktuell minimal:

```python
@app.get("/health")
def health():
    return {"status": "ok", "service": "flowworkshop"}
```

Logging ist klassisch:
`logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")`.

## 4. Bind-Mount-Inhalt (`backend/data/`)

| Datei/Verzeichnis | Größe | Zweck |
|---|---|---|
| `geocode_cache.json` | 434 KB, **3.177 Einträge** | Nominatim-Geocoding-Cache (Workshop-Constraint: nicht löschen) |
| `transparenzliste_hessen.xlsx` | 111 KB | EFRE-Transparenzliste Hessen |
| `transparenzliste_esf_hessen.xlsx` | 6 KB | ESF-Transparenzliste Hessen |
| `transparenzliste_jtf.xlsx` | 6 KB | JTF-Transparenzliste |
| `beguenstigten_analyse.xlsx` | 38 KB | Begünstigten-Analyse |
| `transparenzlisten_urls.json` | 15 KB | Quell-URLs der Transparenzlisten |
| `state_aid_aliases.json` | 3 KB | Alias-Mappings für State-Aid-Verifikation |
| `plz_de.json` | 960 KB | Deutsche Postleitzahlen → Geo-Koordinaten |
| `plz_at.json` | 186 KB | Österreichische PLZ |
| `nuts_de.json` | 51 KB | NUTS-Regionen Deutschland |
| `nuts_at.json` | 6 KB | NUTS-Regionen Österreich |
| `nuts/` | — | NUTS-Geo-Daten |
| `geo/` | — | Geo-Hilfsdaten |
| `demo_documents/` | — | 8 Demo-Skripte: `ai_act_einordnung.py`, `benchmark_roi.py`, `eu_verordnung.py`, `foerderbescheid.py`, `foerderbescheid_esf.py`, `prueffeststellungen.py`, `prueffeststellungen_esf.py` |
| `demo_templates/` | — | `vko_efre_2021.json`, `vko_esf_2021.json` |

In Schätzung der ursprünglichen Plan-Sitzung wurden 5.200+
Geocode-Einträge angenommen; tatsächlich sind es **3.177**. Der Bind-
Mount muss vollständig erhalten bleiben.

## 5. Datenbank-Schema

Aus den SQLAlchemy-Modellen (`models/`) und Inline-Migrations-DDL in
`main.py`:

- Tabellen folgen der Konvention `workshop_<entität>` (z.B.
  `workshop_agenda_items`, `workshop_meta`, `workshop_registrations`,
  `workshop_access_log`).
- Quell-DB: Datenbank `workshop`, User `workshop`, Schema `public`.
- pgvector-Tabellen für RAG (Wissensdatenbank, Embeddings).
- IVFFlat-Index auf Vektor-Spalten (Workshop-Constraint: nicht entfernen).

DB-Größe und exakte Tabellenzeilen werden am Quell-Host vor Stufe 8.2
ermittelt:

```bash
docker exec auditworkshop-db psql -U workshop -d workshop -c \
  "SELECT pg_size_pretty(pg_database_size('workshop'));"
docker exec auditworkshop-db psql -U workshop -d workshop -c \
  "SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY n_live_tup DESC LIMIT 20;"
```

## 6. Frontend

- `frontend/Dockerfile`: Multi-Stage `node:20` Build → `nginx:alpine`.
- `frontend/nginx.conf`: produktions-Reverse-Proxy `/api/` → Backend.
- React 19 + TypeScript 5.9 + Tailwind 4 + Vite 8.

Der Frontend-Bind im Compose ist nicht vorhanden; der Build-Output landet
im Image. Bei Code-Änderungen ist ein Rebuild nötig.

## 7. Smoke-Test-Skript

`auditworkshop/scripts/workshop_smoke.sh` — acht HTTP-Endpunkt-Checks,
parametrierbar über `BACKEND_BASE` und `FRONTEND_BASE`. Bleibt
unverändert nutzbar nach der Migration.

Zusätzlich vorhanden: `auditworkshop/scripts/state_aid_smoke.sh`.

## 8. GitHub-Workflows

Verzeichnis `.github/workflows/` existiert im Workshop-Repository
**nicht**. Drei Workflow-Dateien (`ci.yaml`, `image.yaml`, `deploy.yaml`)
werden in Workstream D neu angelegt.

## 9. Quell-Host

In dieser Plan-Sitzung nicht endgültig identifiziert. In der
Ausführungssitzung am Beginn von Stufe 8.2 zu klären:

- Auf welchem Heim-Host läuft der Stack (NUC oder Desktop)?
- Pfad des Compose-Verzeichnisses?
- SSH-Zugang?

Standardannahme bis zur Klärung: NUC, Pfad `~/projects/auditworkshop/`,
SSH über Tailscale-Hostname des NUC.

## 10. Geänderte Annahmen gegenüber der ursprünglichen Plan-Skizze

- Geocode-Cache: **3.177 Einträge** (nicht 5.200+).
- Embedding-Modell zur Laufzeit: **bge-m3, 1024 Dim.** (CLAUDE.md sagt
  abweichend mpnet 768 Dim.).
- Backend-Codebasis ist deutlich umfangreicher als in
  `auditworkshop/CLAUDE.md` skizziert: 22 Modelle, 23 Router, 23
  Services. Die Migration berührt keinen dieser Inhalte; die
  Anpassungen beschränken sich auf Compose, Health-Endpoint und
  Logging-Setup.
