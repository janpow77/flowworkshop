# Plan: EU-Beihilfe-Transparenzregister

Stand: 2026-05-08

Ziel dieses Dokuments ist ein umsetzungsnaher Plan fuer ein drittes oeffentliches Register in der Workshop-Plattform. Das Register soll State-Aid-/TAM-Daten lokal harvesten, normalisieren, durchsuchen, kartieren und mit Beguenstigtenverzeichnis sowie Sanktionslisten kombinierbar machen.

## 1. Zielbild

Das neue Modul soll neben den bestehenden Kernmodulen stehen:

1. Beguenstigtenverzeichnis
2. Sanktionslisten
3. EU-Beihilfe-Transparenzregister

Fachlicher Nutzen:

- Pruefer koennen zu einem Unternehmen lokal nach oeffentlichen Beihilfeinformationen suchen.
- Beihilfedaten werden mit Betrag, Region, Beihilfeinstrument, Ziel, Behoerde und Fallreferenz angezeigt.
- Wenn vorhanden, wird die KOM-/SA-Fallreferenz sichtbar und auf die Commission Competition Cases Search verlinkt.
- Eine Karte zeigt regionale Konzentrationen, ohne Scheingenauigkeit zu erzeugen.
- Alle Such- und Analysefunktionen laufen nach dem Harvest lokal.

Wichtige Abgrenzung:

- TAM ist nicht zwingend vollstaendig fuer alle Mitgliedstaaten. Die EU-Kommission nennt TAM als einen Veroeffentlichungsweg, alternativ nationale oder regionale State-Aid-Websites.
- Das Register soll deshalb nicht "amtlicher Vollstaendigkeitsnachweis" sein.
- UI und Exporte muessen immer Quelle, Datenstand und Abdeckungshinweis anzeigen.

Quellenbasis:

- EU-Kommission Aid Beneficiaries: https://competition-policy.ec.europa.eu/state-aid/aid-beneficiaries_en
- TAM Public Search: https://webgate.ec.europa.eu/competition/transparency/public?lang=en
- Competition Cases Search: https://competition-cases.ec.europa.eu/search

## 2. Produktname Und Navigation

Empfohlener Modulname:

`EU-Beihilfe-Transparenzregister`

Alternative Kurzbezeichnung:

`Beihilfe-Register`

Nicht empfohlen:

- Nur `TAM`, weil TAM nicht alle Veroeffentlichungswege abdeckt.
- `vollstaendige EU-Beihilfedatenbank`, weil Vollstaendigkeit fachlich nicht garantiert werden kann.

Navigation:

- Oeffentliche Route: `/beihilfen`
- Interne Route optional identisch, aber mit Zusatzfunktionen fuer Admin/Moderator.
- Sidebar-Eintrag: `Beihilfe-Register`
- In Unternehmenssuche/CompanySearchPage als weiterer Datenraum prominent anzeigen.

## 3. Bestehende Codebasis Nutzen

Vorhandene Anknuepfungspunkte:

- `auditworkshop/backend/routers/reference_data.py`
  - erlaubt bereits `registry_type = tam | state_aid | cohesio | sanctions | other`
  - kann fuer manuelle Importe und Suche weiterverwendet oder erweitert werden.
- `auditworkshop/backend/services/dataframe_service.py`
  - enthaelt bereits Reference-Registry-Profile fuer `tam`.
  - enthaelt `search_reference_registry_records(...)`.
- `auditworkshop/frontend/src/pages/CompanySearchPage.tsx`
  - kennt bereits den Registertyp `tam`.
  - kann als Basis fuer Fuzzy-Unternehmenssuche und Trefferkarten dienen.
- `auditworkshop/frontend/src/lib/api.ts`
  - kennt `ReferenceRegistryType`.
- Bestehende Muster:
  - Sanktionslisten: lokale Suche, Trefferqualitaet, Export.
  - Beguenstigtenverzeichnis: Karte, Quellenstand, Worker-Update, Datenqualitaet.

Ziel fuer Claude Code:

- Keine parallele Inselloesung bauen.
- Bestehende Reference-Registry-Struktur erweitern.
- Fuer State-Aid/TAM ein eigenes fachliches Frontend bauen, aber Suchlogik und Tabellen-Metadaten nach Moeglichkeit wiederverwenden.

## 4. Datenquellen

### 4.1 Primaere Quelle: TAM Public Search

TAM bietet oeffentliche Beihilfe-Award-Daten. Die oeffentliche Seite arbeitet mit Formularen und serverseitiger Suche. Vor Umsetzung ist technisch zu klaeren:

- Gibt es einen stabilen Export-Endpunkt?
- Gibt es pagination oder serverseitige Limits?
- Welche Felder werden in der Ergebnisansicht geliefert?
- Sind Detailseiten pro Award vorhanden?
- Welche Session-/CSRF-Mechanik wird verwendet?
- Gibt es CSV/Excel/PDF-Export aus der Suche?

Umsetzungsregel:

- Keine fragile Browser-Automation als Dauerloesung, solange ein stabiler HTTP-Flow moeglich ist.
- Falls nur HTML-Formular moeglich ist: robustes Harvesting mit `requests`, Session, CSRF-Token, Pagination und HTML-Parser.
- Falls ein nicht dokumentierter JSON/API-Endpunkt existiert: nur nutzen, wenn stabil, nachvollziehbar und nicht durch Nutzungsbedingungen ausgeschlossen.

