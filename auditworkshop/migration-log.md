# Migrations-Sitzungs-Log — auditworkshop

Laufendes Log der Workshop-Migration. Format pro Eintrag laut Master-
Dokument Abschnitt 12. Einträge werden später in den Cockpit-Tracker
übernommen, sobald dieser läuft.

## Beobachtungen für Plan-Anpassung

Sammlung von Punkten, die in einer separaten Konversation in das
Master-Dokument oder die vier Plan-Dokumente einfließen sollen. Keine
unmittelbare Änderung der Plan-Dokumente.

1. **Parallelisierung der Phasen 0–5.** Der Eigentümer hebt die strikte
   Sequenzierung des Master-Dokuments (Abschnitt 4) auf und baut
   Tracker, CCX23-Grundlage, Cockpit-Foundations und Workshop-
   Migration parallel. Master-Dokument sollte einen optionalen
   Parallelisierungs-Pfad als zweite Variante neben der sequenziellen
   Standard-Reihenfolge dokumentieren.

2. **Hub auf CCX23 statt NUC.** Eigentümer-Entscheidung verlegt
   `egpu-manager-hub` und `llm-router` in den Docker-Stack auf CCX23.
   GPU_LLM_PREPARATION.md sollte diese Topologie-Variante als
   gleichwertige Alternative zur NUC-Hub-Variante dokumentieren,
   inkl. Trade-off-Tabelle (zentrale Steuerung vs. Latenz-Aufschlag).

3. **Desktop als GPU-Host.** Master-Dokument Abschnitt 1 listet den
   Desktop-PC nur als Konfigurations-/Build-Host und möglichen Host
   für private Workloads. Der Eigentümer nutzt den Desktop mit
   RTX 5070 und RTX 5060 zusätzlich als GPU-Spoke für
   `egpu-manager`. Master-Dokument und GPU_LLM_PREPARATION.md sollten
   den Desktop als optionalen dritten GPU-Host aufnehmen, mit zwei
   GPU-Slots.

4. **Geocode-Cache-Größe in Workshop-CLAUDE.md.** Die
   `auditworkshop/CLAUDE.md` und `flowworkshop/CLAUDE.md` (Workshop-
   Constraints) erwähnen 5.200+ Geocode-Einträge. Tatsächlich liegen
   im Repository **3.177 Einträge**. Korrektur sollte beim nächsten
   CLAUDE.md-Update einfließen.

5. **Embedding-Modell-Inkonsistenz in Workshop-CLAUDE.md.** Workshop-
   CLAUDE.md nennt `paraphrase-multilingual-mpnet-base-v2` (768 Dim.).
   Compose-ENV setzt `bge-m3` (1024 Dim.) — letzteres ist zur
   Laufzeit aktiv. Workshop-CLAUDE.md sollte beim nächsten Update
   bge-m3 als aktuelles Modell ausweisen.

6. **JSON-Logging-Formatter als Cockpit-internes Paket.** Im
   Workshop-Workstream wird der JSON-Formatter projekt-lokal
   eingerichtet. Sobald die zweite Anwendung (audit_designer in
   Phase 6) migriert wird, sollte der Formatter inklusive Request-ID-
   Middleware in ein internes Python-Paket extrahiert werden
   (`cockpit-logging` o.ä.).

7. **Rust für neue Komponenten.** Eigentümer-Wunsch: wo möglich Rust.
   Workshop-Backend bleibt Python/FastAPI (zu hoher Risiko/Nutzen-
   Faktor für Umschreibung). Rust ist sinnvoll und vorgesehen für:
   Cockpit-Realtime (Workstream C), `llm-router` (Workstream E) und
   `egpu-manager-hub` (Workstream E). Lifecycle-Hooks bleiben Bash,
   GitHub-Workflows YAML.

## Hetzner-Bestelliste (zur Eigentümer-Buchung)

Konkrete Produkte, die für die Workshop-Migration und den parallelen
Cockpit-Aufbau bei Hetzner gebucht werden müssen. Preise Stand
Mai 2026 — beim Bestellen final prüfen.

