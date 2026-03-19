# Auditworkshop — Projektbeschreibung

## 1. Ziel und Zweck

Der **Auditworkshop** ist eine standalone Webanwendung für den Workshop *„KI und LLMs in der EFRE-Prüfbehörde"*. Er demonstriert sechs praxisnahe Szenarien, in denen ein lokal betriebenes Large Language Model (Qwen3-14B via Ollama) Prüfer bei der Verwaltungskontrolle von EFRE-geförderten Vorhaben unterstützt.

**Kernziele:**

- **Praxisdemonstration:** Sechs Live-Szenarien zeigen konkrete Einsatzmöglichkeiten von KI im Prüfwesen — von der Dokumentenanalyse bis zur Risikoerkennung.
- **Vollwertiges Checklisten-System:** Keine Vereinfachung — das Datenmodell aus `audit_designer` (Projekte, Checklisten, Fragen, KI-Bemerkungen, Evidence) ist vollständig übernommen.
- **Optimierungsfeld:** Verbesserungen werden hier mit echten EFRE-Daten getestet und danach als Patches in `audit_designer` und `flowinvoice` zurückgespielt.
- **DSGVO-konform:** Alle Daten bleiben lokal. Kein Cloud-LLM, kein Internetversand. Vor dem Workshop werden echte Daten durch anonymisierte Demo-Daten ersetzt.

**Hardware:** ASUS NUC 15 mit RTX 5070 Ti (16 GB VRAM, eGPU via Thunderbolt 4). Embedding-Modell auf CPU.

---

## 2. Architektur

```
┌──────────────┐     ┌───────────────────┐     ┌────────────────┐
│   Frontend   │────▶│     Backend       │────▶│  PostgreSQL    │
│  React 19    │     │   FastAPI 0.115   │     │  16 + pgvector │
│  Port 3000   │     │   Port 8000       │     │  Port 5434     │
│  (nginx)     │     │                   │     │                │
└──────────────┘     │  ┌─────────────┐  │     │  knowledge_    │
                     │  │ Ollama      │  │     │  chunks (RAG)  │
                     │  │ qwen3:14b   │◀─┤     │                │
                     │  │ Host:11434  │  │     │  workshop_*    │
                     │  └─────────────┘  │     │  (Checklisten) │
                     │                   │     │                │
                     │  ┌─────────────┐  │     │  workshop_df_* │
                     │  │ Sentence    │  │     │  (DataFrames)  │
                     │  │ Transformer │  │     │                │
                     │  │ (CPU, 768d) │  │     └────────────────┘
                     │  └─────────────┘  │
                     └───────────────────┘
```

| Komponente | Technologie | Details |
|------------|-------------|---------|
| Frontend | React 19 + TypeScript + Tailwind CSS 4 | Vite 8, Leaflet, Lucide Icons |
| Backend | FastAPI + SQLAlchemy 2.0 | 35+ API-Endpunkte, SSE-Streaming |
| Datenbank | PostgreSQL 16 + pgvector | RAG-Chunks + Checklisten + DataFrames |
| LLM | Ollama (Host) | qwen3:14b (primär), Fallback: qwen3:8b |
| Embeddings | paraphrase-multilingual-mpnet-base-v2 | 768 Dimensionen, CPU |
| Deployment | Docker Compose | 3 Container (db, backend, frontend) |

---

## 3. Die sechs Workshop-Szenarien

### Szenario 1 — Dokumentenanalyse
**Aufgabe:** Auflagen und Nachweispflichten aus Förderbescheiden extrahieren.
**Flow:** Prüfer lädt PDF/DOCX hoch → Backend parst Dokument → LLM extrahiert strukturiert alle bindenden Auflagen mit Fristen und Nachweisarten.
**System-Prompt:** Nummerierte Liste, keine prüfrechtlichen Urteile, Unsicherheiten kennzeichnen.

### Szenario 2 — Checklisten-KI
**Aufgabe:** VKO-Prüfpunkte mit KI-Unterstützung bewerten.
**Flow:** 25 vorkonfigurierte Prüfpunkte (VKO EFRE 2021-2027) → Einzeln oder alle per „Alle bewerten" → LLM erzeugt Begründung + Fundstelle als JSON → Prüfer akzeptiert, bearbeitet oder lehnt ab.
**Vollwertiges Modell:** Accept/Reject/Edit-Zyklus, Evidence-Verknüpfung, Status-Tracking.

