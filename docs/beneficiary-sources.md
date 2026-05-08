# Beneficiary-Quellen — datengetriebene Pipeline (Phase 6b)

Stand: 2026-05-08

Dieses Dokument beschreibt die ab Phase 6b verfuegbare datengetriebene
Worker-Pipeline fuer Begueenstigtenverzeichnisse. Statt fuer jedes neue
Bundesland Code-Patches zu schreiben, pflegt der Admin per UI eine
Konfigurationszeile in `workshop_beneficiary_sources_config` und der
Worker uebernimmt den Rest.

## Zielbild

- **Phase 6a (bereits vorhanden):** Smart-Mode-Harvester
  `services.beneficiary_harvester` schreibt in die zentrale Tabelle
  `workshop_beneficiary_records`. Drei Modi: smart, full-refresh, force.
- **Phase 6b (dieses Dokument):** Konfigurations-Tabelle
  `workshop_beneficiary_sources_config` + Admin-UI + datengetriebener
  Auto-Harvester `services.scheduler.run_beneficiary_auto_harvest`.

## Ablauf

```
Admin-UI ──▶ /api/admin/beneficiary-sources (POST)
              │
              ▼
       BeneficiarySourceConfig
              │
              ├─▶ Test-Run (POST /test-run)
              │     ▶ Vorschau erste 10 Zeilen + Validation
              │     ▶ kein DB-Write
              │
              └─▶ Worker (cron, 02 UTC taeglich)
                    ▶ download(source_url)
                    ▶ sha256 vs last_seen_sha256: gleich → skip
                    ▶ run_beneficiary_harvest(smart-mode)
                    ▶ Audit-Backup nach data/beneficiaries/raw/<source_key>/
                    ▶ last_seen_sha256, record_count, quality updaten
```

## Tabellen

### `workshop_beneficiary_sources_config`

| Spalte | Typ | Bedeutung |
|---|---|---|
| `source_key` | varchar(120) PK | Slug `[a-z0-9_-]+`, identifiziert die Quelle. |
| `display_name` | varchar(200) | Anzeige-Label im UI. |
| `bundesland`, `fonds`, `periode` | varchar | Filterhilfen — werden in `BeneficiaryRecord` mitgegeben. |
| `country_code` | varchar(3) | ISO-2 (DE/AT). |
| `source_type` | enum | `xlsx_url` \| `csv_url` \| `manual_upload`. |
| `source_url` | varchar(500) | Bei `*_url`: URL der Datei. |
| `update_frequency_days` | int | Default 30. |
| `field_mapping` | jsonb | `{kanonisch: xlsx_header}`. Default: NULL → Pattern-Detection greift. |
| `required_fields` | jsonb | Liste kanonischer Aliase, die im Test-Run als Pflicht geprueft werden. |
| `validations` | jsonb | Liste `{field, regex, message}`. |
| `enabled` | bool | Soft-Disable. |
| `last_successful_harvest_at` | timestamp | Vom Worker gepflegt. |
| `last_seen_sha256` | varchar(64) | Inhalts-Hash der zuletzt gesehenen Datei. |
| `record_count`, `quality` | int / enum | Vom Worker gepflegt. |

## Endpoints (Admin-only)

