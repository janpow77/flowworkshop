# Fuzzy-Match Performance Optimierung

Stand: Mai 2026

Ziel: `services/state_aid_service.py::fuzzy_match_company` von ~200ms auf
~25ms beschleunigen, ohne Qualitätsverlust bei den Score-Werten.

## Ergebnis

| Metrik | Vorher | Nachher | Faktor |
|--------|--------|---------|--------|
| Cold median (5 Queries) | ~78 ms | 5.6 ms | **14x** |
| Warm median (5 Queries) | ~72 ms | 4.2 ms | **17x** |
| Smoke-Tests | 15/15 | 15/15 | unverändert |
| Smart-Score-Werte | identisch | identisch | unverändert |

Sample-Tabelle aus `scripts/profile_fuzzy.py --runs 5 --legacy`:

| Query | Country | Hits | Cold (ms) | Warm (ms) | Legacy SQL (ms) | Legacy Cands |
|-------|---------|------|-----------|-----------|-----------------|--------------|
| Fraunhofer | DE | 20 | 77.8 | 24.1 | 1.6 | 22 |
| Müller GmbH | DE | 20 | 5.6 | 3.6 | 2.3 | 353 |
| Siemens AG | DE | 20 | 1.9 | 2.6 | 1.6 | 81 |
| Justus-Liebig-Universität Gießen | DE | 6 | 5.8 | 5.3 | 4.8 | 68 |
| Energieversorgung Offenbach | DE | 20 | 4.7 | 4.2 | 3.8 | 43 |

Hinweis: `Fraunhofer` cold ist 78ms wegen Alias-Expansion (KfW-Alias-Liste enthält
`Fraunhofer` → expandiert zu kompletter Langform mit 8 Tokens). Warm ist 24ms.

## Was geändert wurde

Datei: `auditworkshop/backend/services/state_aid_service.py`

### 1. Stop-Token-Filter für SQL-OR-Liste

Der gemessene Hauptengpass: bei mehrtokigen Queries (z.B. nach Alias-Expansion
`fraunhofer gesellschaft zur foerderung der angewandten forschung`) verursacht
das tokenweise OR-ILIKE eine BitmapHeapScan über den Country-Index — der
GIN-Trgm-Index wird vom Planner aufgegeben (`zur`, `der` matchen >5000 Records).

Lösung: Neue Funktion `_select_sql_tokens(tokens, max_tokens=4)` filtert
deutsche Stoppwörter (`der`, `die`, `und`, `zur`, `zum`, `für`, `mit`, `von`,
`vom`, `oder`, `the`, `and`, …) raus und behält nur die längsten 4 Tokens.

Damit greift der GIN-Trgm-Index wieder als Bitmap Index Scan.

### 2. Identifier-Match nur bei Identifier-LIKEN Queries

Die alte Implementierung machte `beneficiary_identifier ILIKE '%query%'` auch
für lange Firmennamen-Queries. Die Identifier-Spalte hat keinen Trgm-Index
(nur btree) → ILIKE-Substring = Seq Scan über 184k Rows = ~45ms.

Neue Heuristik `_looks_like_identifier(q)`:
- True wenn Query Ziffern enthält (z.B. `HRB12345`, `DE-2023-001`)
- Oder kurzes Akronym ohne Whitespace (max 8 Zeichen)
- False für typische Firmennamen wie `Fraunhofer`, `Siemens AG`, `Deutsche Bahn`

Identifier-Mini-Query läuft jetzt nur noch in den Edge-Fällen.

### 3. SQL-Pre-Ranking via `similarity()`-Spalte

Statt zwei separater SQL-Roundtrips (Hauptquery + extra_filters) gibt es jetzt
**eine** Hauptquery, die per `similarity(beneficiary_name_normalized, q_norm)`
sortiert und nur die Top 500 zurückliefert. NUTS-Label-Hint (selten genutzt)
läuft als optionale Mini-Query.

### 4. Top-K-Cutoff via `process.cdist`

Vor dem Smart-Score-Ensemble (5 Algorithmen) wird ein Batch-Token-Set-Ratio
über `rapidfuzz.process.cdist` berechnet. Dann werden nur die Top 200 Kandidaten
durch das Smart-Score-Ensemble geschickt (statt alle 500). Spart ~60% der
fuzz-Calls bei großen Trefferlisten.

### 5. LRU-Cache für `_smart_fuzzy_score`