### Szenario 3 — Halluzinations-Demo
**Aufgabe:** Risiken von KI-Halluzinationen demonstrieren (Split-View).
**Flow:** Gleiche Frage → einmal ohne RAG-Kontext (KI erfindet Artikelnummern) → einmal mit RAG-Kontext (KI zitiert nur aus der Wissensdatenbank).
**Toggle:** „RAG-Kontext aktivieren" an/aus.

### Szenario 4 — Berichtsentwurf
**Aufgabe:** Prüffeststellungen in Berichtpassagen formulieren.
**Flow:** Prüfer gibt Stichpunkte ein → LLM formuliert sachlich-verwaltungsrechtliche Berichtpassage → Je Feststellung: Sachverhalt, Bewertung, Empfehlung.
**Stilregeln:** Indikativ, Perfekt, keine wertenden Adjektive.

### Szenario 5 — Vorab-Upload & RAG
**Aufgabe:** Eigene Dokumente in die Wissensdatenbank laden und per RAG befragen.
**Flow:** PDF/XLSX/DOCX hochladen → automatisch gechunkt + embedded → Fragen an die Wissensdatenbank stellen → LLM antwortet mit Quellenverweisen.
**Formate:** PDF, XLSX, XLS, XLSM, DOCX, DOCM, HTML, RTF, TXT.

### Szenario 6 — Begünstigtenverzeichnis
**Aufgabe:** EFRE-Begünstigtenverzeichnisse aus beliebigen Bundesländern einlesen, auf Karte darstellen, statistisch auswerten.
**Flow:**
1. XLSX hierher ziehen → Bundesland, Fonds, Förderperiode werden **automatisch erkannt** (aus Titelzeilen der Datei).
2. Spalten werden **automatisch zugeordnet** (Name, Standort, Kosten, Kategorie — funktioniert mit verschiedenen Spaltenformaten).
3. Standorte werden **geocodiert** (Nominatim, persistenter Cache).
4. **Interaktive Leaflet-Karte** zeigt alle Vorhaben, farbcodiert nach Bundesland.
5. Mehrere Verzeichnisse können parallel geladen werden (z.B. Hessen + Sachsen).
6. **Duplikate** (gleiches Bundesland + Fonds) werden erkannt und ersetzt.
7. LLM-Prompt darunter für statistische Fragen.

---

## 4. Funktionen im Detail

### 4.1 Checklisten-System (vollwertig, aus audit_designer)

```
┌────────────────────┬────────────────────────────────────────┐
│ Fragen-Liste (40%) │ Frage-Detail (60%)                     │
│                    │                                        │
│ [Status-Legende]   │ Frage-Text + Antwort-Eingabe           │
│ ✓ ✗ ✎ ✎ —         │ (Ja/Nein/Entfällt oder Freitext)       │
│                    │                                        │
│ ── Bescheid ──     │ Manuelle Bemerkung (Textarea)          │
│ ✓ 1.1 Zuwendungs..│                                        │
│ ✎ 1.2 Förderbed.. │ ⚡ KI-Bemerkung                        │
│ — 1.3 Förderfäh.. │ [Akzeptieren] [Bearbeiten] [Ablehnen]  │
│                    │                                        │
│ ── Vergabe ──      │ Belege / Evidence                      │
│ ✗ 2.1 Vergaber... │ ├─ VO 2021/1060 Chunk 3  (Score: 0.92) │
│ ✎ 2.2 Vergabeve.. │ └─ EFRE-RL Chunk 7       (Score: 0.85) │
│                    │                                        │
│ [+ Frage]          │                                        │
└────────────────────┴────────────────────────────────────────┘
```

