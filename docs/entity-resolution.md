# Phase 6d — Entity-Resolution

Stand: Mai 2026

## Ziel

„Siemens AG" soll als **eine** kanonische Entity erfasst sein, mit FKs aus
allen drei Quell-Modulen (State-Aid, Beneficiaries, Sanctions). Damit wird
Cross-Reference im Audit-Report ein SQL-JOIN statt Python-Fuzzy-Lookup.

## Architektur — additive Schicht

Die Entity-Resolution ist eine **additive** Schicht ueber den drei Original-
Tabellen. Original-Daten bleiben unveraendert. Das Master-Layer ist jederzeit
neu aufzubauen (rebuild idempotent).

```
                ┌─────────────────────────────────────┐
                │      workshop_company_entities      │
                │        (Master-Tabelle)             │
                │ - canonical_name + _normalized      │
                │ - lei (UNIQUE)                      │
                │ - identifiers (JSONB)               │
                │ - addresses (JSONB)                 │
                │ - parent_entity_id, ultimate_parent │
                └──────────────┬──────────────────────┘
                               │ 1
                               │
                               │ n (UNIQUE source_module + source_record_id)
                               ▼
                ┌─────────────────────────────────────┐
                │       workshop_entity_matches       │
                │  source_module + source_record_id   │
                │  source_table (Audit-Trail)         │
                │  match_method, match_confidence     │
                │  match_evidence (JSONB)             │
                │  confirmed_by_user_id, rejected     │
                └──┬──────────┬──────────┬────────────┘
                   │          │          │
                   ▼          ▼          ▼
          state_aid_awards  beneficiary  sanctions_entries
            (Originale unveraendert — KEINE Schreibvorgaenge)
```

## Confidence-Klassen

Die Match-Strategie laeuft von hoch zu niedrig:

| Score | Method                | Beschreibung                                          |
| ----- | --------------------- | ----------------------------------------------------- |
| 100   | `lei`                 | LEI-Match (ISO 17442). Verbindlichster Identifier.    |
| 95    | `identifier`          | National-Identifier (HRB, Steuer-Nr.) im JSONB.       |
| 90    | `name_exact`          | Normalisierter Name identisch (`normalize_company_name`). |
| 75-89 | `name_fuzzy_<score>`  | rapidfuzz `max(token_set_ratio, WRatio)`.             |
| < 75  | (KEIN Match)          | Confidence zu unsicher — kein Eintrag in EntityMatch. |

Der Schwellwert 75 ist im Code fixiert (`CONFIDENCE_FUZZY_THRESHOLD`).

## Pruefer-Workflow

Nach automatischem Rebuild kann ein Pruefer manuell entscheiden:

| Aktion | Endpoint | Effekt |
| ------ | -------- | ------ |
| **Bestaetigen** | `POST /api/entities/{eid}/match/{mid}/confirm` | `confirmed_by_user_id` + `confirmed_at` werden gesetzt; `rejected = false`. |
| **Ablehnen** | `POST /api/entities/{eid}/match/{mid}/reject` | `rejected = true`. Audit-Trail bleibt erhalten — der Eintrag wird in der Search-API und Audit-Reports gefiltert (`rejected.is_(False)`). |

Rejected-Matches bleiben in der Tabelle (Audit-Spur), werden aber von allen
nachgelagerten Sichten ausgeblendet.

## Konzernverbund-Persistierung

Wenn `build_audit_report(... include_corporate_group=True)` aufgerufen wird,
laeuft die GLEIF/Wikidata-Konzern-Suche; das Ergebnis (Mutter, Tochter,
Direct/Ultimate-Parent) wird **persistent** in der Entity-Tabelle verankert:

```python
# In services.state_aid_audit_report.build_audit_report:
link_corporate_group_to_entities(db, corporate_group_obj)
```

Pro `CorporateEntity` aus der GLEIF-Antwort wird eine `CompanyEntity` per
LEI nachgeschlagen — bei Treffer aktualisiert; sonst neu angelegt. Die
Hierarchie (`parent_entity_id`, `ultimate_parent_entity_id`) wird gesetzt.

Damit waechst die Entity-Hierarchie im Workshop kontinuierlich mit jedem
Audit-Report-Bau.

## CLI: Rebuild

```bash
# Trockenlauf — zaehlt nur, schreibt nicht
docker exec auditworkshop-backend python scripts/rebuild_entity_resolution.py \
    --module all --dry

# Vollstaendiger Rebuild
docker exec auditworkshop-backend python scripts/rebuild_entity_resolution.py \
    --module all

# Nur State-Aid (~30k Entities aus 89k Awards)
docker exec auditworkshop-backend python scripts/rebuild_entity_resolution.py \
    --module state_aid

# Limit fuer schnelle Tests
docker exec auditworkshop-backend python scripts/rebuild_entity_resolution.py \
    --module state_aid --limit 1000
```