### 4.2 Ergaenzende Quellen

TAM selbst verweist auf externe Register fuer einzelne Staaten. Mindestens als Quellen-Metadaten vorsehen:

- Polen: `https://sudop.uokik.gov.pl/home`
- Polen Landwirtschaft: `https://srpp.minrol.gov.pl`
- Rumaenien: `https://regas.consiliulconcurentei.ro/transparenta/index.html`
- Spanien: `http://www.infosubvenciones.es/bdnstrans/GE/es/index`
- Slowenien: `https://www.gov.si/teme/objava-vecjih-prejemnikov-pomoci/`

Phase 1 soll TAM priorisieren. Externe Register werden als spaetere Connectoren vorbereitet.

### 4.3 Competition Cases Search

Ziel:

- Aus State-Aid-Referenzen wie `SA.12345` Links zur KOM-Fallakte erzeugen.
- Wenn konkrete Decision-Dokumente automatisiert auffindbar sind, diese als Links anzeigen.
- Wenn nicht: generischen Suchlink mit SA-Nummer anzeigen.

Wichtig:

- Nicht jeder Award muss eine direkt maschinenlesbare PDF-Entscheidung enthalten.
- Die UI muss unterscheiden:
  - `KOM-Fallreferenz vorhanden`
  - `Fallakte verlinkt`
  - `Entscheidungsdokument direkt verlinkt`
  - `kein direkter Dokumentlink gefunden`

## 5. Lokale Speicherung

Alle geharvesteten Daten werden lokal gespeichert. Externe Verbindungen sind nur fuer Aktualisierung/Harvest notwendig.

Vorgeschlagene Verzeichnisse:

- `auditworkshop/backend/data/state_aid/raw/`
- `auditworkshop/backend/data/state_aid/normalized/`
- `auditworkshop/backend/data/state_aid/reports/`

Vorgeschlagene Tabellen:

### 5.1 Raw Harvest Runs

`workshop_state_aid_harvest_runs`

Felder:

- `id`
- `source_key`
- `source_url`
- `started_at`
- `finished_at`
- `status`
- `records_seen`
- `records_inserted`
- `records_updated`
- `records_failed`
- `error_message`
- `triggered_by`
- `source_version`
- `source_last_modified`

### 5.2 Normalisierte Awards

`workshop_state_aid_awards`

Pflichtfelder:

- `id`
- `source_key`
- `source_record_id`
- `source_url`
- `beneficiary_name`
- `beneficiary_name_normalized`
- `beneficiary_identifier`
- `beneficiary_type`
- `country_code`
- `country_name`
- `nuts_code`
- `nuts_label`
- `nuts_level`
- `nace_code`
- `nace_label`
- `aid_amount`
- `aid_currency`
- `aid_amount_eur`
- `aid_instrument`
- `aid_objective`
- `granting_authority`
- `entrusted_entity`
- `granting_date`
- `publication_date`
- `measure_reference`
- `sa_reference`
- `case_url`
- `decision_url`
- `raw_payload_json`
- `created_at`
- `updated_at`
- `harvest_run_id`

Indizes:

- `beneficiary_name_normalized`
- `country_code`
- `nuts_code`
- `granting_date`
- `aid_amount_eur`
- `sa_reference`
- `measure_reference`
- Fulltext/Fuzzy Index auf `beneficiary_name`, `aid_objective`, `granting_authority`.

### 5.3 Quellenstatus

`workshop_state_aid_sources`

Felder:

- `source_key`
- `display_name`
- `source_type`: `tam | national | cases | manual`
- `country_code`
- `base_url`
- `last_successful_harvest_at`
- `last_record_date`
- `record_count`
- `coverage_note`
- `enabled`

## 6. Normalisierung

### 6.1 Unternehmensname

Normalisierung fuer Fuzzy-Suche:

- lowercase
- Umlaute transliterieren
- Rechtsform-Zusatz reduzieren:
  - GmbH
  - AG
  - KG
  - GmbH & Co. KG
  - UG
  - e.V.
  - gGmbH
  - Ltd
  - SA
  - SAS
  - BV
  - Sp. z o.o.
- Satzzeichen entfernen
- Whitespace normalisieren
- haeufige Fuellwoerter optional reduzieren:
  - holding
  - group
  - deutschland
  - germany

Kein aggressives Mergen ohne Anzeige der Originalnamen.

### 6.2 Betrag

- Betrag als Originalbetrag speichern.
- Waehrung speichern.
- Wenn EUR: `aid_amount_eur = aid_amount`.
- Falls andere Waehrung vorkommt: keine automatische Umrechnung ohne belastbare Quelle. Feld leer lassen oder Umrechnung nur mit dokumentierter EZB-Rate.

### 6.3 Region

- NUTS-Code speichern.
- NUTS-Level bestimmen.
- Karte darf nur auf der tatsaechlich vorhandenen Genauigkeit aggregieren.
- Keine Stadtpunkte erzeugen, wenn nur NUTS II vorhanden ist.

#### 6.3.1 Aufloesungs-Stufen