**Datenmodell:**
- **WorkshopProject:** Aktenzeichen, Geschäftsjahr, Zuwendungsempfänger, Fördersumme, Gesamtkosten
- **WorkshopChecklist:** Name, Beschreibung, Template-Referenz → 1:N Fragen
- **WorkshopQuestion:** question_key (hierarchisch, z.B. „2.3"), answer_type (boolean/date/amount/text), Antwort, manuelle Bemerkung, KI-Bemerkung, KI-Status, Ablehnungsbegründung
- **WorkshopEvidence:** Quelle, Dateiname, Chunk-Referenz, Textauszug, Relevanz-Score

**KI-Bewertungs-Workflow:**

| Status | Farbe | Buttons |
|--------|-------|---------|
| Kein KI | grau | [KI-Bemerkung generieren] |
| draft | amber | [Akzeptieren] [Bearbeiten] [Ablehnen] |
| accepted | grün | [Bearbeiten] |
| edited | blau | [Bearbeiten] |
| rejected | rot | [Regenerieren] [Bearbeiten] + Ablehnungsgrund |

**Features:** Demo-Seed (25 VKO-Fragen), Bulk-Assessment (alle Fragen auf einmal), Keyboard-Navigation (↑↓), Debounced Auto-Save, Fragen-CRUD.

### 4.2 Wissensdatenbank (pgvector RAG)

```
┌─────────────────────────────────────────────────────┐
│  Wissensdatenbank         [25 Dokumente · 306 Chunks]│
├─────────────────────────────────────────────────────┤
│  ┌─── Frage stellen ─────────────────────────────┐  │
│  │ [Freitext                            ] [Fragen]│  │
│  │ LLM-Streaming-Antwort mit Quellenangaben...    │  │
│  └────────────────────────────────────────────────┘  │
│  ┌─── Semantische Suche ─────────────────────────┐  │
│  │ [Suchbegriff                        ] [Suchen] │  │
│  │ VO_2021_1060  Score: 0.94  „Artikel 74..."     │  │
│  └────────────────────────────────────────────────┘  │
│  ┌─── Quellen verwalten ─────────────────────────┐  │
│  │ EFRE_PROGRAMM_HESSEN     38 Chunks    [×]     │  │
│  │ EFRE_FOERDERRICHTLINIE   36 Chunks    [×]     │  │
│  │ [Datei hochladen] Source: [____]               │  │
│  └────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

**Vorgeladene Dokumente (25 Stück, 306 Chunks):**
- EFRE-Programm Hessen 2021-2027 (38 Chunks)
- EFRE-Förderrichtlinie 21+ (36 Chunks)
- 4 Förderaufrufe (17 Chunks)
- 7 Merkblätter (Vergabe, Belegaufbewahrung, Gemeinkosten, Gleichstellung, Grundrechte, Nachhaltigkeit, Sachleistungen)
- Länderbericht Deutschland 2019 (81 Chunks)
- EFRE-Umweltbericht (61 Chunks)
- Zusammenfassende Erklärung, Informationsbroschüre, Zeitplan

**Pipeline:** Datei → `file_parser.py` (PDF/XLSX/DOCX/HTML/RTF/TXT) → Wort-Chunking (700 Wörter, 150 Overlap) → Embedding (768 Dim, CPU) → pgvector INSERT (UPSERT).

### 4.3 Datenanalyse (DataFrame → SQL)

**Zweck:** XLSX-Dateien als echte SQL-Tabellen in PostgreSQL speichern und direkt abfragen.

```
┌─────────────────────┬──────────────────────────────────┐
│ Tabellen            │ SQL-Abfrage                      │
│                     │                                  │
│ ▸ hessen_efre       │ SELECT name, kosten              │
│   182 Zeilen        │ FROM {table}                     │
│ ▸ sachsen_efre      │ ORDER BY kosten DESC             │
│   5763 Zeilen       │ LIMIT 5                          │
│                     │                                  │
│ [XLSX hochladen]    │ ┌────────────────────────────┐   │
│                     │ │ CBI GmbH    20.864.000 EUR │   │
│                     │ │ Solarwärme  16.298.640 EUR │   │
│                     │ └────────────────────────────┘   │
└─────────────────────┴──────────────────────────────────┘
```

**Features:**
- Smart Header-Detection (findet Kopfzeile auch bei 3-6 Titelzeilen)
- Zweisprachige Header werden bereinigt (DE/EN → nur DE)
- SQL-Abfragen im Browser (nur SELECT, Ctrl+Enter)
- Automatische Statistik-Zusammenfassung (Min/Max/Avg/Summe für numerische Spalten)
- SQL-Injection-Schutz (Blockliste + LIMIT 1000)
- Beispiel-Queries per Button-Klick

### 4.4 KI-Pipeline-Widget

Aufklappbares Widget auf der Startseite. Zeigt den vollständigen Inferenz-Pfad:

```
PDF → OCR → Parser & Chunker → NUC 15 → GPU 0 (RTX 5060 Ti) → LLM-Antwort
                                       → GPU 1 (RTX 5070 Ti)    (Streaming)
                                         eGPU via Thunderbolt 4
```

**Live-Metriken (3s Polling):** GPU-Auslastung, VRAM, Temperatur, Watt, CPU%, RAM, Ollama-Worker, aktive Modelle, Netzwerk-I/O. Animierte Datenfluss-Punkte, rotierende GPU-Lüfter, pulsierende VRAM-Balken.

### 4.5 Begünstigten-Karte (Leaflet)

```
┌─────────────────────────────────────────────────────┐
│  ┌─ XLSX hierher ziehen ─────────────────────────┐  │
│  │  Bundesland, Fonds und Förderperiode werden   │  │
│  │  automatisch erkannt · Duplikate ersetzt      │  │
│  └───────────────────────────────────────────────┘  │
│                                                     │
│  ● Hessen EFRE 175/182  ● Sachsen EFRE 5025/5763   │
│                                                     │
│  ┌─ Karte ──────────────────────────────────────┐   │
│  │  5.200 Vorhaben · 1,94 Mrd €                │   │
│  │                                              │   │
│  │       ●●● Sachsen (grün)                     │   │
│  │    ● Hessen (blau)                           │   │
│  │                                              │   │
│  ├──────────────────────────────────────────────┤   │
│  │  ● Hessen  ● Sachsen    Größe = Kosten (log)│   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

**Automatische Erkennung:**
- **Bundesland:** Aus Titelzeilen (z.B. „Freistaat Sachsen", „Programm des Landes Hessen")
- **Fonds:** EFRE, ESF, ESF+, ELER, JTF, etc.
- **Periode:** 2014-2020, 2021-2027
- **Spalten:** Name, Standort, Kosten, Kategorie — durch Pattern-Matching auf Spaltennamen (funktioniert mit verschiedenen Formaten: kombiniertes „Standortindikator", getrennte „PLZ" + „Ort", nur „Landkreis")

**Duplikat-Erkennung:** Gleiches Bundesland + Fonds → alte Version wird automatisch ersetzt.

---

## 5. GUI-Übersicht

### Navigation (Sidebar, links, 264px)

```
┌──────────────────────┐
│  Auditworkshop       │
│  KI in der EFRE-     │
│  Prüfbehörde         │
├──────────────────────┤
│  Home                │
│  1 · Dokumenten-     │
│      analyse         │
│  2 · Checklisten-KI  │
│  3 · Halluzination   │
│  4 · Berichtsentwurf │
│  5 · Vorab-Upload    │
│  6 · Begünstigte     │
│  ────────────────    │
│  Projekte            │
│  Wissensbasis        │
│  Datenanalyse        │
└──────────────────────┘
```

### TopBar (oben, 48px)
- Links: Ollama-Status (verbunden/offline + Modellname)
- Rechts: Dark-Mode-Toggle (Mond/Sonne)

### Design-System

| Element | Light | Dark |
|---------|-------|------|
| Primary | Indigo-600 | Indigo-400 |
| Accepted | Green-600 | Green-400 |
| Rejected | Red-600 | Red-400 |
| Draft | Amber-600 | Amber-400 |
| Edited | Blue-600 | Blue-400 |
| Background | Slate-50 | Slate-950 |
| Card | White | Slate-900 |

Dark Mode: System-Preference-Detection + manueller Toggle. Tailwind `dark:` Klassen.

---

## 6. Aktueller Stand (Soll vs. Ist)

| Merkmal | Soll | Ist | Status |
|---------|------|-----|--------|
| 6 Workshop-Szenarien mit SSE-Streaming | Alle 6 live-fähig | Alle 6 implementiert | ✅ |
| Vollwertiges Checklisten-System (aus audit_designer) | CRUD + KI-Assessment + Accept/Reject/Edit | Vollständig | ✅ |
| VKO-Template mit 25 Prüfpunkten | Vorkonfiguriert, per Button ladbar | 25 Fragen, 8 Kategorien | ✅ |
| Wissensdatenbank (pgvector RAG) | Upload, Suche, Ingest, Fragen stellen | 25 Dokumente, 306 Chunks | ✅ |
| EFRE OP-Dokumente vorgeladen | Programm, Richtlinie, Merkblätter, Aufrufe | 25 PDFs eingelesen | ✅ |
| Multi-Format Datei-Upload | PDF, XLSX, DOCX, HTML, RTF, TXT | 10 Formate, serverseitiges Parsing | ✅ |
| DataFrame-Tabellen (XLSX → SQL) | Upload, SQL-Abfragen, Statistiken | 4+ Tabellen, Smart Header-Detection | ✅ |
| Begünstigtenverzeichnis-Karte (Leaflet) | Upload → Auto-Erkennung → Geocoding → Karte | Hessen + Sachsen getestet | ✅ |
| Auto-Erkennung Bundesland/Fonds/Periode | Aus XLSX-Titelzeilen | 16 Bundesländer, 10 Fonds | ✅ |
| Duplikat-Erkennung bei Verzeichnissen | Gleiches BL+Fonds → ersetzen | Funktioniert | ✅ |
| KI-Pipeline-Widget mit Live-GPU-Stats | Animiert, 3s Polling | Vollständig portiert | ✅ |
| Dark Mode | System-Preference + Toggle | Funktioniert | ✅ |
| Docker-Deployment | 3 Container, Health Checks | auditworkshop-db/backend/frontend | ✅ |
| DSGVO-konform (lokale Inferenz) | Kein Cloud-LLM | Ollama auf Host | ✅ |
| Halluzinations-Demo (mit/ohne RAG) | Toggle-Switch, Vergleichsansicht | Implementiert | ✅ |
| Demo-Daten Seed + Reset | Per Button im Frontend | Seed + Reset vorhanden | ✅ |
| Szenario 6: Leaflet-Karte | Interaktiv mit Filtern | Farbcodiert, Auto-Zoom, Popups | ✅ |
| Multi-Bundesland-Support | Beliebige Verzeichnisse | Getestet: Hessen (182) + Sachsen (5.763) | ✅ |
| Geocoding mit Cache | Persistenter Cache | 5.200+ Standorte gecacht | ✅ |
| SQL-Injection-Schutz | Blockliste + Parametrisierung | Implementiert | ✅ |
| Keyboard-Navigation in Checkliste | ↑↓ Pfeiltasten | Funktioniert | ✅ |
| Aria-Labels / Accessibility | Grundlegende a11y | Vorhanden | ✅ |
| Projekt bearbeiten (Frontend) | Edit-Modal | Edit-Modal auf ProjectDetailPage | ✅ |
| Error Boundary (Frontend) | Absturzsichere Darstellung | ErrorBoundary in AppShell | ✅ |
| Teilnehmer-Mitmach-Hinweis | Upload/Fragen/QR erklaert | "So koennen Sie mitmachen" auf HomePage | ✅ |
| Checklisten-Export (PDF/CSV) | Ergebnisse exportieren | CSV + Print-PDF auf ChecklistPage | ✅ |
| Ollama-Offline-Hinweis | Klarer Fehlertext | TopBar zeigt "ollama serve" Hinweis | ✅ |
| E2E-Tests | Automatisierte Tests | Keine | ⚠️ |

---

## 7. Start und Betrieb

```bash
# Container starten
cd /home/janpow/Projekte/Workshop/flowworkshop_grundgeruest
docker compose up -d

# Wissensdatenbank einlesen (einmalig, ~5 Min)
docker exec auditworkshop-backend python scripts/ingest_all.py --knowledge

# Demo-Daten laden (optional)
curl -X POST http://localhost:8000/api/demo/seed

# Öffnen
# Frontend: http://localhost:3000
# Backend:  http://localhost:8000/docs (Swagger)
```

**Container:**

| Container | Port | Status |
|-----------|------|--------|
| auditworkshop-db | 5434 | healthy |
| auditworkshop-backend | 8000 | healthy |
| auditworkshop-frontend | 3000 | running |

---

## 8. Zusammenhang mit anderen Projekten

| Projekt | Beziehung |
|---------|-----------|
| **audit_designer** | Checklisten-Datenmodell übernommen (VpProject → WorkshopProject, VpQuestion → WorkshopQuestion). Verbesserungen fließen als Patches zurück. |
| **flowinvoice** | PDF-Parser-Pattern übernommen (3-Stufen-Fallback). Ollama-Streaming-Muster geteilt. |
| **regulierung** | PipelineWidget (583 Zeilen) portiert. gpu_stats_server-Logik als FastAPI-Routen integriert. |
| **flowstat** | Statistik-Methoden als Referenz für Begünstigten-Auswertung. |

---

*Stand: 14. März 2026 · Version 2.0*
