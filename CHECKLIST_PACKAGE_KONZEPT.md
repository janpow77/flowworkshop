# Konzept: Vollständiges Checklisten-Paket (Export/Import) für Auditworkshop

**Stand:** 2026-06-22 · **Repo:** `Projekte/Workshop/auditworkshop` · Status: **Konzept zur Abnahme** (noch kein Code)

Ziel: dieselbe „Checkliste als Paket exportieren/importieren"-Funktion wie im
`audit_designer` (dort fertig & verifiziert), angepasst an das **relationale**
Checklisten-Modell des Workshops. Eine Checkliste wird als **eine portable
Datei** (`.checklist.json`) exportiert und auf einer anderen Instanz
**vollständig** wieder eingelesen — mit Validierung und „existiert schon?"-Prüfung.

**Paketumfang (bestätigt):** Kernstruktur (Template + Knoten + Antwortsets/
Optionen + Kategorien) **immer**, zusätzlich wählbar **Diskussionen**
(Knoten-Kommentare), **Knoten-Historie** und **Versions-Snapshots**.
**Ohne** Referenzdokumente, Members/Einladungen/Locks (instanzspezifisch).

---

## 1. Ausgangslage (Workshop hat das relational)

Modell in `backend/models/checklist_template.py` (UUID-String-PKs):

- `ChecklistTemplate` (die Checkliste) → `nodes`, `answer_sets`, `categories`, `versions`, `members`, `invites`
- `ChecklistTemplateNode` — Knoten als **Zeilen** mit FKs: `parent_id`, `decision_parent_id`, `answer_set_id`, `category_id`
- `ChecklistAnswerSet` + `ChecklistAnswerOption` — Antwortsets (`template_id NULL` = globale Bibliothek)
- `ChecklistQuestionCategory` — Kategorien
- `ChecklistNodeComment` — **Diskussionen** (threaded, `parent_comment_id`)
- `ChecklistNodeHistory` — **Historie** (`node_snapshot`, `changed_fields`)
- `ChecklistTemplateVersion` — **Voll-Baum-Snapshots** (`tree_snapshot` JSONB)
- `ChecklistNodeReferenceDoc` — Belege (NICHT im Paket)

Vorhandener Export: nur **DOCX/XLSX/PDF** (`routers/checklist_export.py`,
`services/checklist_export_service.py`) — **kein JSON-Paket, kein Import**.

**Kernunterschied zu audit_designer:** dort liegt der Baum als ein JSONB-Blob
(`project_versions.tree_data`), Import = Blob schreiben, IDs bleiben.
Hier sind Knoten/Antwortsets **Zeilen mit FKs** → Import braucht **konsistentes
UUID-Remapping** über mehrere Tabellen. Das ist der eigentliche Mehraufwand.

**Keine Alembic-Migration nötig** — es werden nur vorhandene Tabellen genutzt.

---

## 2. Paketformat (`workshop-checklist-package`, format_version 1)

```jsonc
{
  "format": "workshop-checklist-package",
  "format_version": 1,
  "exported_at": "…",
  "source": { "app": "auditworkshop", "template_id": "<uuid>" },
  "checksum": "sha256:…",            // nur über Strukturkern (s.u.) — stabil ggü. Diskussionen/Zeitstempeln
  "options": { "discussions": true, "history": false, "versions": false },

  "template": {                       // ohne owner_id (instanzspezifisch)
    "title", "description", "source_language", "target_language",
    "properties_json", "status", "current_version"
  },
  "answer_sets": [{                   // template-scoped + referenzierte globale
    "old_id", "scope": "template|global", "name", "description", "sort_order",
    "options": [{ "old_id","name","sort_order","is_standard","is_entfaellt",
                  "value_number","threshold","bemerkung" }]
  }],
  "categories": [{ "old_id","name","sort_order" }],
  "nodes": [{
    "old_id","parent_old_id","node_type","status","branch","ja_label","nein_label",
    "decision_parent_old_id","sort_order","title","public_remark",
    "remark_snippets_json","eingabetyp","answer_type",
    "answer_set_old_id","category_old_id","legal_reference",
    "relevant_documents_json","is_header_field",
    "source_text_en","translated_text_de","review_text_de","translation_status"
  }],

  "discussions": [{ "node_old_id","author_name","message","parent_comment_old_id",
                    "created_at","edited_at" }],          // nur wenn options.discussions
  "history":     [{ "node_old_id","node_version","change_type","node_snapshot",
                    "changed_fields","changed_by_name","change_reason","created_at" }], // optional
  "versions":    [{ "version_number","is_frozen","status","tree_snapshot","notes",
                    "created_at" }]                       // optional (Voll-Baum-Snapshots)
}
```