`derive_nuts_code(region_label, country_iso2)` versucht in mehreren Stufen
aus der von TAM gelieferten `region`-Bezeichnung einen NUTS-Code abzuleiten.
Sobald eine Stufe trifft, wird der Code mit dem entsprechenden `nuts_level`
gespeichert. Wenn keine Stufe greift, wird der Land-Code als Fallback
verwendet (Level 0).

**DE — 4 Stufen**

1. Direkter Bundesland-Match (`Hessen`, `Bayern`, `NRW`, …) → NUTS-1 (Level 1).
2. NUTS-2 Regierungsbezirk / Statistische Region (`Köln`, `Düsseldorf`,
   `Oberbayern`, `Schwaben`, `Darmstadt`, …) → NUTS-1 (Level 1).
3. NUTS-3 Kreis / kreisfreie Stadt (`München` → DE212, `Bonn` → DEA22,
   `Hamburg` → DE600, …) → NUTS-3 (Level 3). Quelle:
   `backend/data/nuts_de.json` mit 401 Eintraegen.
4. Fallback Land-Code (Level 0).

**AT — 3 Stufen**

1. Bundesland-NUTS-2 (`Wien`, `Tirol`, `Steiermark`, …) → NUTS-2 (Level 2);
   Stufen 1-/2-Codes aus `AT_REGION_TO_NUTS2`. Bei einem Bundesland-Treffer
   wird zusaetzlich gegen NUTS-3 geprueft, falls TAM einen praeziseren
   Bezirksnamen (z.B. `Salzburg und Umgebung` → AT323) liefert.
2. NUTS-3 politischer Bezirk (`Linz-Wels` → AT312, `Oststeiermark` → AT224,
   `Waldviertel` → AT124, `Wiener Umland/Nordteil` → AT126, …) → NUTS-3
   (Level 3). Quelle: `backend/data/nuts_at.json` mit allen 35
   Eurostat-NUTS-3-Codes.
3. Fallback Land-Code (Level 0).

**Speicher- und Such-Vertrag**

- Im Award wird der ECHTE 5-stellige NUTS-3-Code gespeichert (z.B. DE212),
  nicht eine kuenstliche Aggregation auf Bundesland.
- Die Suche `nuts_code` filtert per **Prefix-Match** (`nuts_code LIKE 'DE2%'`).
  Eine Suche nach `DE2` matcht damit Bayern-NUTS-1, Oberbayern-NUTS-2 (DE21)
  und Muenchen-NUTS-3 (DE212) gleichermassen. Damit dieser Match auch bei
  170k+ Records performant bleibt, existieren die Postgres-Indizes
  `ix_state_aid_nuts_prefix(nuts_code)` und
  `ix_state_aid_country_nuts(country_code, nuts_code)`.
- `aggregate_for_map(level=N)` rollt NUTS-3 per `substr(nuts_code, 1, 2+N)`
  zurueck — Default Level 1 fuer 16 Bundeslaender / 9 AT-Bundeslaender.

### 6.4 SA-/KOM-Referenz

Erkennung:

- Regex: `SA\\.?\\s*\\d{4,6}`
- Normalisieren auf `SA.xxxxx`.
- Suchlink zur Competition Cases Search erzeugen.
- Direkter Decision-Link nur setzen, wenn eindeutig gefunden.

## 7. Fuzzy-Unternehmenssuche

### 7.1 Ziel

Ein Pruefer gibt einen Unternehmensnamen ein. Das System findet Treffer trotz:

- Rechtsformvarianten
- Umlaute
- Tippfehler
- Gross-/Kleinschreibung
- abweichende Leerzeichen/Bindestriche
- Konzern-/Holding-Zusaetze

### 7.2 Trefferbewertung

Score aus mehreren Komponenten:

- exakter normalisierter Match: sehr hoch
- Token-Overlap: hoch
- trigram/similarity: mittel
- Levenshtein/rapidfuzz ratio: mittel
- Alias-/Identifier-Match: sehr hoch, falls vorhanden
- Land/Region optional als Boost, wenn Filter gesetzt

Anzeige:

- Match Score
- Originalname
- normalisierter Name
- Grund des Matches, z. B. `Name`, `Identifier`, `SA-Referenz`, `Behoerde`

### 7.3 Gemeinsame Unternehmenspruefung

Langfristiges Ziel:

Eine Suche fragt parallel:

- Beguenstigtenverzeichnis
- EU-Beihilfe-Transparenzregister
- Sanktionslisten

Ergebnis als Unternehmensdossier:

- Foerdervorhaben
- Beihilfe-Awards
- Sanktionslistenhinweise
- Gesamtbetrag je Register
- auffaellige Mehrfachnennungen
- Quellenstand
- Export

### 7.4 Such-Performance: pg_trgm-Index

Bei 170k+ Records wird `ILIKE '%token%'` ohne Index zum Seq Scan
(in der Workshop-DB ~120 ms pro Query). Mit dem im Lifespan idempotent
angelegten GIN-Index `ix_state_aid_name_trgm` (PostgreSQL-Extension
`pg_trgm`) wird daraus ein Bitmap Index Scan — gemessen ~0.3 ms,
Faktor ~350x.

