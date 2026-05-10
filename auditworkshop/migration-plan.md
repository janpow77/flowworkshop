# Migrationsplan — auditworkshop auf Hetzner CCX23

Workshop-spezifischer Auszug aus dem freigegebenen Master-Plan
`und-inherited-matsumoto.md`. Diese Datei führt durch die sieben Stufen
aus APPS_PREPARATION.md Abschnitt 8.1 bis 8.7. Der Plan parallelisiert
Tracker-, Cockpit- und LLM-Hub-Aufbau mit der Workshop-Migration; die
hier genannten Stufen sind der Workstream F.

## Vorbedingungen

Aus den parallelen Workstreams müssen folgende Synchronisations-Punkte
erreicht sein, bevor Stufe 8.2 beginnen kann:

- **S1** Tailscale-Mesh enthält MacBook, Desktop, NUC und CCX23.
- **S2** Tracker-Tresor enthält Hetzner-API-Token, GitHub-Tokens,
  Tailscale-OAuth-Client.
- **S3** CCX23 hat Caddy + Postgres (mit pgvector und TimescaleDB) +
  Docker.

Workstream E (LLM-Hub auf CCX23) ist optional zu Beginn von F. Das
Workshop-Backend startet mit direktem NUC-Aufruf; Umstellung auf den
`llm-router` erfolgt, sobald E grün ist (eine Env-Variable).

## Stufe 8.1 — Repository-Konventionen (Workstream D, hier erledigt)

Im Workstream D abgeschlossen:

- `compose.yaml` aus `docker-compose.yml` abgeleitet, db- und
  cloudflared-Service entfernt, Service-Namen `auditworkshop-backend`
  und `auditworkshop-frontend`, Bind-Mounts auf `/var/lib/auditworkshop/`
  und `/etc/auditworkshop/`, Logging-Driver `json-file` mit Rotation.
- `lifecycle/{bootstrap,migrate,start,stop}.sh` angelegt (idempotent).
- `caddy/Caddyfile.fragment` angelegt (Tailscale-only-Bind, HSTS,
  Kompression, X-Content-Type-Options).
- `backup.yaml` angelegt (Schema `workshop`, Pfad
  `/var/lib/auditworkshop/data`, Retention 7/4/12, age-Verschlüsselung).
- `.github/workflows/{ci,image,deploy}.yaml` angelegt.
- Health-Endpoint in `backend/main.py` auf das Cockpit-Schema gehoben:
  `{status, version, started_at, checks}`.
- JSON-Logging-Setup in neuer Datei `backend/logging_config.py`
  (Workshop-Constraint: `config.py` mit System-Prompts bleibt
  unangetastet — die Logging-Konfiguration wurde bewusst in ein
  eigenes Modul ausgelagert). Aktivierung über
  `LOG_FORMAT=json` in `/etc/auditworkshop/env`.
- `RequestContextMiddleware` in `backend/main.py` registriert; setzt
  pro Request eine UUID-Request-ID und liest die Tailscale-Identity
  aus dem `Tailscale-User-Login`-Header, den Caddy auf CCX23
  durchreicht.

Akzeptanzkriterien D:

- `docker compose -f compose.yaml config` parst sauber.
- Backend-Health-Endpoint liefert lokal das vorgegebene JSON-Schema.
- Backend-Logging gibt strukturiertes JSON aus.
- `ci.yaml` läuft auf einem Test-Branch grün.

## Stufe 8.2 — Daten-Snapshot am Quell-Host

Ausführung am Heim-Host (NUC oder Desktop, in Sitzung klären):

```bash
cd ~/projects/auditworkshop  # Pfad in Sitzung verifizieren
docker compose stop backend cloudflared   # DB läuft weiter
TS=$(date +%Y%m%d-%H%M)
docker exec auditworkshop-db pg_dump -Fc -U workshop workshop \
  > workshop-dump-$TS.dump
tar -czf workshop-data-$TS.tar.gz -C backend data
sha256sum workshop-dump-$TS.dump workshop-data-$TS.tar.gz \
  > workshop-snapshot-$TS.sha256
scp workshop-dump-$TS.dump workshop-data-$TS.tar.gz \
    workshop-snapshot-$TS.sha256 \
    deploy@cockpit-server.tail-xxxx.ts.net:/var/tmp/workshop-migration/
ssh deploy@cockpit-server.tail-xxxx.ts.net \
    "cd /var/tmp/workshop-migration && sha256sum -c workshop-snapshot-$TS.sha256"
docker compose start backend cloudflared
```

## Stufe 8.3 — Daten-Restore auf CCX23

```sql
-- Tracker-Tresor liefert das Passwort via
-- POST /api/v1/secrets/{id}/reveal mit purpose und task_context_id.
CREATE ROLE workshop_app LOGIN PASSWORD '<aus Tracker-Tresor>';
CREATE SCHEMA workshop AUTHORIZATION workshop_app;
```

```bash
# Restore ins Schema workshop. Quell-Dump nutzt public — Mapping über
# pg_restore --no-owner und anschließendes ALTER SCHEMA-Verschieben,
# oder Dump bereits mit --schema=public und Restore mit
# search_path-Setzung.
pg_restore --no-owner --role=workshop_app --schema=public \
  -d cockpit workshop-dump-<TS>.dump
psql -d cockpit -c "ALTER SCHEMA public RENAME TO workshop_tmp;
                    ALTER SCHEMA workshop RENAME TO public_old;
                    ALTER SCHEMA workshop_tmp RENAME TO workshop;
                    -- Backup-Schema public_old für Rollback"
psql -d cockpit -c "REINDEX SCHEMA workshop;"

# Tarball auspacken
sudo mkdir -p /var/lib/auditworkshop/data
sudo tar -xzf workshop-data-<TS>.tar.gz \
  -C /var/lib/auditworkshop/data --strip-components=1
sudo chown -R 1000:1000 /var/lib/auditworkshop/data
```