**Checksum-Strukturkern** (für „identisch"-Erkennung): Template-Meta (title/
description/languages/properties) + Antwortsets+Optionen + Kategorien + Knoten
(ohne `id`/Zeitstempel/Übersetzungs-Volatiles, mit `old_id`-relativen Referenzen).
Diskussionen/Historie/Versionen fließen **nicht** in die Checksum ein — so ist
„identisch" unabhängig davon, welche Extras mitexportiert wurden (gleiche
Designentscheidung wie in audit_designer).

---

## 3. UUID-FK-Remapping (Kern des Imports)

Reihenfolge beim Import in **ein neues Template**:

1. `ChecklistTemplate` neu anlegen (owner = aktuelle Session), neue `id`.
2. **Antwortsets**:
   - `scope=global` → find-or-create globale `ChecklistAnswerSet` **per Name**
     (`template_id NULL`); vorhandene wiederverwenden.
   - `scope=template` → immer neu unter dem neuen Template.
   - Optionen je Set neu anlegen. Map `answer_set_old_id → new_id`.
3. **Kategorien** neu anlegen. Map `category_old_id → new_id`.
4. **Knoten** in **zwei Pässen** (robust gegen Reihenfolge/Zyklen):
   - Pass A: alle Knoten mit neuer `id`, `parent_id=NULL`, FKs `answer_set_id`/
     `category_id` über Maps gesetzt. Map `node_old_id → new_id`.
   - Pass B: `parent_id`, `decision_parent_id` über Node-Map nachziehen.
5. **Diskussionen** (optional): je Kommentar `node_id` über Node-Map,
   `parent_comment_id` über Comment-Map (2-Pass wie Knoten), `author_id` per
   `author_name` → `workshop_registrations` (sonst NULL, Name in Klartext im
   Text-Prefix erhalten).
6. **Historie** (optional): `node_id` über Map, `changed_by_id` per Name → sonst
   NULL; `node_snapshot`/`changed_fields` 1:1; ursprünglicher Autor in
   `change_reason` als „(urspr.: …)" — wie audit_designer.
7. **Versions-Snapshots** (optional): `ChecklistTemplateVersion` 1:1 anlegen;
   `tree_snapshot` enthält alte Knoten-IDs → entweder als-historisch
   unverändert übernehmen (Default, da eingefrorene Momentaufnahme) **oder**
   IDs im Snapshot mit der Node-Map umschreiben (sauberer, wenn der Snapshot
   später wieder geladen wird). Empfehlung: **umschreiben**, damit ein
   „Restore" der Version mit den neuen Knoten konsistent bleibt.

---

## 4. Backend (an Workshop-Konventionen)

Neuer Service `backend/services/checklist_package_service.py` (Stil wie
`checklist_export_service.py`). Neue Endpunkte als eigener Router
`backend/routers/checklist_package.py`, registriert in `main.py` neben den
anderen `checklist_*`-Routern, Prefix `/api/checklist-templates`,
`dependencies=[Depends(require_session)]` (wie `checklist_templates.py`):

| Methode | Pfad | Zweck |
|---|---|---|
| `GET` | `/{template_id}/package?discussions=&history=&versions=` | Paket bauen → JSON |
| `POST` | `/package/validate` (multipart `file`) | Struktur + „existiert schon?" (Vorschau, kein Schreibzugriff) |
| `POST` | `/package` (multipart `file`, `title?`, `target_template_id?`) | Import: neues Template **oder** als neue Version |

