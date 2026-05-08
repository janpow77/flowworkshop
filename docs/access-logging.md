# Workshop Access-Logging

Stand: 2026-05-08

Das Workshop-Backend protokolliert pro `/api/*`-Request einen Eintrag in
`workshop_access_log`. Ziel ist, dass der Workshop-Admin nachvollziehen kann,
welche Seiten und Endpoints wie oft genutzt werden — ohne externes Tracking,
ohne Klartext-IP, DSGVO-konform.

## Was wird geloggt

Pro Request eine Zeile mit folgenden Feldern:

| Feld | Inhalt |
|------|--------|
| `created_at` | Zeitpunkt der Anfrage (UTC, server-side) |
| `method` | HTTP-Methode (GET/POST/...) |
| `path` | Konkrete URL (ohne Query) |
| `path_template` | FastAPI-Route-Template (`/api/state-aid/award/{id}`) |
| `query_string` | Query, sensible Parameter sind auf `***` maskiert |
| `status_code` | HTTP-Antwort-Code |
| `duration_ms` | Bearbeitungsdauer in Millisekunden |
| `user_id` / `role` | aus der Workshop-Session, falls erkannt; sonst `anon` |
| `ip_hash` | SHA256(IP + ENV-Salt) — **kein** Klartext-IP |
| `ua_short` | bis 80 Zeichen User-Agent + grobe Browser-Kategorie (`[Chrome]`, `[Bot]`, ...) |
| `referer_path` | nur Pfad-Teil eines Referer (keine Query) |
| `response_size` | Bytes (aus Content-Length, falls gesetzt) |

## Was NICHT geloggt wird

- `/health`, `/openapi.json`, `/docs`, `/redoc`, `/favicon.ico`
- Statische Assets (`/static/*`, `/assets/*`)
- Health-Probes mit User-Agent `kube-probe` oder `docker-healthcheck`
- Pfade ausserhalb von `/api/*`
- **Niemals**: Request-Bodies, Login-Credentials, Klartext-IPs

## DSGVO-Konformitaet

- **IP-Hashing**: SHA256 ueber `IP|<WORKSHOP_IP_SALT>`. Aus dem Hash laesst
  sich die IP nicht rekonstruieren; gleichzeitig erlaubt der Hash, denselben
  Browser ueber mehrere Requests hinweg zu erkennen (z.B. um Sessions zu
  zaehlen).
- **Keine PII**: ausser dem User-Hash (`user_id`-UUID, falls eingeloggt) und
  Vorname+Nachname **per JOIN auf `workshop_registrations`** (nur in der
  Admin-UI sichtbar) gibt es keine personenbezogenen Daten.
- **Query-Sanitisierung**: Parameter mit den Schluesseln `password`, `passwd`,
  `pwd`, `token`, `api_key`, `apikey`, `secret`, `auth`, `authorization`,
  `qr`, `pin` werden vor dem Insert auf `***` gesetzt.
- **TTL**: Default 30 Tage. Ueber `WORKSHOP_ACCESS_LOG_TTL_DAYS` per Env-Var
  konfigurierbar. Pruning laeuft taeglich um 03:00 UTC im Background-Scheduler.

## Architektur

```
Request → CORSMiddleware → AccessLogMiddleware → Router → Response
                                  │
                                  └─► run_in_executor → DB-Insert
                                       (non-blocking, eigene Session)
```

- Die Middleware schreibt den Eintrag **nach** der Response-Auslieferung im
  Default-ThreadPool. Der Hot-Path bleibt unbeeinflusst.
- DB-Fehler im Logging werden geschluckt — die App-Funktion bleibt selbst dann
  erhalten, wenn die Log-Tabelle nicht erreichbar waere.

## Admin-UI

Endpoints unter `/api/admin/access/*` (alle erfordern Admin-Login):

| Endpoint | Zweck |
|----------|-------|
| `GET /summary?since_hours=24` | Kennzahlen: Requests, Unique-User/IP, Status-Verteilung, Avg/p95-Latenz, RPS |
| `GET /timeseries?since_hours=24&bucket_minutes=10` | Zeitreihe fuer Charts |
| `GET /top-paths?since_hours=24&limit=20` | meist genutzte Routen (avg/p95) |
| `GET /top-users?since_hours=24&limit=20` | aktivste Nutzer (Name+Org via JOIN) |
| `GET /recent?limit=200&user_id=&path=&before_id=` | Drilldown letzte N Eintraege |
| `GET /stats/state-aid?since_hours=24` | aggregiert nur State-Aid-Endpoints (search/ask/map/export/...) |

## Konfiguration (ENV)

| Variable | Default | Bedeutung |
|----------|---------|-----------|
| `WORKSHOP_IP_SALT` | `flowworkshop-2026` | Salt fuer den IP-Hash |
| `WORKSHOP_ACCESS_LOG_TTL_DAYS` | `30` | Tage, nach denen Eintraege geloescht werden |
| `ACCESS_LOG_PRUNE_HOUR` | `3` | UTC-Stunde fuer das taegliche Pruning |

## Pruefen

```bash
# eine Anfrage absetzen:
curl http://localhost:8006/api/state-aid/status

# DB-Eintraege zaehlen:
docker exec auditworkshop-backend python3 -c "
from sqlalchemy import text
from database import engine
with engine.connect() as c:
    print(c.execute(text('SELECT count(*) FROM workshop_access_log')).scalar())
"

# Admin-Stats abfragen (mit Token):
TOKEN=$(curl -s -X POST http://localhost:8006/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"jan.riener@wirtschaft.hessen.de"}' | jq -r .token)
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8006/api/admin/access/summary?since_hours=24" | jq
```

## Tests

`backend/tests/test_access_log_middleware.py` deckt ab:

- Health-Endpunkte werden NICHT geloggt
- API-Endpunkte werden mit korrektem `path_template` geloggt
- Pfad-Parameter erscheinen als Template (`/award/{id}` statt `/award/abc123`)
- 404-Pfade werden mit `path == path_template` geloggt
- Sensible Query-Parameter werden auf `***` maskiert
- `kube-probe`/`docker-healthcheck` werden ignoriert
- IP-Hash ist deterministisch und verbirgt die Klartext-IP
- User-Agent-Kategorisierung trifft Chrome/Firefox/curl/Bot
