# Layer A — Embedding-Index (bge-m3) ueber alle Module

Stand: Mai 2026

## Ziel

Bislang verbindet **Fuzzy-Match** (`rapidfuzz`) die drei Module State-Aid,
Beneficiaries und Sanctions. Das findet syntaktisch aehnliche Namen, aber
keine semantischen Verwandtschaften. Mit dem **Embedding-Index** ueber alle
Beneficiary-, Project- und Sanctions-Records wird semantische Suche moeglich:
„Klimaschutz-Projekte in Bayern" findet auch Records ohne diese Keywords.

## Architektur — additive Schicht

Layer A ist eine **additive** Schicht ueber den drei Original-Tabellen plus
der Master-Entity-Tabelle aus Phase 6d. Original-Daten bleiben unveraendert.
Der Index ist jederzeit neu aufzubauen (Rebuild idempotent).

```
                ┌─────────────────────────────────────┐
                │   workshop_entity_embeddings        │
                │   (bge-m3 Vector(1024))             │
                │ - source_module (str)               │
                │ - source_record_id (str)            │
                │ - text_input (Audit/Debug)          │
                │ - embedding (Vector 1024 Dim.)      │
                │ - model_name                        │
                │   UNIQUE(source_module, record_id)  │
                │   IVFFlat-Cosine-Index (lists=100)  │
                └──────────────┬──────────────────────┘
                               │
                               ▼  module = source_module
          ┌────────────────────┴────────────────────┐
          │                                         │
   state_aid_awards   beneficiary_records   sanctions_entries   company_entities
   (Originale unveraendert — KEINE Schreibvorgaenge)
```

Die Embeddings kommen aus dem **egpu-manager Gateway** (bge-m3, 1024 Dim,
multilingual, gut fuer DE/EN-Mix). Im Backend-Container laeuft kein lokales
Embedding-Modell — der Gateway wird ohnehin schon fuer `knowledge_service`
genutzt.

## Embedding-Text pro Modul

| Modul             | Felder                                                              |
| ----------------- | ------------------------------------------------------------------- |
| `state_aid`       | `beneficiary_name | aid_objective | granting_authority`             |
| `beneficiary`     | `beneficiary_name | project_name | project_description`             |
| `sanctions`       | `name | aliases (joined) | sanctions_program`                       |
| `company_entity`  | `canonical_name | addresses[0].city`                                |

Leere Felder werden uebersprungen, kein Trenner-Padding.

## Initial-Build und Rebuild

```bash
# Schnelle Validierung (100 Records, kein Schreibvorgang)
python scripts/rebuild_embeddings.py --module state_aid --limit 100 --dry

# Live-Build, batchweise
python scripts/rebuild_embeddings.py --module state_aid --batch-size 50 --limit 100

# Initial-Build aller Module — im Hintergrund
docker exec -d auditworkshop-backend \
    python scripts/rebuild_embeddings.py --module all --batch-size 50

# Modell-Wechsel: alle Embeddings neu berechnen
python scripts/rebuild_embeddings.py --module all --force-update
```

Idempotenz: `--skip-existing` (Default true) ueberspringt bereits eingebettete
Records. Ein zweiter Lauf mit denselben Daten ergibt `inserted == 0`.

## Performance-Anker

| Groesse                                        | Wert                  |
| ---------------------------------------------- | --------------------- |
| Initial-Build aller 180k Records (eGPU)         | ~30 min               |
| Pro Suche (IVFFlat + Cosine)                    | <100 ms               |
| Speicher-Footprint (180k × 1024 × 4 Byte)        | ~700 MB + IVFFlat-Overhead |
| Modell                                          | bge-m3 (1024 Dim)     |
| Backend                                         | egpu-manager Gateway  |

`lists=100` im IVFFlat-Index ist eine bewaehrte Voreinstellung fuer den
gegebenen Datenbestand. Bei deutlich groesseren Datensaetzen (>1 Mio.) waere
`sqrt(N)` als Faustregel zu nehmen.

## API

### Public lesbar

- `GET /api/embeddings/search?q=...&module=state_aid|beneficiary|sanctions|company_entity|all&limit=20&min_similarity=0.7`
  — Top-N semantisch aehnliche Records inkl. `cosine_similarity`.
- `GET /api/embeddings/stats` — Pro Modul Anzahl Embeddings, Coverage% gegen
  Quell-Records, letztes Update.

### Admin-only

- `POST /api/embeddings/rebuild?module=...&batch_size=50&skip_existing=true`
  — Triggert einen Rebuild SYNCHRON. Bei grossen Bestaenden besser ueber das
  CLI-Skript im Hintergrund laufen lassen.

## Integration in den Audit-Report

Der Cross-Register-Pruefbericht (`services/state_aid_audit_report.py`) hat
einen neuen Parameter:

```python
build_audit_report(
    db, query,
    include_semantic_neighbors=True,
    semantic_neighbors_top_n=5,
    semantic_min_similarity=0.7,
)
```

Wenn `True`, werden nach den klassischen Cross-References zusaetzlich die
top-5 **semantisch aehnlichsten** Records pro Modul als Cross-References
gefuehrt — mit den neuen Typen:

- `semantic_neighbor_state_aid`
- `semantic_neighbor_beneficiary`
- `semantic_neighbor_sanctions`

Das PDF rendert sie in einer eigenen Sektion **„Semantische Nachbarschaft"**
mit dem expliziten Hinweis:

> Diese Records wurden vom KI-Embedding als aehnlich erkannt — kann Hinweis
> auf verwandte Vorgaenge sein, ist aber kein Identitaets-Beweis.

Die `Evidence`-Felder enthalten `cosine_similarity`, `original_record_id`,
`text_input` (Audit-Spur, was wurde embeddet) und `model_name`.

## Lifespan

Der Lifespan in `main.py` legt nur die Tabelle und den IVFFlat-Index an —
**kein automatischer Initial-Build** (kostet 30 min beim Start). Der Build
ist eine explizite Admin-Aktion ueber das CLI-Skript oder den
`POST /api/embeddings/rebuild`-Endpoint.

## Wann was nutzen?

| Szenario                                | Tool                              |
| --------------------------------------- | --------------------------------- |
| Exakter Identifier (LEI, HRB)           | Phase 6d Entity-Resolution        |
| Namensvariante (Whitespace, e.V.)        | rapidfuzz Fuzzy-Match             |
| Thematische Suche („Klimaschutz Bayern") | Layer A Embedding-Index           |
| Konzernverbund-Recherche                 | GLEIF/Wikidata + Phase 6d Linker  |

Embedding-Layer ersetzt KEINEN dieser Mechanismen — er ergaenzt sie. Im
Audit-Report werden klassische Cross-Refs (Name/Identifier/Address) weiterhin
SEPARAT von den semantischen Nachbarn ausgewiesen, damit der Pruefer den
Unterschied zwischen identischen Quellen und thematisch aehnlichen Vorgaengen
direkt sieht.