Alle unter `/api/admin/beneficiary-sources`:

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/` | Liste aller Configs. |
| GET | `/{source_key}` | Eine Config. |
| POST | `/` | Neue Config anlegen. |
| PUT | `/{source_key}` | Config updaten (PATCH-Semantik). |
| DELETE | `/{source_key}` | Soft-Disable (`enabled=false`). |
| POST | `/{source_key}/test-run` | Test-Harvest ohne DB-Write. |
| POST | `/{source_key}/harvest` | Manueller Trigger (smart/full-refresh/force). |
| GET | `/{source_key}/runs` | Letzte 10 Harvest-Runs. |

## Self-Service-Workflow (Admin-UI)

1. **Sidebar:** "Quellen-Verwaltung" (nur fuer Admins sichtbar) oeffnet
   `/admin/beneficiary-sources`.
2. **Neue Quelle anlegen:** Plus-Button oben rechts oeffnet ein Modal mit
   Slug, Anzeigename, Bundesland/Fonds/Periode/Country, Source-Typ + URL.
3. **Test-Run:** Klick auf eine Quelle oeffnet einen Drawer. Im Tab
   "Test-Run" eine XLSX hochladen — die Vorschau zeigt erkannte Felder +
   erste 10 Zeilen + Validation-Findings. Kein DB-Write.
4. **Field-Mapping korrigieren:** Tab "Field-Mapping" — pro kanonischem
   Alias kann der Admin den exakten XLSX-Header eintragen (oder leer
   lassen, dann greift die Pattern-Detection).
5. **Validations:** Tab "Field-Mapping" → Abschnitt unten. Pro Regel
   `{field, regex, message}`.
6. **Enable + Speichern:** Speichern-Button oben. Sobald `enabled=true`
   und `source_type` auf `xlsx_url`/`csv_url` umgestellt ist, holt der
   Worker die Quelle taeglich.
7. **Manueller Harvest (jetzt):** Tab "Konfiguration" → Aktionen →
   "Harvest jetzt". Optional Datei mit-hochladen.
8. **Run-History:** Tab "Run-History" — letzte 20 Laeufe mit Status,
   Counts, Trigger und Fehler.

## Beispiel-Config

```json
{
  "source_key": "hessen_efre_2021_2027",
  "display_name": "Hessen · EFRE · 2021-2027",
  "bundesland": "Hessen",
  "fonds": "EFRE",
  "periode": "2021-2027",
  "country_code": "DE",
  "source_type": "xlsx_url",
  "source_url": "https://wibank.de/transparenzliste-efre.xlsx",
  "source_landing_page": "https://wibank.de/transparenz",
  "update_frequency_days": 30,
  "license": "dl-de/by-2-0",
  "sheet_name": "Vorhaben",
  "header_row": 0,
  "field_mapping": {
    "name": "Name des Begünstigten",
    "projekt": "Bezeichnung des Vorhabens",
    "aktenzeichen": "Förderkennzeichen",
    "kosten": "Gesamtkosten des Vorhabens"
  },
  "required_fields": ["name", "kosten"],
  "validations": [
    {"field": "cost_total_raw", "regex": "^\\d", "message": "Kostenwert muss numerisch starten"}
  ],
  "enabled": true,
  "notes_for_pruefer": "Liste wird quartalsweise aktualisiert."
}
```

## Worker-Verhalten

- **Cron-Slot:** `BENEFICIARY_AUTO_HARVEST_HOUR` (Default = `NIGHTLY_BATCH_HOUR`,
  also 02 UTC).
- **Faelligkeit:** Pro Quelle wird `last_successful_harvest_at +
  update_frequency_days` mit `now()` verglichen. Erst-Harvest (last=NULL)
  ist immer faellig.
- **SHA-Skip:** Inhalts-Hash der heruntergeladenen Datei wird gegen
  `last_seen_sha256` verglichen — gleich → kein Harvest, nur
  `last_successful_harvest_at` wird hochgesetzt.
- **Audit-Backup:** Original-Bytes werden nach
  `BENEFICIARY_RAW_DIR/<source_key>/<ISO-Timestamp>_<filename>.xlsx`
  geschrieben. Audit-Spur in die Quell-Datei.
- **Smart-Mode:** Insert-Strategie ist `ON CONFLICT DO NOTHING` — neue
  Records werden ergaenzt, bestehende bleiben unangetastet.
- **Status-Update:** Nach erfolgreichem Lauf wird die Config-Zeile mit
  `last_seen_sha256`, `last_successful_harvest_at`, `record_count`,
  `quality` aktualisiert.

## ENV-Vars

| Name | Default | Beschreibung |
|---|---|---|
| `ENABLE_BENEFICIARY_AUTO_HARVEST` | true | Worker an/aus. |
| `BENEFICIARY_AUTO_HARVEST_HOUR` | `NIGHTLY_BATCH_HOUR` (02) | Stunden-Slot UTC. |
| `BENEFICIARY_RAW_DIR` | `/app/data/beneficiaries/raw` | Audit-Backup-Verzeichnis. |
| `BENEFICIARY_HTTP_TIMEOUT` | 180 | Sekunden pro Quelle. |

## Tests

- `backend/tests/test_beneficiary_sources_config.py` — CRUD, Test-Run,
  Harvest, Run-History (Integrationstests gegen Backend).
- `backend/tests/test_beneficiary_auto_harvest.py` — Worker-Logik
  (Faelligkeit, SHA-Skip, Audit-Archive) ohne Netzwerk/DB.

## Migration

Beim Backend-Start (Lifespan) wird `workshop_beneficiary_sources_config`
einmalig aus den existierenden Legacy-DataFrame-Tabellen geseeded — pro
Source ein Eintrag mit `source_type=manual_upload`, `enabled=true`,
`field_mapping=NULL`. Der Admin kann sie spaeter ueber die UI auf
`xlsx_url` umstellen und das Mapping pflegen.

## Sicherheitshinweise

- Endpoints sind alle `require_admin` — Moderatoren haben keinen Zugriff.
- `source_key` wird per Regex-Slug (`^[a-z0-9_-]+$`) validiert — kein
  SQL-Injection-Risiko ueber Pfad-Parameter.
- Audit-Archivierung saeubert Filenames (nur `[a-zA-Z0-9._-]`) — kein
  Path-Traversal.
- DELETE ist Soft-Disable, kein Hard-Delete: damit der `last_seen_sha256`
  beim spaeteren Re-Enable nicht verloren geht und der Worker keinen
  unnoetigen Re-Harvest macht.