IVFFlat-Index nach Restore prüfen (Workshop-Constraint).

## Stufe 8.4 — Stack-Aufbau (Staging-Sub-Domain)

```bash
sudo mkdir -p /opt/auditworkshop /etc/auditworkshop
cd /opt/auditworkshop
git clone --branch claude/workshop-hetzner-migration-95SDB \
  https://github.com/janpow77/flowworkshop.git .
sudo cp .env.production.example /etc/auditworkshop/env
sudo chmod 0600 /etc/auditworkshop/env
sudo $EDITOR /etc/auditworkshop/env  # Tresor-Werte einsetzen
sudo bash lifecycle/bootstrap.sh
sudo bash lifecycle/start.sh
```

Caddy-Fragment unter Staging-Hostname `auditworkshop-stage.tail-xxxx.ts.net`
einbinden.

LLM-Verbindung initial: `OLLAMA_URL=http://<nuc-tailscale>:11434`,
`EGPU_GATEWAY_URL=http://<nuc-tailscale>:7842`. Sobald Workstream E
grün, Umstellung auf `OLLAMA_URL=http://llm-router:7842/v1` und
`EGPU_GATEWAY_URL=http://llm-router:7842` (Docker-Netz-intern auf CCX23).

Verifikation:

```bash
BACKEND_BASE=https://auditworkshop-stage.tail-xxxx.ts.net \
FRONTEND_BASE=https://auditworkshop-stage.tail-xxxx.ts.net \
bash scripts/workshop_smoke.sh
```

Sechs Live-Szenarien manuell durchspielen:
Dokumentenanalyse, Checklisten-Unterstützung, Halluzinations-
demonstration, Berichtsentwurf, Vorab-Upload, Begünstigtenverzeichnis.

## Stufe 8.5 — Cutover (Wartungsfenster, ausdrückliche Freigabe)

Master-Dokument Abschnitt 6 verlangt eine bewusste Pause. Nicht ohne
Eigentümer-Freigabe ausführen.

```bash
# Quell-Host
docker compose stop backend cloudflared
docker exec auditworkshop-db pg_dump -Fc -U workshop workshop \
  > workshop-delta-$(date +%Y%m%d-%H%M).dump
scp workshop-delta-*.dump deploy@cockpit-server.tail-xxxx.ts.net:/var/tmp/workshop-migration/

# CCX23
psql -d cockpit -c "TRUNCATE SCHEMA workshop CASCADE;"  # nur nach Bestätigung
pg_restore --no-owner --role=workshop_app --schema=workshop \
  -d cockpit workshop-delta-<TS>.dump

# Caddy-Fragment auf produktive Domain umstellen
sudo cp caddy/Caddyfile.fragment /etc/caddy/sites-enabled/auditworkshop.conf
sudo sed -i 's/auditworkshop-stage/auditworkshop/' /etc/caddy/sites-enabled/auditworkshop.conf
sudo systemctl reload caddy

# Smoke-Test gegen produktive URL
BACKEND_BASE=https://auditworkshop.tail-xxxx.ts.net \
FRONTEND_BASE=https://auditworkshop.tail-xxxx.ts.net \
bash scripts/workshop_smoke.sh
```

Quell-Stack 7 Tage als Hot-Standby gestoppt halten. Cloudflare-Tunnel
deaktiviert, Token noch nicht revoked.

## Stufe 8.6 — Stabilisierung (mehrere Tage)

- 48-h-Logsichtung: Tailscale-NUC-Latenz, pgvector-Query-Zeit,
  Geocoding-Cache-Hit-Rate, Backend-Fehler.
- Erster automatischer Backup-Job in der Nacht, erster Restore-Test in
  einer Sandbox-DB.
- Cockpit-Statusübersicht zeigt Workshop als gesund (gleichzeitige
  Validierung von Workstream C).

## Stufe 8.7 — Cleanup (nach 7 Tagen ohne Rollback)

- `docker compose down` am Quell-Host. Volume `db_data` archivieren oder
  löschen — nur nach ausdrücklicher Bestätigung.
- Cloudflare-Tunnel-Konfiguration löschen, Tunnel-Token revoken.
- `migration-log.md` finalisieren, Eintrag in Cockpit-Tracker,
  Architecture Decision Record schreiben.

## Rollback-Pfad (jederzeit bis Cleanup)

Falls Probleme nach Cutover:

1. Caddy-Fragment auf Quell-Host zurückstellen (DNS bleibt unverändert,
   weil Tailscale-Hostname in Caddy zeigt; bei externer DNS: A-Record
   zurück).
2. Quell-Stack hochfahren: `docker compose start backend cloudflared`.
3. Letzter Delta-Dump in alte DB einspielen, falls Schreibvorgänge auf
   CCX23 stattfanden.

## End-to-End-Verifikation (S5)

Siehe Master-Plan `und-inherited-matsumoto.md`, Abschnitt
„End-to-End-Integrations-Test (S5)" — zwölf Bedingungen, alle
gleichzeitig grün.