| # | Produkt | Standort | Konfiguration | ca. Preis |
|---|---|---|---|---|
| 1 | Cloud-Server **CCX23** | Falkenstein (FSN1) | Ubuntu 24.04 LTS · IPv4 + IPv6 · SSH-Key statt Passwort · 4 dedizierte AMD-EPYC-vCPU · 16 GB RAM · 160 GB NVMe · 20 TB Traffic · Cloud-Init für deploy-User + Tailscale | ~30 €/Monat |
| 2 | **Storage Box BX11** | Falkenstein | 1 TB · Sub-Account `ccx23-backup` · Sub-Account `nuc-backup` · automatischer Snapshot 04:00 | ~3,90 €/Monat |
| 3 | Cloud Snapshots | (zum CCX23) | täglich, Aufbewahrung 7 Tage | ~0,012 €/GB/Monat |

**Nicht zusätzlich nötig:** Floating IP, Load Balancer, weitere Server.
Das CCX23 trägt Cockpit, shared Postgres, Caddy und alle künftigen
Anwendungen, die auf Hetzner laufen sollen. Workshop-Stack belegt
~1,5 GB der 16 GB RAM (Backend ~512 MB + Frontend nginx ~50 MB +
Postgres-Anteil ~1 GB).

**Bestellschritte (am MacBook im Browser):**

1. Hetzner-Account anlegen, Identitätsprüfung abwarten — kann je nach
   Tageszeit Stunden dauern.
2. Cloud Console → *Add Server* → Standort Falkenstein → Image *Ubuntu
   24.04* → Type *CCX23* → IPv4 + IPv6 → SSH-Key hochladen →
   Cloud-Init-User-Data einfügen (deploy-User, Tailscale-Daemon,
   Tailscale-Beitritt mit OAuth-Auth-Key aus Tracker-Tresor).
3. Nach Hochfahren: Backup aktivieren → täglich, 7 Tage.
4. Storage Boxen → *Bestellen* → BX11 in Falkenstein → zwei Sub-
   Accounts via API anlegen.
5. API-Token im Cockpit-Tracker-Tresor ablegen
   (`POST /api/v1/secrets`), nicht im Klartext speichern.

## Sitzungs-Einträge

### 2026-05-10: Phase 5 / Workstream D — Repository-Konventionen

- Dauer: ~3 h (verteilt auf zwei Sitzungen).
- Behandelte Aufgaben: Inventur, migration-plan, `compose.yaml` aus
  `docker-compose.yml` abgeleitet, `lifecycle/{bootstrap,migrate,start,
  stop}.sh`, `caddy/Caddyfile.fragment`, `backup.yaml`, drei GitHub-
  Workflows (`ci.yaml`, `image.yaml`, `deploy.yaml`), Health-Endpoint
  im `backend/main.py` auf Cockpit-Schema gehoben, JSON-Logging-Setup
  als neues `backend/logging_config.py` (System-Prompts in
  `config.py` unangetastet), `RequestContextMiddleware` registriert,
  `.env.production.example`, drei Helper-Skripte
  (`scripts/snapshot_for_hetzner.sh`,
  `scripts/restore_on_ccx23.sh`,
  `scripts/verify_hetzner_deploy.sh`).
- Resultat: Workshop-Repository erfüllt die Cockpit-Konventionen aus
  Master-Dokument Abschnitt 7.
  - `docker compose -f compose.yaml config --quiet` → exit 0.
  - `ruff check main.py logging_config.py` → All checks passed.
  - Bash-Syntax aller drei Helper-Skripte: `bash -n` → OK.
- Nächster Schritt: Hetzner-Bestellung (siehe Abschnitt oben), dann
  Workstreams A (CCX23 + Storage Box), B (cockpit-tracker auf NUC),
  C (Cockpit-Repository), E (egpu-manager + llm-router) starten.
  Stufe 8.2 (Daten-Snapshot) sobald S1, S2, S3 erreicht sind.
- Offene Punkte: Quell-Host und Compose-Pfad final bestätigen
  (Annahme: NUC, `~/projects/auditworkshop`); produktive Workshop-URL
  bestätigen (Annahme: `auditworkshop.tail-xxxx.ts.net`); Tracker-
  Tresor-IDs für Workshop-Geheimnisse vergeben (DB-Passwort,
  Tailscale-OAuth, ghcr.io-Pull-Token, age-Recipient).
- Beobachtungen für Plan-Anpassung: siehe Abschnitt oben.