Migration in `main.py` Lifespan:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IF NOT EXISTS ix_state_aid_name_trgm
  ON workshop_state_aid_awards
  USING GIN (beneficiary_name_normalized gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_state_aid_authority_trgm
  ON workshop_state_aid_awards
  USING GIN (granting_authority gin_trgm_ops)
  WHERE granting_authority IS NOT NULL;
```

Verifikation:

```sql
EXPLAIN ANALYZE SELECT * FROM workshop_state_aid_awards
  WHERE beneficiary_name_normalized ILIKE '%fraunhofer%';
-- Bitmap Index Scan on ix_state_aid_name_trgm
```

Zusaetzlich: Tokens, die in den ILIKE-Vorfilter gehen, werden mit
`_escape_like()` aus `services/state_aid_service.py` SQL-wildcard-sicher
gemacht (`%` und `_` werden escapt). Damit wird eine User-Eingabe wie
`50%` oder `a_b` nicht versehentlich als Wildcard interpretiert.

### 7.5 Adaptiver Schwellwert (`min_score`)

Im `/api/state-aid/search`-Endpoint ist `min_score` jetzt optional. Wenn
nicht gesetzt, wird er aus der Token-Anzahl der Query bestimmt:

| Tokens | min_score | Begruendung |
| --- | --- | --- |
| 1 | 80.0 | Einzelner Token braucht strengen Match — sonst zu viele False Positives |
| 2 | 70.0 | Mittlere Toleranz |
| >=3 | 60.0 | Langer Query darf toleranter matchen |

Beispiele:
- `BMW` -> 80.0
- `Deutsche Bahn` -> 70.0
- `Fraunhofer Gesellschaft Forschung` -> 60.0

Frontend-Slider (40-100) ueberschreibt die Heuristik; `meta.auto_min_score=true`
im Response signalisiert, dass die Heuristik aktiv war.

### 7.6 Aliases-Mapping (Akronyme)

Datei: `auditworkshop/backend/data/state_aid_aliases.json`. Mapping
Akronym (lowercase) -> ausgeschriebene Form. Wird vor der Fuzzy-Suche
durch `expand_alias()` aufgeloest.

Beispiele:

| Eingabe | Effektive Query | meta.alias_used |
| --- | --- | --- |
| `KfW` | `Kreditanstalt für Wiederaufbau KfW` | `Kreditanstalt für Wiederaufbau` |
| `BMW` | `Bayerische Motoren Werke BMW` | `Bayerische Motoren Werke` |
| `BMWK Förderung` | `Bundesministerium für Wirtschaft und Klimaschutz BMWK Förderung` | `Bundesministerium für Wirtschaft und Klimaschutz` |
| `Random` | `Random` | (kein Eintrag) |

Das Original wird an die expandierte Form angehaengt — so kann der
Identifier-Match weiter ueber das Akronym laufen, der Name-Match aber
ueber die Vollform.

### 7.7 Empty-Result-Fallback

Wenn die Suche `total_hits=0` liefert, wird automatisch in zwei Stufen
gelockert (jeweils einmalig pro Request):

1. `min_score -= 15` (begrenzt auf >= 50.0)
2. `country_code` wird entfernt

Die Lockerungen werden im Response unter `meta.relaxed` aufgelistet:

```json
{
  "total_hits": 7,
  "threshold": 50.0,
  "meta": {
    "auto_min_score": true,
    "relaxed": ["min_score:80->65", "country_code:DE->none"]
  }
}
```

So bekommt der Pruefer immer ein Ergebnis, sieht aber transparent, dass
die ursprungliche Filter-Strenge verfehlt wurde.

## 8. Kartenansicht

### 8.1 Grundprinzip

Die Karte soll State-Aid-Daten regional darstellen, aber keine falsche Praezision erzeugen.

Wenn nur NUTS II vorhanden ist:

- Aggregation auf NUTS II.
- Kein Punkt auf Stadt- oder Adressniveau.

Wenn NUTS III vorhanden ist:

- Aggregation auf NUTS III.

Wenn nur Land vorhanden ist:

- Anzeige in Tabelle/Statistik, aber nicht als genauer Kartenpunkt.

### 8.2 Datenbasis Fuer Karte

Erforderlich:

- EU-weite NUTS-Centroids oder NUTS-GeoJSON lokal speichern.
- Quelle bevorzugt Eurostat/GISCO.
- Version dokumentieren, z. B. `NUTS 2024`.

Vorgeschlagene Dateien:

- `auditworkshop/backend/data/nuts/eu_nuts_2024_centroids.json`
- `auditworkshop/backend/data/nuts/eu_nuts_2024_regions.geojson` optional fuer Choropleth.

### 8.3 Kartenmodi

Modus 1: Cluster/Kreise

- Kreisgroesse: Anzahl Awards oder Gesamtbetrag.
- Farbe: Land oder Beihilfeziel.
- Tooltip: Region, Anzahl, Betrag.

Modus 2: Choropleth

- Flaechenfarbe nach Gesamtbetrag pro Region.
- Optional spaeter, wenn GeoJSON performant genug ist.

Modus 3: Tabellenverbund

- Klick auf Region filtert Trefferliste.
- Regionendetail zeigt:
  - Gesamtbetrag
  - Anzahl Awards
  - Top-Beguenstigte
  - Top-Behoerden
  - Top-Beihilfeziele
  - SA-Referenzen

### 8.4 Kartenqualitaet Anzeigen

Immer sichtbar:

- `Kartierbare Datensaetze: x von y`
- `Genauigkeit: NUTS II / NUTS III / Land / unbekannt`
- `Datenstand: letzter Harvest`
- `Nicht kartierbare Datensaetze: n`

## 9. Frontend

Neue Seite:

- `auditworkshop/frontend/src/pages/StateAidRegisterPage.tsx`

Route:

- `/beihilfen`

Komponenten:

- `StateAidSearchPanel`
- `StateAidResultsTable`
- `StateAidMap`
- `StateAidAwardDetail`
- `StateAidSourceStatus`
- `StateAidExportActions`

### 9.1 Layout

Erster Screen:

- Suchfeld fuer Unternehmen
- Filterleiste
- Datenstand/Quellenstatus
- Ergebniszahlen
- Tabs:
  - Treffer
  - Karte
  - Auswertung
  - Quellen

Keine Marketingseite. Direkt nutzbares Fachtool.

### 9.2 Filter

- Unternehmen
- Land
- NUTS-Region
- Jahr / Zeitraum
- Mindestbetrag / Hoechstbetrag
- Beihilfeinstrument
- Beihilfeziel
- Behoerde
- SA-Referenz
- NACE
- Quelle

### 9.3 Detailansicht

Je Award:

- Beguenstigter
- Betrag
- Datum
- Beihilfeinstrument
- Ziel
- Behoerde
- Region/NUTS
- NACE
- Massnahmenreferenz
- SA-Referenz
- Link Competition Cases Search
- Direkter KOM-Entscheidungslink, falls vorhanden
- Quelle und Harvest-Datum

### 9.4 Export

Mindestens:

- CSV fuer Excel
- PDF-Bericht

Optional:

- XLSX, wenn vorhandene Exportlogik dies sauber unterstuetzt.

Export muss enthalten:

- Suchparameter
- Datenstand
- Quellenhinweis
- Trefferliste
- Zusammenfassung
- Hinweis zur Vollstaendigkeit

## 10. Backend-API

Neue Router-Datei:

- `auditworkshop/backend/routers/state_aid.py`

Endpoints:

- `GET /api/state-aid/status`
- `GET /api/state-aid/sources`
- `POST /api/state-aid/harvest`
- `GET /api/state-aid/search`
- `GET /api/state-aid/award/{id}`
- `GET /api/state-aid/map`
- `GET /api/state-aid/stats`
- `GET /api/state-aid/company-dossier`

Zugriff:

- Suche/Karte oeffentlich lesbar.
- Harvest nur Admin/Worker.
- Quellenstatus oeffentlich lesbar, aber technische Fehlerdetails nur Admin.

## 11. Harvester

Neue Datei:

- `auditworkshop/backend/scripts/harvest_state_aid.py`

Funktionen:

- `--check`: Quellen pruefen, keine Daten schreiben.
- `--country DE`: einzelnes Land.
- `--source tam`: Quelle auswaehlen.
- `--since YYYY-MM-DD`: inkrementell, falls Quelle das erlaubt.
- `--limit N`: Testlauf.
- `--smart` (Default), `--full-refresh`, `--force`: Modus-Auswahl, mutually exclusive.

### 11.0 Drei Harvest-Modi

Der Harvester laeuft in einem von drei Modi. Default ist `smart` — alte
Datensaetze bleiben unveraendert, nur neue werden eingefuegt.

**`smart` (Default, idempotent):**

- Wenn `--since` nicht gesetzt und `last_successful_harvest_at` der Source
  vorhanden ist: Auto-Since = `last_successful_harvest_at - 14 Tage`.
  Geclampt auf `1990-01-01` als Untergrenze.
- 14 Tage Lookback, weil TAM Awards nachtraeglich publiziert (siehe Realitaet
  in `state-aid-source-analysis.md`).
- DB-Schreibstrategie: `ON CONFLICT (source_key, source_record_id) DO NOTHING`.
- Counter-Semantik: neue Inserts -> `records_inserted`, Konflikte ->
  `records_skipped`. Kein `failed`, weil das ein erwarteter Zustand ist.
- Mehrfaches Aufrufen ohne Side Effects.

**`full-refresh`:**

- `--since` / `--until` werden so durchgereicht, wie sie kommen.
- Kein Auto-Since.
- DB-Schreibstrategie: `ON CONFLICT DO UPDATE` — uebernimmt Korrekturen,
  die TAM nachtraeglich an Awards macht (z.B. korrigierter Betrag,
  geaenderte Bewilligungsstelle).
- Counter-Semantik: jeder Touch (Insert oder Update) -> `records_inserted`;
  ein separates `updated`-Feld bleibt 0 (saubere Trennung wuerde SELECT
  vorab erfordern, bewusst weggelassen).

**`force`:**

- Vor dem Lauf werden alle Awards der Quelle (`source_key`) geloescht.
- Anschliessend Insert ohne Conflict-Handling (Tabelle ist leer).
- Anzahl der vorab geloeschten Datensaetze wird im Run-Log unter
  `error_message` als Info-Text vermerkt (kein Fehler-Status).

Im `StateAidHarvestRun.parameters` (JSON) werden zusaetzlich gespeichert:
`mode`, `effective_since` (das tatsaechlich verwendete Datum), `auto_since_used`
(bool). Damit ist im Admin-UI nachvollziehbar, was passiert ist.

Worker-Integration:

- Scheduler um `run_state_aid_auto_harvest(...)` erweitern (siehe §16.5).
- `WORKER_API_TOKEN` wie beim Beguenstigtenverzeichnis nutzen.
- Harvest-Logs in Datenbank speichern.

### 11.0a Chunked Harvest (Jahres-Buckets)

Bei langen Zeitraeumen wird der Harvest in Jahres-Chunks zerlegt, damit
einzelne TAM-Suchen nicht in Server-Limits laufen und die Logs zwischen
Jahren auswertbar bleiben. Die CLI-Schalter:

- `--chunk-by year` zerlegt den Zeitraum [`--since`, `--until`] in
  Kalenderjahre und ruft pro Jahr ein eigenes `run_harvest` auf. Default
  ist `none` (ein Lauf).
- Pure Helper: `scripts/harvest_state_aid.build_year_chunks(since, until)`
  liefert die Liste `[(start, end), ...]`. Erste/letzte Grenze sind auf das
  Originalfenster geclippt, dazwischen volle Kalenderjahre. Tag-genau
  anschliessend, keine Luecke, keine Ueberlappung.
- Zwischen Chunks `time.sleep(2.0)` — TAM gegenueber freundlich, gleichzeitig
  sichtbares Logging fuer den Workshop-Admin.
- Idempotenz: Jeder Chunk laeuft im gleichen Modus weiter (per Default
  `smart`), sodass ein Re-Run desselben Zeitraums keine Duplikate einspielt.
- Fehlerverhalten: Faellt ein einzelnes Jahr aus, wird der Fehler geloggt
  und der naechste Chunk gestartet — der Aggregat-Status ist `partial`.
- Pro Chunk wird ein eigener `StateAidHarvestRun` geschrieben. Die CLI
  liefert ein aggregiertes JSON `{"chunks": [...], "totals": {...}}`.
- Logging-Format pro Chunk: `Chunk 2024 OK: seen=12345 inserted=12000
  skipped=345 failed=0`.

### 11.0b Full-History (`--full-history`)

Eintippen-Schalter fuer den kompletten TAM-Datenbestand eines Landes:

- Setzt implizit `--since 2014-07-01` (Pflicht zur Veroeffentlichung von
  Awards beginnt mit Art. 9 GBER, VO 651/2014).
- Setzt implizit `--until <heute>`.
- Setzt implizit `--chunk-by year`.
- Setzt implizit `--limit 100000` pro Chunk (sofern nicht anders gesetzt).
- Hilfetext warnt explizit vor langer Laufzeit. Faustformel: ~10 000 Awards
  pro Jahr in DE × ~12 Jahre = ~120 000 Datensaetze, bei TAM-Rate-Limit
  ~0.6 s/Request entsprechend ~30 min reine HTTP-Zeit.

### 11.1 TAM-Harvest Strategie

1. Public Search laden.
2. CSRF-Token extrahieren.
3. Suchformular fuer Land/Region absenden.
4. Ergebnis-Pagination erkennen.
5. Ergebniszeilen parsen.
6. Detailseiten abrufen, wenn notwendig.
7. Rohdaten speichern.
8. Normalisierte Awards upserten — Strategie modusabhaengig (siehe §11.0).

Respektvolle Limits:

- Rate Limit.
- Retry mit Backoff.
- User-Agent setzen.
- Kein aggressives Parallel-Scraping.

### 11.5 LLM-Frage-Endpoint (`POST /api/state-aid/ask`)

Klartext-Frage in eine Pruefer-taugliche Antwort uebersetzen — z.B. "Zeig mir
alle Beihilfen ueber 1 Mio EUR aus Bayern fuer Maschinenbau im Jahr 2022" oder
"Wer hat 2020 in NRW von der KfW Geld bekommen?".

Architektur — zwei LLM-Calls und ein SQL-Call dazwischen, damit die
Daten-Hoheit bei SQL bleibt:

```
LLM-Call 1: Frage         -> JSON-Filter (Function-Call-Style)
                v
SQL:        existing _apply_award_filters + fuzzy_match_company
                v
LLM-Call 2: Treffer + Stats -> Klartext-Zusammenfassung (Stream)
```

Implementierung in `services/state_aid_llm.py`:

- `parse_question(question, country_code)` — Filter-Uebersetzer mit
  Whitelist-Sanitizer (`_sanitize_filter_dict`) gegen LLM-Drift. Erlaubte
  Felder: `q`, `country_code`, `nuts_code`, `since`, `until`, `min_amount`,
  `max_amount`, `aid_instrument`, `objective`, `granting_authority`,
  `sa_reference`, `source_key`. Faellt das LLM aus, greift ein
  deterministischer Regex-Fallback (Jahr / Bundesland / "ueber X Mio").
- `compute_stats(hits)` — pure Python, berechnet Total, Top-3-Empfaenger,
  Top-3-Behoerden, Top-3-Regionen, Top-3-Ziele, Verteilung pro Jahr und
  Top-Empfaenger-Anteilsquote. Kein LLM beteiligt.
- `relax_filters(filter_dict)` — entfernt das spezifischste Feld zuerst
  (`min_amount` -> `max_amount` -> `objective` -> `aid_instrument` -> ...),
  damit "0 Treffer" automatisch in einen sinnvollen Treffer-Set umgesetzt
  werden kann. Maximal 3 Lockerungen, jeweils im Stream signalisiert.
- `stream_summary(question, hits, stats)` — streamt Klartext-Tokens. Bekommt
  vom Aufrufer NUR aggregierte Werte, keine Roh-Hits — das LLM kann also
  keinen einzelnen Award umdichten.

Endpoint-Spezifikation:

- Methode: `POST /api/state-aid/ask`
- Body:
  ```json
  {
    "question": "Zeig mir alle Beihilfen ueber 1 Mio EUR aus Bayern 2022",
    "country_code": "DE",
    "locale": "de",
    "limit": 50
  }
  ```
- Response: `text/event-stream` (SSE)
- Eventtypen (jeweils `event: <type>` + `data: {...}`):
  - `status` — Pipeline-Schritt (`{"step": "filter" | "search" | "summary"}`).
  - `filter` — Erkannter Filter + raw_llm-Output:
    `{"filter": {...}, "raw_llm": "...", "source": "llm"|"fallback"}`.
  - `relax` — Filter wurde gelockert: `{"removed_field": "min_amount", "new_filter": {...}}`.
  - `results` — SQL-Treffer + berechnete Stats:
    `{"total_hits": N, "hits": [{...}], "stats": {...}, "filter_used": {...}, "relaxations": [...]}`.
  - `summary_token` — einzelner LLM-Token: `{"text": "..."}`.
  - `done` — Abschluss: `{"elapsed_ms": N, "total_hits": N, "filter_used": {...}}`.
  - `error` — Fehler im Step: `{"step": "...", "message": "..."}`.

Garantien:

- **Keine LLM-Halluzination im Datenfeld.** Betraege, Namen und Behoerden
  werden ausschliesslich aus dem SQL-Ergebnis serialisiert. Das LLM darf in
  der Zusammenfassung nur die berechneten Aggregate paraphrasieren.
- **Whitelist-Sanitizer.** LLM-Output wird vor dem SQL-Aufruf in einer
  Whitelist gefiltert. Felder wie `evil_sql` oder `limit` ausserhalb der
  Erlaubnis-Liste werden verworfen.
- **Timeouts.** Filter-Call max. 15 s, Summary-Call max. 30 s. Bei Timeout
  gibt es einen Hinweis im Stream und das Frontend sieht weiterhin die
  rohen SQL-Treffer.
- **Logging.** Jede Anfrage geht in `LlmQuestionLog` mit `scenario=99` und
  `matched_mode='state_aid_ask'` — fuer spaetere Optimierung.
- **Pruefrelevanz-Hinweis.** Der Summary-Prompt verlangt am Ende den
  Pflicht-Disclaimer: *Diese Auswertung ist ein Arbeitsmittel; das
  pruefungsrechtliche Urteil obliegt dem Pruefer.* Das deckt sich mit dem
  globalen `DISCLAIMER` in `config.py`.

Pruefer-Hinweis (Plan §13): Auch wenn die Zusammenfassung lesbar ist, muss
der Pruefer die rohen SQL-Treffer im `results`-Event kontrollieren, bevor
er sich auf den Summary-Text stuetzt. Die Treffer enthalten `source_url`
und `case_url` zur Quelle und sollten bei Zweifeln direkt geprueft werden.

## 12. Datenqualitaet

Qualitaetskriterien:

- Jede Quelle hat Datenstand.
- Jede importierte Zeile hat Rohpayload.
- Jede normalisierte Zeile hat Quelle.
- Betrag wird nicht stillschweigend falsch umgerechnet.
- Karte zeigt nur echte vorhandene Genauigkeit.
- Falllinks werden als `Suchlink` oder `Direktlink` gekennzeichnet.
- Fuzzy-Treffer zeigen Score und Originalname.

Qualitaetsampel je Quelle:

- Gruen: stabile Quelle, gute Felder, hoher Normalisierungsgrad.
- Gelb: Quelle nutzbar, aber einzelne Felder fehlen.
- Rot: Quelle nicht harvestbar oder keine belastbaren Daten.

## 13. Fachliche Hinweise In Der UI

Pflichthinweis auf der Seite:

> Dieses Register bildet lokal gespeicherte, oeffentlich zugaengliche Beihilfe-Transparenzdaten ab. Die Vollstaendigkeit haengt vom Veroeffentlichungsweg der Mitgliedstaaten und vom letzten Harvest-Zeitpunkt ab.

Hinweis bei Karte:

> Die Karte aggregiert nach der in der Quelle vorhandenen regionalen Genauigkeit. Bei NUTS-Daten werden keine genaueren Standorte abgeleitet.

Hinweis bei KOM-Link:

> Die SA-Referenz verweist auf die Fallakte der Kommission. Ein direkter Entscheidungslink ist nur ausgewiesen, wenn er automatisiert eindeutig ermittelt wurde.

## 14. Akzeptanzkriterien

Phase 1 gilt als fertig, wenn:

- TAM fuer mindestens Deutschland erfolgreich geharvestet wird.
- Daten lokal gespeichert werden.
- Suche nach Unternehmensnamen mit Fuzzy-Logik funktioniert.
- Treffer Detailansicht mit SA-/KOM-Link zeigt.
- Karte nach NUTS-Region aggregiert.
- CSV- und PDF-Export funktionieren.
- Quellenstand und Vollstaendigkeitshinweis sichtbar sind.
- Harvest kann per Worker/Admin ausgelöst werden.
- Tests/Build laufen.

Phase 2 gilt als fertig, wenn:

- Weitere TAM-Laender geharvestet werden koennen.
- Externe Register als Quellenstatus sichtbar sind.
- Company-Dossier registeruebergreifend funktioniert.

## 15. Umsetzungspakete Fuer Claude Code

### Paket A: Technische Quellenanalyse

- TAM Search HTTP-Flow analysieren.
- Ergebnisstruktur dokumentieren.
- Pagination/Exportmoeglichkeiten pruefen.
- Entscheidung treffen: HTTP Parser vs. Browser Automation.
- Ergebnis in `docs/state-aid-source-analysis.md` dokumentieren.

### Paket B: Backend-Datenmodell

- Tabellen/Migrationen fuer State-Aid-Awards und Harvest-Runs erstellen.
- Service fuer Normalisierung bauen.
- SA-Referenz-Erkennung implementieren.
- Tests fuer Normalisierung.

### Paket C: TAM-Harvester

- `harvest_state_aid.py` erstellen.
- Check/Force/Limit/Country-Modi.
- Raw- und normalized-Speicherung.
- Fehlerrobustheit und Logs.

### Paket D: Backend-API

- Router `state_aid.py`.
- Search endpoint mit Fuzzy-Suche.
- Map endpoint mit NUTS-Aggregation.
- Detail endpoint.
- Exportdaten endpoint falls noetig.

### Paket E: Frontend-Seite

- Route `/beihilfen`.
- Suchpanel, Ergebnisliste, Detailpanel.
- Kartenansicht.
- Quellenstatus.
- Exportbuttons.

### Paket F: Cross-Register Company Dossier

- Gemeinsame Suche gegen:
  - Beguenstigtenverzeichnis
  - Beihilfe-Register
  - Sanktionslisten
- Zusammenfassungsansicht.
- Export als Pruefnotiz.

### Paket G: QA Und Live

- `python3 -m py_compile` fuer Backend-Dateien.
- Frontend `npm run build`.
- Docker Compose Rebuild.
- Live Smoke:
  - Suche Unternehmen
  - Karte oeffnen
  - Detailansicht
  - KOM-Link
  - CSV/PDF Export

## 16. Risiken Und Entscheidungen

Offene technische Risiken:

- TAM hat eventuell kein dokumentiertes Bulk-API.
- Suchergebnisse koennen serverseitig limitiert sein.
- CSRF/Formularstruktur kann sich aendern.
- Externe nationale Register haben unterschiedliche Datenformate.
- Direkte KOM-Entscheidungslinks sind eventuell nicht fuer jede SA-Referenz maschinenlesbar.

Entscheidungen:

- Erst TAM Deutschland als vertikaler Slice.
- Danach EU-weite Erweiterung.
- Keine Scheingenauigkeit auf der Karte.
- Lokale Suche und lokale Speicherung haben Vorrang.
- Vollstaendigkeit immer transparent kommunizieren.

### 16.5 Auto-Harvest Scheduler-Hook

Der bestehende `services/scheduler.py` (Plan v3.2 §16, taeglicher Tick alle
5 Minuten) wurde um einen State-Aid-Auto-Harvest erweitert. Lifespan-Task,
kein separater Worker-Container.

**Konfiguration ueber Umgebungsvariablen:**

| Variable | Default | Bedeutung |
| --- | --- | --- |
| `STATE_AID_AUTO_HARVEST` | `true` | An-/Aus-Schalter |
| `STATE_AID_AUTO_HARVEST_SOURCES` | `tam_de,tam_at` | Komma-Liste der Source-Keys |
| `STATE_AID_AUTO_HARVEST_HOUR` | `4` | UTC-Stunde des Tagesfensters |
| `STATE_AID_AUTO_HARVEST_LIMIT` | `5000` | Max. Awards pro Source/Tag |

**Verhalten:**

- Im Tagesfenster (`now.hour == STATE_AID_AUTO_HARVEST_HOUR`) wird geprueft,
  ob seit dem letzten cron-Lauf >= 22 Stunden vergangen sind. Wenn ja:
  einmaliger Harvest pro Source.
- Pro Source wird `run_harvest(mode="smart")` mit `triggered_by="cron"` und
  `limit=STATE_AID_AUTO_HARVEST_LIMIT` aufgerufen. Smart-Mode nutzt
  automatisch das `last_successful_harvest_at` der Source (-14 Tage
  Lookback) als `since`-Wert.
- Country-Code wird aus `StateAidSource.country_code` gelesen, sonst
  Fallback `tam_de` -> `DEU`, `tam_at` -> `AUT`.
- Fehler pro Source unterbrechen den Loop nicht — naechste Source wird
  abgearbeitet. Pro Fehler wird eine `Notification` (kind:
  `admin_harvest_failed`) an alle Admins gepusht (Bell-Icon).
- DB-Sessions ueber `SessionLocal()` mit `try/finally close`, blocking-Code
  laeuft via `asyncio.to_thread`, damit der Scheduler-Tick nicht blockt.