Rechte: `_require_member`/`require_session` wie im bestehenden
`checklist_export.py`. Validierung: Baum-Integrität (root/parent/branch),
Antwortset-/Kategorie-Vollständigkeit, `format_version`-Schranke; Existenz-
Prüfung per `title` (+ Checksum-Vergleich gegen gleichnamige Templates → `identical`).

**Import-Ziele:**
- **Neues Template** (Default) — entspricht „Checkliste importieren" im Dashboard.
- **In bestehendes Template** (optional) — als **`ChecklistTemplateVersion`-Snapshot**
  (sicher, da eingefroren; kein riskanter Live-Node-Replace). Spiegelt das „auch
  in bestehendes Projekt" aus audit_designer.

---

## 5. React-Frontend (TypeScript + Tailwind 4)

- `components/checklist/ExportMenu.tsx` erweitern: Eintrag **„Als Paket
  exportieren…"** → öffnet ein **Auswahlmenü-Modal**: Checkboxen
  **Diskussionen / Historie / Versions-Snapshots** (Antwortsets+Kategorien als
  „immer enthalten" angezeigt). Export = `GET …/package` → Blob-Download
  `<title>.checklist.json`.
- **Import-Einstieg** auf der Checklisten-Übersicht (analog Landing/Tool-Tiles):
  „Checkliste importieren (Paket)" → Datei wählen → `POST …/package/validate` →
  **Vorschau-Modal** (Existenz-Warnung, Kennzahlen Knoten/Fragen/Antwortsets/
  Diskussionen/Historie/Versionen, Antwortsets „neu/wiederverwendet", Fehler/
  Warnungen, Namensfeld) → `POST …/package` → Navigation zum neuen Template.
- `lib/api.ts` (fetch-basiert, `request`/`requestForm`, `getWorkshopAuthHeaders`)
  um `exportChecklistPackage(id, opts)`, `validateChecklistPackage(file)`,
  `importChecklistPackage(file, opts)` ergänzen. Upload via `FormData` (wie
  `requestForm`).

---

## 6. Tests & Verifikation (Workshop-Konventionen)

- **pytest** (`backend/`, `conftest.py`): Round-Trip (Export→Import = identisch),
  UUID-FK-Remapping (parent/decision/answer_set/category konsistent), globale
  Antwortset-Wiederverwendung per Name, Diskussionen/Historie/Versionen-Round-
  Trip, Validierung (Strukturfehler, Existenz/Identität), Import-in-bestehendes
  (Version-Snapshot).
- **`scripts/workshop_smoke.sh`** um die drei neuen Endpoints (401 ohne Auth)
  ergänzen.
- **Frontend-e2e** (`frontend/e2e/d-checklist.spec.ts` erweitern): Export-Datei
  erzeugen, re-importieren, Vorschau prüfen.

---

## 7. Risiken / offene Punkte

1. **Globale vs. template-scoped Antwortsets**: globale per Name dedupen, sonst
   wuchert die Bibliothek. Konflikt „gleicher Name, andere Optionen" → Default:
   vorhandenes globales Set wiederverwenden (nicht überschreiben); als Warnung
   melden.
2. **`tree_snapshot` der Versionen** enthält alte IDs → Remap empfohlen (s. 3.7).
3. **Autoren/Änderer** (Diskussionen/Historie) referenzieren
   `workshop_registrations` → per Name auflösen, sonst NULL + Name im Klartext.
4. **`properties_json`/`statistics_json`** 1:1 übernehmen (reine Daten).
5. **Sprachfelder** (`source_language`/`target_language`, Übersetzungsfelder der
   Knoten) gehören zur Struktur → mitexportieren.

---

## 8. Aufwand & Dateien (Schätzung)

| Bereich | Dateien | LOC (ca.) |
|---|---|---|
| Backend Service | `services/checklist_package_service.py` (neu) | ~450 |
| Backend Router | `routers/checklist_package.py` (neu) + `main.py` (1 Zeile) | ~130 |
| Schemas | `schemas/checklist_package.py` (neu, Pydantic Out) | ~60 |
| Frontend | `ExportMenu.tsx` (+), neuer Import-Dialog, `lib/api.ts` (+) | ~400 |
| Tests | `backend/tests/test_checklist_package.py`, e2e (+), smoke (+) | ~350 |

**Gesamt:** ~1–1,5 Tage. Keine DB-Migration.

---

## 9. Nicht enthalten (bewusst)

Referenzdokumente (`ChecklistNodeReferenceDoc`), Members/Einladungen/Locks,
Lese-/Unread-Status. Diese sind instanz-/personenspezifisch und gehören nicht in
ein portables Struktur-Paket.

---

## 10. Interop-Prüfung audit_designer ↔ Workshop (2026-06-22, verifiziert)

**Ergebnis: bidirektional machbar, verlustarm — mit Adapter.** Konkret getestet
(throwaway-Prototypen gegen echte Systeme):

- **Designer → Workshop**: echtes audit_designer-Paket (Projekt „Vorhabenprüfung
  CL 2021-2027", **443 Knoten**) in das **echte Workshop-ORM** (SQLite) geladen →
  1 Wurzel, vollständiger Eltern-Baum, 245 Branches + Decision-Parents, 254
  Textbausteine, 69 Ja/Nein-Labels — alles erhalten.
- **Workshop → Designer**: repräsentative relationale Checkliste (Antwortset
  „Bewertung"/4 Optionen, Decision mit Ja/Nein-Labels, JA/NEIN-Branches,
  CUSTOM_ENUM, Textbaustein, Diskussion) → in den **laufenden** audit_designer
  importiert → Antwortset wurde Kategorie (4 Items), Branches/Labels/Textbaustein/
  Diskussion überstanden. Cleanup ok.

### Pflicht-Erkenntnisse für den Adapter

1. **Hierarchie-Quelle**: audit_designer speichert den Baum in `children`-Arrays;
   `parent_id` ist dort **immer NULL**. Der Workshop-Import MUSS `children`
   top-down laufen (nicht `parent_id`), und der Workshop→Designer-Export MUSS
   `children` füllen + `parent_id` null lassen. `decision_parent_id` = nächster
   DECISION-Vorfahre.
2. **Antwortset ↔ Kategorie**: Workshop `ChecklistAnswerSet`(+Optionen) ⇆
   audit_designer `categories`(+items)/`CUSTOM_ENUM` — sauber per Name abbildbar.
   (Workshops `ChecklistQuestionCategory` ist nur Gruppierung und hat KEIN
   Pendant in audit_designer.)
3. **⚠ Lossy-Punkt**: audit_designer-Knoten mit `answer_type=CUSTOM_ENUM`, die
   per `qchess_antwortset_id` an die QChess-Bibliothek gebunden sind, führen die
   Options-Labels **NICHT** im Paket (weder `answer_options` noch `category_id`).
   → Für echten Cross-Repo/-Instance-Transport sollte der **audit_designer-Export
   erweitert** werden: `qchess_antwortset_id` beim Export auflösen und die
   Optionen als gebündelte Kategorie/`answer_options` mitgeben. (Betrifft auch
   audit_designer↔audit_designer über Instanzgrenzen.)
4. **Feld-Korrespondenz**: `qchess_ja_label`/`qchess_nein_label` ⇆ `ja_label`/
   `nein_label`; `qchess_eingabetyp` ⇆ `eingabetyp`; `internal.team_notes` ⇆
   `ChecklistNodeComment`; Historie ⇆ `ChecklistNodeHistory`; Zusatzversionen ⇆
   `ChecklistTemplateVersion.tree_snapshot`.

### Empfohlenes Design

Statt eines dritten „Austauschformats": **jede Importseite akzeptiert auch das
Paket der Gegenseite** über ihren `normalize_payload`/Adapter — d.h. der
Workshop-Import erkennt `format == "audit-designer-checklist-package"` und
konvertiert (children-walk, Antwortset↔Kategorie), und umgekehrt erkennt
audit_designer `format == "workshop-checklist-package"`. Beide Konvertierungen
sind oben verifiziert.