Rueckgabewert ist ein JSON-Dokument mit pro Modul:

```json
{
  "results": {
    "state_aid": {
      "records_seen": 89000,
      "records_skipped_existing": 0,
      "matches_created": 89000,
      "entities_created": 28452,
      "low_confidence_skipped": 0,
      "records_failed": 0
    }
  },
  "totals": {...}
}
```

## REST-API

### Public lesbar (Login erforderlich)

| Methode | Pfad                        | Zweck                                |
| ------- | --------------------------- | ------------------------------------ |
| GET     | `/api/entities/search?q=Siemens` | Master-Suche fuer Autocomplete  |
| GET     | `/api/entities/{id}`        | Detail mit Matches und Hierarchie    |

### Admin-only

| Methode | Pfad                        | Zweck                                |
| ------- | --------------------------- | ------------------------------------ |
| POST    | `/api/entities/{eid}/match/{mid}/confirm` | Bestaetigen      |
| POST    | `/api/entities/{eid}/match/{mid}/reject`  | Ablehnen         |
| POST    | `/api/admin/entity-resolution/rebuild?module=...` | Rebuild  |

### Beispiel: Search

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  'http://localhost:8006/api/entities/search?q=Siemens&limit=5'
```

Response:

```json
{
  "count": 1,
  "results": [
    {
      "id": 12345,
      "canonical_name": "Siemens AG",
      "canonical_name_normalized": "siemens",
      "entity_type": "company",
      "country_code": "DEU",
      "lei": "W38RGI023J3WT1HWRP41",
      "match_count": 3,
      "has_state_aid": true,
      "has_beneficiary": true,
      "has_sanctions": false
    }
  ]
}
```

## Audit-Report-Integration

Das Feld `entity_resolution` der `AuditReportData` enthaelt die kanonische
Master-Entity, die dem Suchbegriff entspricht. Cross-References im Bericht
bekommen ein zusaetzliches `entity_id` in ihrer `evidence`-Sektion, damit
JSON-Konsumenten direkt joinen koennen.

Beispiel-Sektion `entity_resolution`:

```json
{
  "entity_id": 12345,
  "canonical_name": "Siemens AG",
  "lei": "W38RGI023J3WT1HWRP41",
  "country_code": "DEU",
  "identifiers": {
    "hrb": ["HRB 6684 Berlin", "HRB 12300 München"]
  },
  "addresses": [
    {"city": "München", "postal_code": "80333", "country": "DEU", "source": "beneficiary"}
  ],
  "aliases": [
    "Siemens Aktiengesellschaft",
    "SIEMENS AG"
  ],
  "parent_entity_id": null,
  "ultimate_parent_entity_id": null,
  "matches_total": 14,
  "matches_state_aid": 8,
  "matches_beneficiary": 5,
  "matches_sanctions": 1
}
```

## Wichtige Garantien

- **Originale unveraendert.** Keine Schreibvorgaenge in `workshop_state_aid_awards`,
  `workshop_beneficiary_records`, `workshop_sanctions_entries`.
- **EntityMatch ist UNIQUE pro Source-Record.** Ein Original-Record kann nur
  genau einer Entity zugeordnet sein. Die UNIQUE-Constraint auf
  `(source_module, source_record_id)` macht die Zuordnung idempotent.
- **Rejected-Matches** bleiben als Audit-Trail erhalten, werden aber von der
  Search-API und vom Audit-Report gefiltert.
- **Confidence-Schwelle 75.** Darunter wird kein Match angelegt — der Pruefer
  kann ueber die Detail-UI manuell zuordnen.
- **Rebuild idempotent.** Zweiter Aufruf bei gleichen Daten erzeugt
  `matches_created == 0` und `entities_created == 0`.

## Nightly LLM-Verifikations-Batch (Layer C)

Layer C ist die `cron`-getriggerte Variante des LLM-Re-Rankers (`services/audit_match_verifier.py`,
„Layer B") — er prueft naechtlich bis zu **500 EntityMatches** mit niedriger
Confidence (75-89) automatisch durch das LLM und vor-stempelt sie als
`confirmed`/`rejected`. Damit hat der Audit-Report am naechsten Tag deutlich
weniger Live-LLM-Latenz (Layer B muss nicht alles neu pruefen).

### Was wird verifiziert?

- `match_confidence` zwischen 75 und 89 (ambivalente Fuzzy-Matches)
- `created_at > now() - 48h` (nur juenge Matches; alte sollten manuell sein)
- `confirmed_by_user_id IS NULL AND rejected = FALSE` (noch nicht entschieden)
- `match_evidence` enthaelt **noch keinen** `llm_verdict`-Eintrag
  (Idempotenz: zweiter Run skippt)

Sortierung: `ORDER BY created_at DESC, id DESC` (neueste zuerst), `LIMIT 500`.

### Was passiert bei welchem Verdict?

| Verdict | Confidence | Effekt auf EntityMatch |
| ------- | ---------- | ---------------------- |
| `yes`   | >= 85      | `confirmed_by_user_id = 'system:llm_batch'`, `confirmed_at = now()`, `rejected = false` |
| `yes`   | < 85       | nur `evidence['llm_verdict']` — Pruefer muss manuell entscheiden |
| `no`    | (egal)     | `rejected = true` |
| `unknown` | (egal)   | nur `evidence['llm_verdict']` — bleibt offen fuer Pruefer |

Die Auto-Confirm-Schwelle 85 ist bewusst strenger als der Layer-B-Default (80),
weil der Pruefer im Audit-Report nicht mehr live mitschaut.

### Konfiguration (Env-Variablen)

| Variable | Default | Zweck |
| -------- | ------- | ----- |
| `ENABLE_ENTITY_MATCH_LLM_BATCH` | `true` | Cron-Schalter |
| `ENTITY_MATCH_LLM_BATCH_HOUR` | `NIGHTLY_BATCH_HOUR + 1` (= 03 UTC) | Stundenfenster |
| `ENTITY_MATCH_LLM_BATCH_MAX` | `500` | Max Matches pro Lauf |
| `ENTITY_MATCH_LLM_BATCH_RECENT_HOURS` | `48` | Lookback-Fenster |
| `ENTITY_MATCH_LLM_BATCH_TIMEOUT_S` | `30.0` | Per-Call-Timeout in Sekunden |

Globaler Hard-Cap: 2 h (`overall_timeout_s=7200`). Bei Erreichen gilt
`status='partial'`, restliche Matches bleiben fuer den naechsten Lauf.

### Manuelle Trigger

```bash
# CLI: nur Eligible anzeigen, kein DB-Write, kein LLM-Call:
docker exec auditworkshop-backend \
  python scripts/entity_match_llm_batch.py --dry --max 5

