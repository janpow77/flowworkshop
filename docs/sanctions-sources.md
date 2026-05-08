# Multi-Source-Sanktionslisten

Stand: 2026-05-08 (Phase 6c — DB-backed)

Das Workshop-Backend pflegt einen lokalen In-Memory-Index ueber mehrere
internationale Sanktionslisten und bietet darueber Fuzzy-Suche, aggregierte
Statistik und tagliche Auto-Refreshes. Alle Quellen kommen einheitlich
ueber OpenSanctions (`targets.simple.csv`-Schema) und werden in einer
einzigen Postgres-Tabelle `workshop_sanctions_entries` persistiert.
Die CSVs unter `/app/data/sanctions/<key>_targets.csv` sind nur noch
Download-Cache + Erst-Befuellungs-Quelle.

## Lokal indexierte Quellen

| Source-Key         | Liste                                          | Herausgeber                       | Lizenz                                      |
|--------------------|------------------------------------------------|-----------------------------------|---------------------------------------------|
| `eu_fsf`           | EU Konsolidierte Finanzsanktionsliste (FSF)    | Europaeische Kommission           | CC BY 4.0                                   |
| `un_sc`            | UN Security Council Consolidated List          | UN-Sicherheitsrat                 | Public Domain                               |
| `us_ofac_sdn`      | OFAC SDN List                                  | U.S. Treasury — OFAC              | Public Domain                               |
| `gb_hmt_sanctions` | UK FCDO/OFSI Consolidated List                 | UK FCDO / HM Treasury OFSI        | Crown Copyright (UK Open Government Licence)|
| `ch_seco`          | SECO Schweizer Sanktionsliste                  | SECO Schweiz                      | Public Domain                               |

URL-Schema: `https://data.opensanctions.org/datasets/latest/<dataset>/targets.simple.csv`.

OpenSanctions-Datasets (abweichend vom internen Source-Key):

| Source-Key (intern) | OpenSanctions-Dataset      |
|---------------------|----------------------------|
| `eu_fsf`            | `eu_fsf`                   |
| `un_sc`             | `un_sc_sanctions`          |
| `us_ofac_sdn`       | `us_ofac_sdn`              |
| `gb_hmt_sanctions`  | `gb_fcdo_sanctions`        |
| `ch_seco`           | `ch_seco_sanctions`        |


## Architektur

### DB-Backed-Pattern (Phase 6c)

```
            +----------------+      +----------------+
            |  OpenSanctions |      |   PostgreSQL   |
            | targets.simple |      | workshop_sanc- |
            |  CSV-Download  |      | tions_entries  |
            +-------+--------+      +--------+-------+
                    |                        ^
   refresh_all() -->|                        |
                    v                        |
            +-------+----------+   upsert   +--+
            | download_csv()   |----------> |  |
            +-------+----------+            |  |
                    |                       |  |
                    | load_from_csv_to_db   |  |
                    +---------------------->+  |
                                            |  |
                    +-----------------------+--+
                    | load_index_from_db()
                    v
            +----------------+
            | In-Memory      |   <-- search()
            | rapidfuzz-Index|       (rapidfuzz token_set_ratio)
            +----------------+
```

- **DB ist Source-of-Truth** (Audit, Persistierung, refresh_run_id-FK).
- **In-Memory ist Hot-Path** — Search laeuft auf den 39k+ Eintraegen via
  rapidfuzz, nicht ueber SQL (waere fuer Token-Set-Ratio zu langsam).
- Beim Lifespan-Start liest `MultiSanctionsService.load_all()` aus der
  DB (`load_index_from_db`). Wenn die DB-Tabelle leer ist (Erststart oder
  frische Migration), wird die CSV in die DB upsertet und der Index
  daraus gebaut — der naechste Start ist reiner DB-Read.

### Komponenten

`services/sanctions_service.py`:

- `SanctionsSource` (dataclass): Metadaten einer Quelle (Key, Name, URL, CSV-Pfad,
  License). Per ENV pro Quelle ueberschreibbar (`<KEY>_CSV_PATH`,
  `<KEY>_DOWNLOAD_URL` — z.B. `UN_SC_CSV_PATH`, `US_OFAC_SDN_DOWNLOAD_URL`).
- `SanctionsListIndex`: In-Memory-Index ueber eine einzelne Quelle. Wird per
  `load_from_records()` aus DB-Daten gefuellt (oder per `load(csv_path)` aus
  CSV — Fallback fuer Tests). `search()` liefert `SanctionsHit`-Treffer
  mit `source_key` und `source_display_name`.
- `MultiSanctionsService(use_db=True)`: Singleton-Container, der den DB-
  Pfad nutzt. Bietet `load_all()`, `search(query, sources=...)`, `stats()`,
  `refresh_all(refresh_run_id=...)` und `refresh_source(key, refresh_run_id=...)`.
  Tests koennen weiterhin `MultiSanctionsService(...)` ohne DB instanziieren
  (`use_db=False` Default), dann lauft alles in-memory ueber die CSV.
- Modul-Funktionen:
  - `load_from_csv_to_db(db, source_key, csv_path, refresh_run_id=...)`:
    liest CSV, `ON CONFLICT (source_key, entry_id) DO UPDATE`-Upsert in
    `workshop_sanctions_entries`.
  - `load_index_from_db(db, source) -> SanctionsListIndex`: streamt alle
    Eintraege einer Quelle aus der DB in einen frischen In-Memory-Index.
  - `download_csv(source) -> int`: lediglich der HTTP-Download.
- `FsfIndex` ist ein Backward-Compat-Alias auf `SanctionsListIndex`.
  `get_index()` liefert weiterhin den `eu_fsf`-Index — Bestandscode
  (FlowInvoice, audit_designer) muss nicht angepasst werden.

`models/sanctions_entries.py`:

- `SanctionsEntry`: kanonisches Schema mit Originalwerten verbatim.
  `name_normalized` wird per `normalize_name()` befuellt, damit
  pg_trgm-Indizes funktionieren. `aliases` und `raw_payload` sind JSONB.
  Eindeutigkeit ueber `(source_key, entry_id)`.
- `refresh_run_id`: FK auf `workshop_sanctions_refresh.id` — bei jedem
  Upsert wird der aktive Lauf gesetzt, damit ueber die Audit-Tabelle
  nachvollziehbar ist, in welchem Lauf welcher Eintrag dazu kam.

## API-Endpunkte (`/api/sanctions/`)

| Endpunkt                | Methode | Beschreibung                                              |
|-------------------------|---------|-----------------------------------------------------------|
| `/lists`                | GET     | Statische Cards-Definition (alle dokumentierten Listen)   |
| `/sources`              | GET     | Status aller lokal indexierten Quellen (Per-Source)       |
| `/method`               | GET     | Methodische Erlaeuterung der Fuzzy-Suche                  |
| `/stats`                | GET     | Aggregierte Stats + Per-Source-Breakdown                  |
| `/search`               | GET     | Multi-Source-Fuzzy-Suche, Filter via `sources=eu_fsf,un_sc`|
| `/refresh`              | POST    | Refresh aller Quellen oder einzelner via `?source_key=...`|

`GET /search` Parameter:
- `q` (required, min 2 Zeichen)
- `limit` (default 15, max 50)
- `min_score` (default 65.0, 40..100)
- `schema_filter` (`Person` | `Organization`)
- `sources` (optional, Komma-Liste der Source-Keys; Default = alle aktivierten)

`POST /refresh` (Admin-only):
- ohne Parameter → `refresh_all()` (alle Quellen sequenziell)
- `?source_key=<key>` → nur diese Quelle

## Lifespan + Auto-Refresh

`main.py` Lifespan ruft `sanctions_service.warmup()` auf, das den
Multi-Service initialisiert und `load_all()` aufruft. Pro Quelle wird:

1. Der In-Memory-Index aus `workshop_sanctions_entries` aufgebaut
   (kein CSV-IO im Hot-Path).
2. Wenn die DB-Tabelle fuer die Quelle leer ist und die CSV vorliegt,
   wird die CSV in die DB upsertet und der Index daraus gebaut. Der
   naechste Start ist reiner DB-Read.
3. Wenn weder DB noch CSV vorliegen, bleibt der Index leer
   (`loaded=False` im /sources-Endpoint). `MultiSanctionsService.has_missing_csvs()`
   triggert einen asynchronen Background-Task `run_sanctions_refresh()`,
   der die fehlenden Quellen nachzieht — typische Laufzeit < 2 min fuer
   alle 5 Quellen.

Damit ist die Workshop-Demo nach dem ersten Container-Start automatisch
mit allen Listen versorgt, ohne dass der Pruefer manuell `refresh`-Calls
ausloesen muss.

### Erst-Migration: Backfill aus existierenden CSVs

Wenn die CSVs bereits unter `/app/data/sanctions/<key>_targets.csv`
liegen, der Container aber zum ersten Mal mit dem neuen Schema startet,
wird die DB-Tabelle automatisch durch `load_all()` befuellt. Alternativ
laeuft das Backfill-Skript als One-Shot:

```bash
docker exec auditworkshop-backend python scripts/backfill_sanctions_entries.py
```

Idempotent ueber `ON CONFLICT (source_key, entry_id) DO NOTHING` — ein
zweiter Lauf liefert `records_inserted == 0`. Mit `--source-key eu_fsf`
laesst sich eine einzelne Quelle nachfuellen, mit `--dry` wird nur
gezaehlt.

## Scheduler (Daily Refresh)

`services/scheduler.py · run_sanctions_refresh()`:

- Legt einen `SanctionsRefreshRun` (status=`running`) vorab an.
- Liest Pre-Stats aller Quellen (rows_before, persons_before, sha256_old).
- Ruft `MultiSanctionsService.refresh_all(refresh_run_id=run.id)` auf.
  Pro Quelle: Download CSV → `load_from_csv_to_db()` (Upsert mit
  `refresh_run_id` als FK) → `load_index_from_db()` (In-Memory-Rebuild).
- Aktualisiert den Run mit den finalen Stats (status, rows_before/after,
  sources, parameters JSON mit Per-Source-Subreport).
- Ist resilient: einzelne Quellen-Fails fuehren zu Status `partial`, der
  Run wird trotzdem persistiert. Der `refresh_run_id` ist auf jedem
  upsertten Eintrag gesetzt — damit ist nachvollziehbar, in welchem Lauf
  welcher Eintrag das letzte Mal beruehrt wurde.

Der tagliche Auto-Refresh laeuft im `NIGHTLY_BATCH_HOUR`-Slot (Default
02:00 UTC = 04:00 CEST). ENV-Override: `SANCTIONS_REFRESH_HOUR`.

## Audit-Report-Integration

`services/state_aid_audit_report.py` nutzt `MultiSanctionsService.search()`
fuer die Sanctions-Sektion:

- `total_hits`: Summe ueber alle Quellen
- `hits[]`: Top-20 aggregiert nach Score, jeder Hit mit `source_key` +
  `source_display_name`
- `listing_sources`: alle Quellen, in denen Treffer vorkamen

Die PDF-Tabelle (`state_aid_audit_pdf.py`) zeigt eine Spalte `Quelle`
mit Kuerzeln (`EU FSF`, `UN SC`, `OFAC`, `UK OFSI`, `SECO`).

`data_freshness.sanctions` und `sources_explanation` sind ebenfalls
Multi-Source-aware (juengste mtime ueber alle Quellen, aggregierte
Record-Zahl, Liste der lokal geladenen Source-Keys).

## Datenbank-Migrationen

Idempotent in `main.py` Lifespan:

- `workshop_sanctions_refresh.sources` (VARCHAR(255)) — Komma-Liste der
  refreshten Source-Keys.
- `workshop_sanctions_refresh.parameters` (JSON) — Per-Source-Subreport.
- Phase 6c: `workshop_sanctions_entries`-Tabelle (von SQLAlchemy auto-
  angelegt). Zusaetzliche Indizes:
  - `ix_sanctions_name_trgm` (GIN trgm auf `name_normalized`) — fuer
    Postgres-seitige Fuzzy-ILIKE-Voraussortierung.
  - `ix_sanctions_aliases_gin` (GIN auf JSONB `aliases`) — fuer
    Containment-Suche `aliases @> '"Foo"'`.
  - `uq_sanctions_source_entry` (UNIQUE auf `source_key, entry_id`) —
    Voraussetzung fuer `ON CONFLICT`-Upserts.
  - Idempotente ALTER COLUMN auf `birth_date`/`first_seen`/`last_seen`
    von VARCHAR(40) auf TEXT (OpenSanctions liefert teils
    semikolongetrennte Mehrfachwerte > 40 Zeichen).

## Backward-Compatibility

- `FsfIndex` ist ein Alias auf `SanctionsListIndex`.
- `get_index()` liefert weiterhin den `eu_fsf`-Index — kein Refactoring
  von Bestandscode noetig.
- `FSF_CSV_PATH`, `FSF_DOWNLOAD_URL` Module-Konstanten bleiben erhalten.
- Das Antwortschema von `GET /search` enthaelt zusaetzlich
  `source_key`, `source_display_name` und `sources_searched` —
  alte Felder unveraendert.

## Tests

`tests/test_sanctions_multi.py` (16 Tests, ohne Netzwerk/DB):

- `test_default_sources_have_five_entries`
- `test_default_sources_have_required_fields`
- `test_single_index_loads_synthetic`
- `test_single_index_search_with_source_key`
- `test_multi_service_loads_all`
- `test_multi_service_search_aggregates`
- `test_multi_service_search_filter_by_sources`
- `test_multi_service_search_unknown_source_filter_returns_empty`
- `test_multi_service_search_orders_by_score`
- `test_multi_service_missing_csv_does_not_crash`
- `test_multi_service_partial_load`
- `test_multi_service_stats_per_source_breakdown`
- `test_fsf_index_alias_still_works`
- `test_get_index_returns_eu_fsf_singleton`
- `test_normalize_name_strips_legal_suffix`
- `test_multi_service_search_empty_min_score_high`

`tests/test_sanctions_db_storage.py` (Phase 6c, 7 Tests, gegen lokale
Postgres im Container — auf Host-Test-Runs werden sie geskippt):

- `test_load_from_csv_to_db_inserts_rows` — CSV-Zeilen landen in
  `workshop_sanctions_entries`, Originalwerte verbatim, Aliases als
  JSONB-Liste.
- `test_load_index_from_db_rebuilds_records` — DB → In-Memory-Index
  reproduziert Stats korrekt.
- `test_search_consistency_csv_vs_db` — Suche auf DB-aufgebautem Index
  liefert gleiche Treffer wie auf CSV-aufgebautem Index.
- `test_refresh_run_id_propagates_to_entry` — `refresh_run_id` wird
  beim Upsert auf jeden Eintrag gesetzt.
- `test_smart_idempotency_second_run_no_new_rows` — zweiter Lauf
  fuegt 0 neue Zeilen ein, Tabelle waechst nicht.
- `test_backfill_source_idempotent` — Backfill-Skript ist idempotent
  (`records_inserted == 0`, `records_skipped == 3` beim 2. Lauf).
- `test_load_from_csv_to_db_skips_invalid_rows` — Zeilen ohne
  `id`/`name` werden als `records_skipped` gezaehlt.

Alle Tests gruen, Laufzeit < 300 ms (DB-Tests im Container, In-Memory-
Tests host-side).