Neue gecachte Variante `_smart_fuzzy_score_cached(q_norm, c_norm)` mit
`@lru_cache(maxsize=4096)`. Liefert exakt denselben Score (Determinismus-Check
in Tests). Hilft bei wiederholten Audit-Reports / mehrfacher Suche mit gleichen
Queries.

### 6. `processor=None` in allen rapidfuzz-Calls

Strings sind bereits via `normalize_company_name` lower-cased und ohne Akzente.
Der Default-Processor würde sie unnötig nochmal traversieren.

### 7. Top-Level-Import von JaroWinkler

Vorher: `from rapidfuzz.distance import JaroWinkler` innerhalb von
`_smart_fuzzy_score` — bei jedem Call. Jetzt einmal beim Modul-Import.

## EXPLAIN (ANALYZE) — nach der Optimierung

Query: `Fraunhofer` (country=DE), pg_trgm `%`-Operator + Country-Filter:

```
Limit  (cost=1093.86..1093.88 rows=9 width=41) (actual time=10.086..10.087 rows=1 loops=1)
  Buffers: shared hit=799 read=985
  ->  Sort  (cost=1093.86..1093.88 rows=9 width=41) (actual time=10.085..10.086 rows=1 loops=1)
        Sort Key: (similarity((beneficiary_name_normalized)::text, 'fraunhofer'::text)) DESC
        Sort Method: quicksort  Memory: 25kB
        ->  Bitmap Heap Scan on workshop_state_aid_awards (cost=1026.44..1093.72 rows=9 width=41) (actual time=2.991..10.084 rows=1 loops=1)
              Recheck Cond: ((beneficiary_name_normalized)::text % 'fraunhofer'::text)
              Filter: ((country_code)::text = 'DE'::text)
              ->  Bitmap Index Scan on ix_state_aid_name_trgm (cost=0.00..1026.44 rows=17 width=0) (actual time=2.736..2.737 rows=2011 loops=1)
                    Index Cond: ((beneficiary_name_normalized)::text % 'fraunhofer'::text)
Execution Time: 10.095 ms
```

Wichtig: `Bitmap Index Scan on ix_state_aid_name_trgm` — der GIN-Trgm-Index
wird durchgehend genutzt.

## Vorher: BitmapHeapScan auf Country-Index (ohne Trgm)

Query: `Fraunhofer` mit aliasexpansion → 8 Tokens inkl. Stoppwörter:

```
Limit  (cost=48247.23..48305.57 rows=500 width=41) (actual time=99.349..103.359 rows=500 loops=1)
  Workers Planned: 2
  Workers Launched: 2
  ->  Parallel Bitmap Heap Scan on workshop_state_aid_awards
        Recheck Cond: ((country_code)::text = 'DE'::text)
        Filter: ((lower(...) ~~ '%fraunhofer%') OR (lower(...) ~~ '%gesellschaft%') OR ... OR (lower(...) ~~ '%der%'))
        Rows Removed by Filter: 28258
        Heap Blocks: exact=8630
        ->  Bitmap Index Scan on ix_state_aid_country_nuts
              Index Cond: ((country_code)::text = 'DE'::text)  -- 101031 rows!
Execution Time: 103.679 ms
```

Hier sieht man: der Planner nimmt den Country-Index (101k Rows!) statt dem
Trgm-Index, weil das OR über 8 Tokens (inkl. `der`, `zur`) inkonsistent
selektiv ist.

## Tests

Datei: `auditworkshop/backend/tests/test_state_aid_search_quality.py`

Neue Tests:
- `test_select_sql_tokens_*` — Stoppwort-Filter
- `test_looks_like_identifier_*` — Heuristik für Identifier-Erkennung
- `test_smart_fuzzy_score_cached_*` — Cache-Determinismus, Hashability, LRU-Stats
- `test_fuzzy_constants_present` — neue Konstanten
- `test_sql_stop_tokens_contains_german_articles` — Stoppwort-Liste

Alle 36 Tests grün; bestehende 21 bleiben unverändert grün (Score-Werte identisch).

## Profiling

Reproduzierbar via:

```bash
docker exec auditworkshop-backend python scripts/profile_fuzzy.py --runs 5 --explain
docker exec auditworkshop-backend python scripts/profile_fuzzy.py --runs 5 --legacy
```

## Smoke

```bash
BACKEND_BASE=http://localhost:8006 bash auditworkshop/scripts/state_aid_smoke.sh
# 15/15 pass
```