# CLI: Vollbatch (500 Matches der letzten 48 h):
docker exec auditworkshop-backend \
  python scripts/entity_match_llm_batch.py

# Admin-API: synchroner Trigger (Body optional)
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"max_matches": 50, "only_recent_hours": 168}' \
  http://localhost:8006/api/admin/entity-resolution/llm-verify-batch

# Audit-Trail der letzten 20 Runs:
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8006/api/admin/entity-resolution/llm-runs?limit=20
```

### Recovery-Strategie

- Run mit `status='failed'` blockiert nicht — der naechste Tages-Slot startet
  einen neuen Lauf. Der Scheduler-Guard (22 h) verhindert zwei `cron`-Laeufe
  am selben Tag, aber `admin:<uid>`-Trigger sind jederzeit moeglich.
- Bei OOM/Crash bleibt das Zwischenstand-Commit (alle 50 Records) erhalten;
  schon-verifizierte Matches werden im naechsten Lauf via `evidence['llm_verdict']`
  ausgefiltert.
- Bei Fehl-Verdicts kann der Pruefer manuell ueberschreiben:

```bash
# Auto-Confirm zurueckziehen (rejected=true):
curl -X POST -H "Authorization: Bearer $TOKEN" \
  http://localhost:8006/api/entities/{eid}/match/{mid}/reject

# Pruefer-Confirm setzen, ueberschreibt 'system:llm_batch':
curl -X POST -H "Authorization: Bearer $TOKEN" \
  http://localhost:8006/api/entities/{eid}/match/{mid}/confirm
```

### Audit-Trail in der DB

Tabelle `workshop_entity_match_llm_runs`:

| Spalte | Inhalt |
| ------ | ------ |
| `id` | BigInt PK |
| `started_at` / `finished_at` | Lauf-Zeitfenster |
| `triggered_by` | `cron` / `admin:<uid>` / `cli` |
| `status` | `running` / `ok` / `partial` / `failed` |
| `total_eligible` | Wie viele Matches wuerden in Frage kommen |
| `total_verified` | Wie viele wurden tatsaechlich vom LLM gerated |
| `matches_confirmed` | `yes` + Confidence >= 85 |
| `matches_rejected` | `no`-Verdicts |
| `matches_unknown` | `unknown` oder `yes` mit Confidence < 85 |
| `skipped_due_to_timeout` | Bei Overall-Timeout |
| `parameters` | `BatchVerifyParams` als JSON |
| `error_message` | bei `failed` |

Pro Verdict zusaetzlich ein Eintrag in `workshop_llm_question_log`
(Wiederverwendung der Layer-B-Logging-Funktion `log_verdict_to_db`).
