# Workshop-Demo — Vollständiges Planungsdokument

**Projektbezeichnung:** FlowWorkshop  
**Zweck:** Eigenständige Workshop-Demo-Anwendung „KI und LLMs in der EFRE-Prüfbehörde"  
**Basis:** Neues eigenständiges Projekt — Elemente aus flowinvoice und audit_designer werden übernommen  
**Zielarchitektur:** React + FastAPI + Ollama (lokal), Single-Container-Stack  
**Stand:** März 2026

---

## 1. Projektstruktur (Ziel)

```
flowworkshop/
├── backend/
│   ├── main.py                     ← FastAPI-Instanz
│   ├── routers/
│   │   ├── workshop.py             ← Streaming-Endpunkte (alle 4 Szenarien)
│   │   ├── documents.py            ← Demo-Dokumente und Datei-Upload
│   │   └── system.py               ← GPU/System-Stats (aus gpu_stats_server.py)
│   ├── services/
│   │   ├── ollama_service.py       ← Aus audit_designer VP-AI übernommen
│   │   ├── pdf_parser.py           ← Aus flowinvoice übernommen (Multi-Level)
│   │   └── chunker.py              ← Aus flowinvoice übernommen
│   ├── data/
│   │   └── demo_documents/         ← Anonymisierte Musterdokumente
│   │       ├── foerderbescheid.py
│   │       ├── checkliste.py
│   │       ├── prueffeststellungen.py
│   │       └── eu_verordnung.py
│   └── config.py
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── PresenterToolbar.tsx
│   │   │   ├── SzenarioCard.tsx
│   │   │   ├── DocumentDropzone.tsx   ← Aus flowinvoice übernommen
│   │   │   ├── LlmResponsePanel.tsx   ← Streaming-Ausgabe
│   │   │   ├── ChecklistTable.tsx     ← Aus audit_designer übernommen
│   │   │   ├── HalluzinationsSwitch.tsx
│   │   │   ├── SprechzettelPanel.tsx
│   │   │   └── PipelineDisplay.tsx    ← workshop_ki_pipeline.html integriert
│   │   ├── pages/
│   │   │   ├── WorkshopHome.tsx
│   │   │   ├── Szenario1.tsx
│   │   │   ├── Szenario2.tsx
│   │   │   ├── Szenario3.tsx
│   │   │   └── Szenario4.tsx
│   │   └── App.tsx
├── docker-compose.yml
├── CLAUDE.md                        ← Projektkontext für Claude Code CLI
└── README.md
```

---

## 2. Aus flowinvoice zu übernehmende Elemente

| Element | Quelle | Zweck im Workshop |
|---|---|---|
| `pdf_parser.py` (Multi-Level) | `flowinvoice/backend/services/` | Szenario 1 + 2: PDF-Extraktion |
| `chunker.py` | `flowinvoice/backend/services/` | Kontextvorbereitung für LLM |
| `DocumentDropzone` | `flowinvoice/frontend/src/components/` | Upload in Szenarien 1, 2, 4 |
| Ollama-Service (llama-Anbindung) | `flowinvoice/backend/services/ollama_service.py` | Basis für Workshop-Streaming |
| Docker-Compose-Muster | `flowinvoice/docker-compose.yml` | Angepasstes Single-Stack-Setup |

## 3. Aus audit_designer zu übernehmende Elemente

| Element | Quelle | Zweck im Workshop |
|---|---|---|
| `ChecklistDesigner`-Datenstruktur | `audit_designer/backend/models/` | Szenario 2: Checklisten-Anzeige |
| VP-AI Ollama-Integration | `audit_designer/backend/services/vpai/ollama.py` | Streaming-Service |
| Wissensdatenbank-Suche | `audit_designer/backend/routers/knowledge.py` | Szenario 3: RAG-Demo |
| Checklisten-Anzeige-Komponente | `audit_designer/frontend/src/components/` | Szenario 2: KI-Einschätzung-Spalte |
| System-Prompts-Muster | `audit_designer` CLAUDE.md / vp_ai.md | Basis für Workshop-Prompts |

---

## 4. Die vier Szenarien (Implementierungsdetails)

### Szenario 1 — Dokumentenanalyse

Das Modell extrahiert aus einem Förderbescheid alle bindenden Auflagen mit Nachweispflichten. Didaktischer Effekt: Zeitersparnis gegenüber manueller Durchsicht sichtbar machen.

**Backend-Endpunkt:** `POST /api/workshop/stream` mit `scenario=1`

**System-Prompt:**
```
Du bist ein Hilfswerkzeug für EFRE-Prüfer. Analysiere Förderdokumente
strukturiert und präzise. Extrahiere Auflagen und Nachweispflichten.
Weise ausdrücklich auf Unsicherheiten hin. Formuliere keine
prüfrechtlichen Urteile — das Urteil obliegt dem Prüfer.
```

**Schritte im UI:**
1. Demo-Dokument laden (Button) oder eigene Datei hochladen.
2. Prompt anzeigen und live editieren lassen.
3. Streaming-Ausgabe mit Unsicherheits-Markierung.
4. Hinweiskasten: „Diese Auswertung ist ein Arbeitsmittel."

**Sprechzettel-Inhalte:**
- Timing: Qwen3-14B braucht ca. 15–25 Sekunden für dieses Szenario.
- Rückfrage „Kann das Modell das auswendig lernen?" → Nein, kein Gedächtnis zwischen Anfragen.
- Hinweis auf Token-Limit bei sehr langen Dokumenten.

---

### Szenario 2 — Checklisten-Unterstützung

Das Modell gleicht eine EFRE-VKO-Checkliste gegen vorliegende Unterlagen ab und liefert vorläufige Einschätzungen (erfüllt / nicht erfüllt / nicht beurteilbar). Die Checklisten-Komponente aus dem audit_designer wird im Read-only-Modus mit zusätzlicher KI-Spalte gezeigt.

**Backend-Endpunkt:** `POST /api/workshop/stream` mit `scenario=2`

**System-Prompt:**
```
Du bist ein Hilfswerkzeug für EFRE-Prüfer. Beurteile jeden Prüfpunkt
der folgenden Checkliste ausschließlich auf Basis der vorgelegten
Unterlagen. Gib das Ergebnis als JSON zurück im Format:
[{"id": "...", "status": "erfüllt|nicht_erfüllt|nicht_beurteilbar",
"begruendung": "...", "fundstelle": "..."}]
Erfinde keine Informationen. Weise explizit auf fehlende Nachweise hin.
```

**Schritte im UI:**
1. Demo-Checkliste laden (12 VKO-Prüfpunkte).
2. Demo-Unterlagen laden (Bescheid + Vergabeunterlagen).
3. Modell gibt JSON aus — Backend parsed und befüllt Tabelle.
4. Farbkodierte Spalte „KI-Einschätzung" (grün/rot/grau).
5. Jede Einschätzung ist per Klick überschreibbar.

**Sprechzettel-Inhalte:**
- Kernbotschaft: Das Modell bereitet vor, es entscheidet nicht.
- Rückfrage „Was wenn das Modell falsch liegt?" → Der Prüfer überschreibt, trägt die Verantwortung.
- Rechtlicher Bezug: Artikel 63 EU-Haushaltsordnung (VO EU/Euratom 2018/1046).

---

### Szenario 3 — Regulatorische Recherche und Halluzinationsdemo

Das stärkste didaktische Element: Dieselbe Frage zu Artikel 74 VO (EU) 2021/1060 wird einmal ohne und einmal mit Dokumentkontext gestellt. Der direkte Vergleich macht das Halluzinationsrisiko begreifbar.

**Backend-Endpunkt:** `POST /api/workshop/stream` mit `scenario=3`, Parameter `with_context: bool`

**System-Prompt ohne Kontext:**
```
Du bist ein Hilfswerkzeug für EFRE-Prüfer. Beantworte die folgende
Frage zu EU-Verordnungen so präzise wie möglich.
```

**System-Prompt mit Kontext:**
```
Du bist ein Hilfswerkzeug für EFRE-Prüfer. Beantworte die folgende
Frage ausschließlich auf Basis der beigefügten Dokumente. Erfinde
keine Artikelnummern. Zitiere immer die genaue Fundstelle.
Wenn die Antwort nicht im Dokument steht, sage das explizit.
```

**Schritte im UI:**
1. HalluzinationsSwitch steht auf „Ohne Kontext".
2. Frage stellen: „Welche Anforderungen stellt Artikel 74 der Dachverordnung an risikobasierte Verwaltungskontrollen?"
3. Modell halluziniert Artikelnummern — Warnhinweis erscheint im Panel.
4. Switch umlegen auf „Mit Kontext" — EU-Verordnungstext aus Wissensdatenbank wird geladen.
5. Erneute Anfrage — präzise, quellengestützte Antwort.
6. Split-View zeigt beide Antworten nebeneinander.

**Sprechzettel-Inhalte:**
- Kernbotschaft: RAG ist die produktive Antwort auf Halluzination — die Wissensdatenbank des audit_designer ist genau dafür gebaut.
- Rückfrage „Kann man dem Modell vertrauen?" → Mit Kontext ja, ohne Kontext nein. Die Prüfbehörde muss das Setup kontrollieren.
- Hinweis EU AI Act: Artikel 13 (Transparenzpflichten), Anhang III Hochrisikosysteme.

---

### Szenario 4 — Berichtsentwurf

Das Modell formuliert aus Prüffeststellungen eine Berichtpassage. Zeigt Stärke bei Rohformulierung und Schwäche beim fachlichen Urteil.

**Backend-Endpunkt:** `POST /api/workshop/stream` mit `scenario=4`

**System-Prompt:**
```
Du bist ein Hilfswerkzeug für EFRE-Prüfer. Formuliere auf Basis der
folgenden Prüffeststellungen eine Berichtpassage für einen
EFRE-Vorhabenprüfungsbericht. Stil: sachlich, verwaltungsrechtlich
präzise, im Indikativ. Jede Feststellung erhält einen eigenen Absatz
mit: (1) Sachverhalt, (2) Bewertung, (3) Empfehlung. Keine
Aufzählungszeichen. Keine Einleitungsfloskeln. Perfekt statt
Präteritum — außer bei „war", „hatte", Modalverben.
```

**Schritte im UI:**
1. Demo-Feststellungen laden (4 Stichpunkte).
2. Prompt anzeigen — Stilanforderungen sind sichtbar.
3. Split-View: Links Feststellungen, rechts editierbarer Entwurf.
4. Kopieren-Button überführt in Zwischenablage.

**Sprechzettel-Inhalte:**
- Kernbotschaft: Das Modell formuliert, der Prüfer verantwortet.
- Hinweis: Der Stil-Prompt ist entscheidend für die Qualität — live demonstrieren, was passiert wenn man ihn weglässt.
- Rechtlicher Bezug: Artikel 63 VO (EU, Euratom) 2018/1046 — Verantwortung bei der Prüfperson.

---

## 5. Backend-Spezifikation

### 5.1 Streaming-Endpunkt

```python
# POST /api/workshop/stream
class WorkshopStreamRequest(BaseModel):
    scenario: int                    # 1–4
    prompt: str                      # Nutzerprompt (editierbar)
    documents: list[str] = []        # Extrahierter Dokumenttext
    with_context: bool = True        # Szenario 3: Kontext an/aus
    demo_doc: str | None = None      # Name des Demo-Dokuments

# Response: StreamingResponse (Server-Sent-Events)
# Format: data: {"token": "...", "done": false}\n\n
```

### 5.2 Demo-Dokument-Endpunkt

```python
# GET /api/workshop/demo/{name}
# name: foerderbescheid | checkliste | feststellungen | eu_verordnung
# Response: {"text": "...", "label": "...", "pages": 3}
```

### 5.3 GPU/System-Stats-Endpunkt

```python
# GET /api/system/gpu   → nvidia-smi Metriken
# GET /api/system/info  → CPU, RAM, Ollama-Worker
# (Logik aus gpu_stats_server.py direkt integriert)
```

### 5.4 System-Prompts (zentral verwaltet)

```python
# backend/config.py
SYSTEM_PROMPTS = {
    1: "Du bist ein Hilfswerkzeug für EFRE-Prüfer...",
    2: "Du bist ein Hilfswerkzeug für EFRE-Prüfer...",
    "3_ohne": "Du bist ein Hilfswerkzeug für EFRE-Prüfer...",
    "3_mit":  "Du bist ein Hilfswerkzeug für EFRE-Prüfer...",
    4: "Du bist ein Hilfswerkzeug für EFRE-Prüfer...",
}
```

---

## 6. Frontend-Spezifikation

### 6.1 WorkshopHome

Vier Szenario-Karten im 2×2-Grid mit Nummer-Badge, Titel, Kurzbeschreibung. Darunter: Pipeline-Anzeige (PipelineDisplay-Komponente mit workshop_ki_pipeline.html integriert, live GPU-Stats). Demo-Modus-Toggle blendet PresenterToolbar ein.

### 6.2 PresenterToolbar

Sticky Header: Szenario-Titel, Schritt-Indikator (z. B. „2 / 4"), Ollama-Status (grüner Dot), Modellname, Toggle Sprechzettel, ← → Navigation zwischen Schritten. Keyboard-Shortcut: `Alt+N` für Sprechzettel, `Alt+←/→` für Schritt-Navigation.

### 6.3 SprechzettelPanel

Ausfahrbares Drawer (320 px, rechts). Inhalt je Schritt: Kernbotschaft, typische Rückfragen mit Antworten, prüfmethodischer Bezug, Zeithinweis. Inhalte sind im Code hinterlegt (TypeScript-Objekt), nicht über UI editierbar.

### 6.4 LlmResponsePanel

Streaming-Ausgabe mit drei Anzeigemodi: normal (fließend einlaufend), JSON-formatiert (für Szenario 2), Split-View (für Szenario 3). Unsicherheits-Marker: Sätze die „nicht sicher", „unklar", „möglicherweise" enthalten werden gelb hinterlegt. Hinweiskasten am Ende jeder Antwort.

---

## 7. Docker-Compose (Single-Stack)

```yaml
# docker-compose.yml
services:
  backend:
    build: ./backend
    ports: ["8000:8000"]
    environment:
      - OLLAMA_URL=http://host.docker.internal:11434
      - MODEL_NAME=qwen3:14b
    extra_hosts:
      - "host.docker.internal:host-gateway"
    volumes:
      - ./backend/data:/app/data

  frontend:
    build: ./frontend
    ports: ["3000:3000"]
    depends_on: [backend]
```

Ollama läuft als Host-Dienst (nicht in Docker), da die GPU-Anbindung über den Host stabiler ist.

---

## 8. CLAUDE.md für das Projekt

```markdown
# FlowWorkshop — Claude Code CLI Kontext

## Zweck
Standalone Workshop-Demo für Prüfbehörden-Workshop "KI und LLMs".
Vier Szenarien mit lokalem Qwen3-14B via Ollama auf RTX 5070 Ti (eGPU).

## Stack
- Backend: FastAPI (Python 3.12), Port 8000
- Frontend: React + TypeScript + Tailwind, Port 3000
- LLM: Ollama auf Host, http://host.docker.internal:11434
- Modell: qwen3:14b (primär), qwen3:30b-a3b (alternativ)

## Wichtige Pfade
- Demo-Dokumente: backend/data/demo_documents/
- System-Prompts: backend/config.py → SYSTEM_PROMPTS
- Sprechzettel-Inhalte: frontend/src/data/sprechzettel.ts

## Was NICHT geändert werden soll
- System-Prompts ohne Absprache verändern
- Demo-Dokumente mit echten Förderdaten befüllen
- Datenschutzhinweis in der Pipeline-Ansicht entfernen

## Architektur-Entscheidungen
- Kein Auth — das ist eine lokale Demo-Anwendung
- Kein persistenter Speicher — alle Daten sind session-basiert
- Streaming via Server-Sent-Events (kein WebSocket)
```

---

## 9. Claude Code CLI — Analyse-Prompts

Die folgenden Prompts werden nacheinander in Claude Code CLI ausgeführt, jeweils im Verzeichnis des Quellprojekts. Sie analysieren flowinvoice und audit_designer und bereiten die Übernahme vor.

---

### Prompt A — flowinvoice analysieren

Diesen Prompt im Verzeichnis `~/flowinvoice` (oder dem konsolidierten Pfad) ausführen:

```
Analysiere das flowinvoice-Projekt und erstelle eine strukturierte
Übersicht der Elemente, die in das neue Projekt "flowworkshop"
übernommen werden sollen.

Untersuche dazu:

1. backend/services/pdf_parser.py (oder ähnlich benannt):
   - Welche Parsing-Stufen sind implementiert?
   - Welche Dependencies werden verwendet (pdfplumber, PyMuPDF, Tesseract)?
   - Gibt es eine Donut-Integration?
   - Kopiere die relevanten Funktionen nach /tmp/flowworkshop_import/pdf_parser.py
     und entferne alle flowinvoice-spezifischen Imports und Datenbankaufrufe.
     Der Extrakt soll nur die reine Text-Extraktionslogik enthalten.

2. backend/services/ollama_service.py (oder ähnlich):
   - Wie ist die Ollama-Anbindung aufgebaut?
   - Gibt es Streaming-Unterstützung via SSE?
   - Kopiere die Streaming-Logik nach /tmp/flowworkshop_import/ollama_service.py
     bereinigt um alle Celery/Redis-Abhängigkeiten.

3. frontend/src/components/ — suche nach:
   - Datei-Upload-Komponenten (Dropzone, FileUpload o.ä.)
   - Fortschrittsanzeigen für lange Operationen
   - Kopiere relevante Komponenten nach /tmp/flowworkshop_import/frontend/

4. docker-compose.yml:
   - Notiere die Backend-Port-Konfiguration und Ollama-Anbindung.

Erstelle am Ende /tmp/flowworkshop_import/flowinvoice_extrakt.md
mit einer Tabelle: Element | Quellpfad | Zielpfad in flowworkshop | Anpassungsbedarf.
Halte die Beschreibungen kurz — eine Zeile pro Punkt.
```

---

### Prompt B — audit_designer analysieren

Diesen Prompt im Verzeichnis `~/audit_designer` ausführen:

```
Analysiere das audit_designer-Projekt und extrahiere die Elemente,
die in das neue Projekt "flowworkshop" übernommen werden sollen.

Untersuche dazu:

1. backend/ — suche nach:
   - Ollama/LLM-Service (VP-AI-Bereich, vpai/, llm o.ä.)
   - Streaming-Implementierung (SSE oder WebSocket)
   - Checklisten-Datenmodell (Checkliste, ChecklistItem, Prüfpunkt)
   - Wissensdatenbank-Router (knowledge, wissensbasis o.ä.)
   Kopiere die Ollama-Service-Klasse nach /tmp/flowworkshop_import/ollama_vpai.py
   und das Checklisten-Schema nach /tmp/flowworkshop_import/checklist_schema.py

2. frontend/src/ — suche nach:
   - Checklisten-Anzeige-Komponente (ChecklistView, ChecklistTable o.ä.)
   - VP-AI-Komponenten (Streaming-Ausgabe, Chat-Interface)
   - Wissensdatenbank-Suche
   Kopiere relevante Komponenten nach /tmp/flowworkshop_import/frontend/audit/

3. Lese CLAUDE.md und vp_ai.md (falls vorhanden):
   - Notiere alle System-Prompts und LLM-Konfigurationen.
   - Notiere den Modellnamen und Ollama-URL.

4. docker-compose.yml:
   - Wie wird Ollama angebunden (host.docker.internal)?
   - Welcher Port wird verwendet?

Erstelle /tmp/flowworkshop_import/audit_designer_extrakt.md
mit derselben Tabellenstruktur wie Prompt A.
Identifiziere außerdem Konflikte zwischen den beiden Extrakten
(z. B. unterschiedliche Ollama-Service-Implementierungen)
und schlage eine Zusammenführungsstrategie vor.
```

---

### Prompt C — flowworkshop aufbauen

Diesen Prompt im leeren Verzeichnis `~/flowworkshop` ausführen,
nachdem Prompts A und B abgeschlossen sind:

```
Erstelle das neue Projekt "flowworkshop" auf Basis der analysierten
Extrakten in /tmp/flowworkshop_import/.

Lese zunächst:
- /tmp/flowworkshop_import/flowinvoice_extrakt.md
- /tmp/flowworkshop_import/audit_designer_extrakt.md
- /tmp/flowworkshop_import/pdf_parser.py
- /tmp/flowworkshop_import/ollama_service.py
- /tmp/flowworkshop_import/ollama_vpai.py
- /tmp/flowworkshop_import/checklist_schema.py
- Alle Dateien in /tmp/flowworkshop_import/frontend/

Erstelle dann die vollständige Projektstruktur:

BACKEND (FastAPI, Python 3.12):

backend/main.py:
  FastAPI-App mit CORS für localhost:3000.
  Router: workshop, documents, system.
  Startup: Prüfe Ollama-Verbindung, logge Modell-Status.

backend/config.py:
  OLLAMA_URL, MODEL_NAME, alle 5 SYSTEM_PROMPTS (Szenarien 1–4
  plus Szenario 3 ohne Kontext) als Konstanten.

backend/services/ollama_service.py:
  Zusammengeführte Version aus flowinvoice und audit_designer.
  Pflicht: async_stream(prompt, system_prompt, documents) → AsyncGenerator.
  Ausgabe als SSE: data: {"token": "...", "done": false}\n\n

backend/services/pdf_parser.py:
  Aus flowinvoice extrahiert, bereinigt.
  Funktion: extract_text(file_bytes, filename) → str.
  Stufen: direkte Extraktion → OCR-Fallback.

backend/routers/workshop.py:
  POST /api/workshop/stream — SSE-Streaming für alle Szenarien.
  Request-Body: scenario (1–4), prompt, documents, with_context, demo_doc.

backend/routers/documents.py:
  GET /api/documents/demo/{name} — gibt Demo-Dokument als Text zurück.
  POST /api/documents/upload — nimmt PDF/DOCX entgegen, gibt Text zurück.

backend/routers/system.py:
  GET /api/system/gpu — nvidia-smi via subprocess.
  GET /api/system/info — psutil CPU/RAM/Ollama-Worker.
  (Logik aus gpu_stats_server.py direkt übernehmen.)

backend/data/demo_documents/:
  Erstelle vier Python-Module mit anonymisierten Musterdokumenten
  als Strings. Realistische EFRE-Struktur, keine echten Daten.
  foerderbescheid.py: fiktiver Bescheid, 3 Abschnitte, 5 Auflagen.
  checkliste.py: 12 VKO-Prüfpunkte mit ID, Titel, Kategorie.
  feststellungen.py: 4 Prüffeststellungen als Stichpunkte.
  eu_verordnung.py: Artikel 74 VO (EU) 2021/1060 (offizieller Text).

FRONTEND (React + TypeScript + Tailwind):

Erstelle die Komponenten aus der Planung (PresenterToolbar,
SzenarioCard, DocumentDropzone, LlmResponsePanel, ChecklistTable,
HalluzinationsSwitch, SprechzettelPanel).

Erstelle die vier Szenario-Seiten.

frontend/src/data/sprechzettel.ts:
  TypeScript-Objekt mit Moderatornotizen je Szenario und Schritt.
  Struktur: {[szenario: number]: {[schritt: number]: {
    kernbotschaft: string, rueckfragen: {frage: string, antwort: string}[],
    rechtlicher_bezug: string, timing_hinweis: string}}}

DOCKER:
  docker-compose.yml nach Spezifikation aus dem Planungsdokument.
  Ollama läuft auf dem Host, nicht im Container.

CLAUDE.md:
  Aus dem Planungsdokument übernehmen.

Erstelle nach Abschluss eine Datei STATUS.md mit:
- Was ist implementiert.
- Was fehlt noch.
- Welche Abhängigkeiten müssen installiert werden.
- Startbefehl.

Arbeite ohne Zwischenfragen durch. Wenn etwas unklar ist,
treffe eine pragmatische Entscheidung und dokumentiere sie in STATUS.md.
```

---

### Prompt D — Demo-Dokumente finalisieren

Nach Prompt C, im Verzeichnis `~/flowworkshop`:

```
Prüfe die Demo-Dokumente in backend/data/demo_documents/ auf
Plausibilität für den Prüferworkshop.

Anforderungen:
- Förderbescheid: Soll Auflagen enthalten, die das Modell klar
  extrahieren kann (Nachweispflichten, Fristen, Berichtspflichten).
  Mindestens 800 Wörter. Keine echten Förderkennzeichen.
- Checkliste: 12 Prüfpunkte der VKO-Checkliste EFRE 2021–2027,
  angelehnt an reale Struktur. Kategorien: Vergabe, Förderfähigkeit,
  Publizität, Umwelt.
- Prüffeststellungen: 4 Feststellungen mit unterschiedlicher
  Schwere (ein Systemmangel, eine Unregelmäßigkeit, zwei Hinweise).
- EU-Verordnung: Artikel 74 Absatz 1 und 2 VO (EU) 2021/1060
  im offiziellen deutschen Wortlaut (öffentlich zugänglich, kein
  Urheberrecht da EU-Recht). Vollständig, nicht gekürzt.

Überarbeite die Dokumente entsprechend und teste danach:
  cd backend && python -c "from data.demo_documents import foerderbescheid; print(len(foerderbescheid.TEXT))"
Alle vier sollen mehr als 500 Zeichen ausgeben.
```

---

### Prompt E — Integrationstest

Nach Prompt D:

```
Führe einen vollständigen Integrationstest von flowworkshop durch.

1. Starte das Backend:
   cd backend && pip install -r requirements.txt --break-system-packages
   uvicorn main:app --reload --port 8000

2. Teste alle API-Endpunkte:
   curl http://localhost:8000/api/documents/demo/foerderbescheid
   curl http://localhost:8000/api/system/gpu
   curl http://localhost:8000/api/system/info

3. Teste den Streaming-Endpunkt mit einem einfachen Prompt:
   curl -X POST http://localhost:8000/api/workshop/stream \
     -H "Content-Type: application/json" \
     -d '{"scenario": 1, "prompt": "Fasse das Dokument kurz zusammen.",
          "documents": ["Dies ist ein Test-Förderbescheid."],
          "with_context": true}'
   Prüfe ob SSE-Tokens ankommen.

4. Falls Ollama nicht verbunden: Notiere den Fehler in STATUS.md,
   aber brich nicht ab — zeige stattdessen einen sinnvollen
   Fallback-Text im Frontend.

5. Starte das Frontend:
   cd frontend && npm install && npm run dev

6. Öffne http://localhost:3000 und prüfe ob WorkshopHome lädt.

Dokumentiere alle Fehler und Korrekturen in STATUS.md.
```

---

## 10. Implementierungsreihenfolge

Die Prompts A und B können parallel laufen (separate Claude Code CLI-Sitzungen in den jeweiligen Projektverzeichnissen). Prompt C setzt beide voraus. Prompt D und E sind sequenziell.

Realistischer Zeitaufwand mit Claude Code CLI im autonomen Modus: 6–8 Stunden für alle fünf Prompts inklusive manueller Nachkontrolle.

---

## 11. Datenschutz und Betriebshinweise

Im Workshop-Betrieb dürfen ausschließlich die eingebetteten Demo-Dokumente oder vorab anonymisierte Testdokumente hochgeladen werden. Die lokale Ollama-Instanz stellt sicher, dass keine Daten das Gerät verlassen — Artikel 28 DSGVO entfällt mangels Datenübermittlung an Dritte. Das Modell ist vor dem Workshop vollständig zu laden (Thunderbolt-4-Initialisierung der eGPU dauert ca. 2–3 Minuten).

Für die Präsentation empfiehlt sich ein externer Monitor mit mindestens 1920×1080 Auflösung. Der Sprechzettel läuft auf dem NUC-Display, die Workshop-Oberfläche auf dem Präsentationsmonitor — dazu `Alt+N` zur Steuerung des Drawers.

---

## 12. Optimierungsphase — flowworkshop als Testfeld

flowworkshop dient nicht nur als Workshop-Demo, sondern als kontrolliertes Optimierungsfeld. Jede Verbesserung wird hier zuerst entwickelt und getestet — ohne Risiko für die Produktivsysteme flowinvoice und audit_designer. Nach erfolgreichem Test erfolgt der gezielte Rücktransfer.

Die Optimierungsphase gliedert sich in vier Bereiche, die jeweils durch einen eigenen Claude Code CLI-Prompt abgedeckt werden, sowie zwei abschließende Back-Porting-Prompts.

---

### Prompt F — LLM-Prompts optimieren (Ausgabequalität)

Im Verzeichnis `~/flowworkshop`, nach dem ersten erfolgreichen Workshop-Durchlauf:

```
Optimiere die System-Prompts in backend/config.py auf Basis
konkreter Schwächen, die im Workshop sichtbar wurden.

Vorgehen:

1. Lese alle fünf System-Prompts aus backend/config.py.

2. Erstelle für jeden Prompt eine Testmatrix:
   Schreibe backend/tests/test_prompts.py mit mindestens drei
   Testfällen je Prompt. Jeder Testfall enthält:
   - Eingabe (Dokument-Snippet + Nutzerprompt)
   - Erwartetes Verhalten (als Kommentar, kein Assert)
   - Häufige Fehlerquelle (Halluzination, falsches Format, fehlende Fundstelle)
   Führe die Testdatei nicht aus — sie dient als Dokumentation.

3. Optimiere die Prompts nach diesen Prinzipien:
   - "Du bist ein Hilfswerkzeug" explizit am Anfang behalten
     (EU AI Act Transparenzpflicht Artikel 13 Absatz 1)
   - Keine positiven Fähigkeitsaussagen ("Ich kann..." → verboten)
   - Formatanweisung immer am Ende des Prompts (LLM folgt letzter
     Anweisung stärker)
   - Für Szenario 2 (JSON): Beispiel-JSON in den Prompt aufnehmen
     (Few-Shot verbessert Strukturtreue um ca. 30-40%)
   - Für Szenario 3 (Halluzination): Negativbeispiel aufnehmen
     ("Nenne KEINE Artikelnummern, die nicht im Dokument stehen")
   - Für Szenario 4 (Bericht): Stilmuster (ein Absatz Beispiel)
     direkt im Prompt als Referenz

4. Dokumentiere je Prompt:
   - Was war das konkrete Problem?
   - Welche Änderung wurde vorgenommen?
   - Warum ist das besser? (eine Satz)
   Schreibe das in backend/docs/prompt_changelog.md.

5. Erstelle backend/config_optimized.py als separate Datei —
   überschreibe config.py nicht. Die Entscheidung zur Übernahme
   trifft der Nutzer manuell.
```

---

### Prompt G — Backend-Services optimieren (Robustheit)

Im Verzeichnis `~/flowworkshop`:

```
Optimiere die Backend-Services auf Robustheit und
Fehlerbehandlung. Ziel ist produktionsreifer Code,
der direkt in flowinvoice und audit_designer übernommen
werden kann.

1. backend/services/ollama_service.py:

   Folgende Schwachstellen beheben:
   a) Timeout-Handling: Wenn Ollama nach 30 Sekunden keinen
      ersten Token geliefert hat, sende SSE-Event:
      data: {"error": "timeout", "message": "Ollama antwortet nicht"}
      Beende den Stream danach sauber.
   b) Reconnect-Logik: Bei ConnectionError maximal dreimal
      versuchen (1s, 3s, 5s Backoff), dann Fehler-Event senden.
   c) Modell-Fallback: Wenn qwen3:14b nicht verfügbar ist
      (404 von Ollama), versuche automatisch qwen3:8b,
      dann llama3.1:8b. Logge den Fallback als WARNING.
   d) Token-Zähler: Füge dem abschließenden done-Event hinzu:
      data: {"done": true, "token_count": N, "model": "..."}
      Das erlaubt Performance-Tracking im Frontend.

2. backend/services/pdf_parser.py:

   a) Dateigröße prüfen: Ablehnen wenn > 50 MB mit klarem
      Fehlermessage.
   b) Passwortschutz erkennen: PyMuPDF wirft PasswordError —
      abfangen und nutzerfreundliche Meldung zurückgeben.
   c) Leere Extraktion behandeln: Wenn Level 1 und 2 weniger
      als 50 Zeichen liefern, automatisch Level 3 aktivieren
      (OCR-Fallback), auch wenn das Dokument einen Text-Layer hat.
   d) Extraktions-Metadaten zurückgeben: Nicht nur den Text,
      sondern auch {"text": "...", "method": "level1|ocr",
      "pages": N, "char_count": N, "warnings": []}.
      Das erlaubt dem Frontend eine sinnvolle Fortschrittsanzeige.

3. backend/routers/workshop.py:

   a) Request-Validierung: scenario muss 1–4 sein, prompt
      darf nicht leer sein, documents darf max. 5 Einträge
      à max. 20.000 Zeichen haben. Bei Verletzung: 422 mit
      klarem Fehlertext.
   b) Streaming-Kontext-Zusammenbau: Dokumente werden vor
      dem LLM-Aufruf auf max. 8.000 Tokens gekürzt
      (Wort-basierte Schätzung: Zeichen / 4). Protokolliere
      die Kürzung im done-Event.

4. Schreibe für alle Änderungen einen kurzen Docstring
   mit: Was macht die Funktion, welche Ausnahmen werden
   behandelt, welche Rückgabetypen.

5. Erstelle backend/docs/service_changelog.md mit einer
   Tabelle der Änderungen: Service | Problem | Lösung | Testbar mit.
```

---

### Prompt H — Frontend-Komponenten optimieren (UX)

Im Verzeichnis `~/flowworkshop/frontend`:

```
Optimiere die Frontend-Komponenten auf Workshop-taugliche UX.
Der Fokus liegt auf Klarheit für das Publikum und
Bedienkomfort für den Moderator.

1. LlmResponsePanel:

   a) Tipp-Cursor: Während der Stream läuft, zeige einen
      blinkenden Cursor am Ende des Texts (CSS-Animation,
      kein JS-Overhead).
   b) Token-Counter: Zeige unten rechts live die Token-Anzahl.
      Quelle: done-Event aus Backend (token_count).
   c) Unsicherheits-Highlighting: Wörter und Phrasen, die auf
      Unsicherheit hinweisen, gelb unterstreichen.
      Pattern (case-insensitive): möglicherweise, unklar, könnte,
      unter Vorbehalt, nicht sicher, eventuell, scheint, vermutlich.
      Implementierung: Nach Stream-Ende Text per Regex scannen,
      keine Echtzeit-Markierung (zu aufwendig im Stream).
   d) Modell-Badge: Zeige Modellname und Latenz (Sekunden bis
      zum ersten Token) als Badge über dem Panel.

2. ChecklistTable (Szenario 2):

   a) Zeilenanimation: Wenn die KI-Einschätzung per JSON
      eintrifft, Zeilen nacheinander einblenden (50ms Versatz
      je Zeile) statt alle auf einmal.
   b) Override-Indikator: Wenn der Prüfer eine KI-Einschätzung
      überschreibt, Zelle mit leichtem Rahmen markieren
      (nicht aufdringlich — kleines Stift-Icon genügt).
   c) Zusammenfassung: Unterhalb der Tabelle Zähler:
      "Erfüllt: X · Nicht erfüllt: X · Nicht beurteilbar: X
       · Manuell überschrieben: X"

3. HalluzinationsSwitch (Szenario 3):

   a) Animierter Toggle: Beim Umschalten von "Ohne Kontext"
      auf "Mit Kontext" kurze Fade-Animation im Ausgabepanel.
   b) Warnbanner: Im "Ohne Kontext"-Modus roter Balken oben
      im Panel: "⚠ Kein Dokumentkontext — erhöhtes Halluzinationsrisiko"
   c) Split-View: Nach dem zweiten Durchlauf (beide Modi)
      automatisch Split-View einblenden (nebeneinander,
      scrollbar synchronisiert).

4. PresenterToolbar:

   a) Ollama-Latenz-Anzeige: Zeige Tokens/Sekunde neben dem
      Modellnamen (gleitender Durchschnitt, aktualisiert je Token).
   b) Schritt-Fortschritt: Fortschrittsbalken unter der Toolbar
      (nicht als Prozent, sondern als ausgefüllte Punkte:
      ● ● ○ ○).
   c) Notfall-Reset: Kleines "✕"-Icon ganz rechts in der Toolbar,
      das den aktuellen Stream abbricht und alle Felder leert,
      ohne die Seite zu verlassen.

5. Allgemein:

   Prüfe alle Komponenten auf:
   - Kein hartkodierter Text außerhalb von src/data/
   - Keine console.log()-Aufrufe im Produktionscode
   - Alle fetch()-Aufrufe haben AbortController für sauberen Abbruch

   Erstelle frontend/docs/component_changelog.md.
```

---

### Prompt I — Lessons Learned messen

Diesen Prompt nach dem ersten echten Workshop-Durchlauf ausführen, im Verzeichnis `~/flowworkshop`:

```
Erstelle eine strukturierte Lessons-Learned-Auswertung
für den Workshop-Betrieb.

1. Analysiere backend/logs/ (falls vorhanden) oder
   frage interaktiv: "Welche Fehler oder Auffälligkeiten
   gab es im Workshop? Beschreibe kurz." Warte auf Eingabe.

2. Prüfe die token_count-Werte aus den SSE-Events:
   - Wie lange hat jedes Szenario durchschnittlich gedauert?
   - Gab es Timeouts?
   - Welches Modell wurde tatsächlich verwendet (Fallback)?

3. Prüfe frontend/docs/component_changelog.md und
   backend/docs/service_changelog.md:
   - Welche Optimierungen haben sich im Live-Betrieb bewährt?
   - Was hat nicht funktioniert?

4. Erstelle docs/lessons_learned.md mit drei Abschnitten:
   a) Was hat gut funktioniert (mit technischem Grund)
   b) Was soll verbessert werden (priorisierte Liste)
   c) Welche Erkenntnisse sollen in flowinvoice /
      audit_designer zurückfließen (mit konkretem Verweis
      auf Datei und Funktion)
```

---

## 13. Back-Porting — Rücktransfer in die Produktivsysteme

Nach der Optimierungsphase in flowworkshop werden die bewährten Verbesserungen gezielt in flowinvoice und audit_designer übernommen. Die Back-Porting-Prompts sind bewusst konservativ formuliert: Sie überschreiben nichts automatisch, sondern erstellen Patch-Dateien zur manuellen Kontrolle.

---

### Prompt J — Rücktransfer in flowinvoice

Im Verzeichnis `~/flowinvoice`:

```
Übernimm optimierte Komponenten aus dem Workshop-Projekt
flowworkshop in flowinvoice. Arbeite ausschließlich mit
Patch-Dateien — verändere flowinvoice-Dateien nicht direkt.

1. Lese zunächst:
   ~/flowworkshop/backend/docs/service_changelog.md
   ~/flowworkshop/backend/docs/prompt_changelog.md
   ~/flowworkshop/docs/lessons_learned.md (falls vorhanden)

2. Für den Ollama-Service:
   Vergleiche ~/flowworkshop/backend/services/ollama_service.py
   mit dem entsprechenden Service in flowinvoice (Pfad ermitteln).
   Identifiziere Unterschiede:
   - Timeout-Handling vorhanden?
   - Reconnect-Logik vorhanden?
   - Modell-Fallback vorhanden?
   - Token-Count im done-Event?
   Erstelle /tmp/flowinvoice_patches/ollama_service.patch
   (git diff Format) mit nur den Unterschieden, die übernommen
   werden sollen. Kommentiere jeden Hunk mit "# GRUND: ..."

3. Für den PDF-Parser:
   Identifiziere analog Unterschiede zu
   ~/flowworkshop/backend/services/pdf_parser.py.
   Erstelle /tmp/flowinvoice_patches/pdf_parser.patch.
   Besondere Vorsicht: flowinvoice hat möglicherweise
   Donut-Integration, die flowworkshop nicht hat.
   Diese darf NICHT verloren gehen — überspringe Hunks,
   die Donut-Logik berühren.

4. Für Frontend-Komponenten:
   Prüfe ob DocumentDropzone in flowinvoice vorhanden ist.
   Falls ja: Vergleiche mit flowworkshop-Version.
   Erstelle /tmp/flowinvoice_patches/dropzone.patch
   nur für UX-Verbesserungen (Cursor, Fortschritt, AbortController).
   Keine strukturellen Änderungen.

5. Erstelle /tmp/flowinvoice_patches/ANLEITUNG.md:
   - Für jeden Patch: Was ist der Inhalt, warum soll er
     übernommen werden, welches Risiko besteht.
   - Reihenfolge der Anwendung.
   - Testbefehl nach jedem Patch.
   Format: Eine Zeile Risikobewertung (niedrig / mittel / hoch)
   pro Patch — damit der Nutzer entscheiden kann.
```

---

### Prompt K — Rücktransfer in audit_designer

Im Verzeichnis `~/audit_designer`:

```
Übernimm optimierte Komponenten aus flowworkshop in
audit_designer. Wie bei Prompt J: nur Patch-Dateien,
keine direkte Änderung.

1. Lese:
   ~/flowworkshop/backend/docs/service_changelog.md
   ~/flowworkshop/backend/config_optimized.py (LLM-Prompts)
   ~/flowworkshop/frontend/docs/component_changelog.md
   ~/flowworkshop/docs/lessons_learned.md

2. Für den VP-AI Ollama-Service:
   Vergleiche mit ~/flowworkshop/backend/services/ollama_service.py.
   Erstelle /tmp/audit_designer_patches/vpai_ollama.patch.
   Besondere Beachtung: audit_designer hat möglicherweise
   eigene Chunkingstrategie für Prüfdokumente.
   Diese darf nicht durch die flowworkshop-Version ersetzt werden.

3. Für die LLM System-Prompts:
   Lese backend/config_optimized.py aus flowworkshop.
   Identifiziere Optimierungsprinzipien, die auf
   audit_designer übertragbar sind:
   - Few-Shot-Beispiele für JSON-Ausgabe
   - Expliziter Halluzinationsschutz
   - Formatanweisungen am Prompt-Ende
   Erstelle /tmp/audit_designer_patches/system_prompts.md
   (kein Patch, sondern Empfehlungen mit Begründung je Prompt).
   Der Nutzer soll die System-Prompts manuell anpassen.

4. Für die Checklisten-Komponente:
   Vergleiche ChecklistTable aus flowworkshop mit der
   entsprechenden Komponente in audit_designer.
   Erstelle /tmp/audit_designer_patches/checklist_table.patch
   nur für:
   - Zeilenanimation
   - Override-Indikator
   - Zusammenfassungszeile
   Keine strukturellen Änderungen am Datenmodell.

5. Für die Wissensdatenbank-Suche (Szenario 3):
   Das ist die umgekehrte Richtung: Prüfe ob die
   Wissensdatenbank-Implementierung aus audit_designer
   robuster ist als die in flowworkshop verwendete.
   Falls ja: Erstelle
   /tmp/flowworkshop_patches/knowledge_from_audit_designer.patch
   als Rückpatch (Verbesserung zurück in flowworkshop).

6. Erstelle /tmp/audit_designer_patches/ANLEITUNG.md
   analog zu Prompt J — mit Risikobewertung je Patch.
```

---

## 14. Gesamtablauf Optimierungszyklus

```
flowworkshop aufbauen (Prompts A–E)
        ↓
Workshop durchführen
        ↓
Optimierungsphase (Prompts F–H parallel möglich)
        ↓
Lessons Learned erfassen (Prompt I)
        ↓
Patches erstellen (Prompts J + K parallel)
        ↓
Manuelle Kontrolle der Patch-Dateien durch Jan
        ↓
Patches in flowinvoice / audit_designer anwenden
        ↓
Tests in beiden Produktivsystemen
```

Der entscheidende Punkt: Kein Back-Porting-Prompt ändert flowinvoice oder audit_designer direkt. Alle Patches landen zuerst in `/tmp/` und werden manuell geprüft. Das Risiko eines versehentlichen Regressionsfehlers in einem Produktivsystem ist damit auf null reduziert.

---

## 15. Erweiterungen — Szenarien 5 und 6

Die folgenden zwei Szenarien erweitern den Workshop um einen Daten- und Recherche-Block. Sie setzen den Kernworkshop (Szenarien 1–4) voraus und sind als eigenständiger zweiter Workshop-Block konzipiert — etwa 45 Minuten zusätzlich.

---

### 15.1 RAG-Wissensdatenbank (Vorbereitung für Szenario 3 und darüber hinaus)

Die Wissensdatenbank ist bisher in Szenario 3 als Datenlieferant für den Halluzinationsvergleich eingebunden (Artikel 74 VO (EU) 2021/1060). Sie soll als eigenständige Komponente aufgebaut werden, die auch für Szenario 5 (Vorab-Upload) genutzt wird.

**Vorgesehene Dokumente in der Wissensdatenbank:**

Die Datenbank wird lokal und offline aufgebaut. Alle aufgenommenen Dokumente sind öffentlich zugänglich und unterliegen keinem Urheberrechtsschutz (EU-Sekundärrecht und Bundesrecht).

| Dokument | Rechtsgrundlage / Quelle | Relevanz |
|---|---|---|
| VO (EU) 2021/1060 (Dachverordnung) | EUR-Lex | Artikel 74, 79, 49 |
| VO (EU) 2021/1058 (EFRE-VO) | EUR-Lex | Förderfähigkeit |
| EFRE-Förderrichtlinie Hessen 21+ | wirtschaft.hessen.de | Länderspezifische Regeln |
| VV zu § 44 LHO Hessen | Hessisches Finanzministerium | Zuwendungsrecht |
| Vergaberecht (GWB, VgV, UVgO) | gesetze-im-internet.de | Szenario 2 |
| EU AI Act (VO (EU) 2024/1689) | EUR-Lex | Workshop-Kontext |

**Technische Umsetzung:**

Die Dokumente werden als PDF heruntergeladen, durch den PDF-Parser in Chunks aufgeteilt (700–1100 Tokens, 150 Token Overlap) und als Embeddings in einer PostgreSQL-Datenbank mit pgvector-Erweiterung gespeichert. Das Embedding-Modell ist `paraphrase-multilingual-mpnet-base-v2` (aus flowinvoice bekannt, läuft auf CPU). Die pgvector läuft im selben PostgreSQL-Container wie die übrigen Anwendungsdaten und wird beim Start des Backends nicht neu aufgebaut — sie wird einmalig befüllt und dann persistent genutzt.

**Backend-Endpunkte:**

```python
# GET /api/knowledge/search?q=...&top_k=5
# → Gibt die fünf relevantesten Chunks mit Quelle und Fundstelle zurück

# POST /api/knowledge/ingest
# → Nimmt PDF entgegen, parsed, chunked, speichert in pgvector
# → Nur für Szenario 5 (Vorab-Upload) relevant
```

---

### 15.2 Szenario 5 — Vorab-Upload: Eigenes Dokument der Prüfer

Teilnehmende Prüfbehörden schicken vorab einen anonymisierten Zuwendungsbescheid oder eine Prüfcheckliste. Diese werden im Backend in die Wissensdatenbank aufgenommen und sind dann im Workshop live abfragbar.

**Didaktischer Wert:** Das Modell antwortet auf Basis eines echten (aber anonymisierten) Behördendokuments. Das ist deutlich überzeugender als jede Demo-Datei.

**Logistik:**

Vorab wird eine Einladungs-E-Mail verschickt mit der Bitte, eine anonymisierte Kopie eines Zuwendungsbescheids (max. 10 Seiten, PDF) bis 48 Stunden vor dem Workshop zu senden. Die Dokumente werden auf dem NUC lokal verarbeitet — sie verlassen das Gerät nicht.

**Datenschutzrechtliche Einordnung:** Da keine personenbezogenen Daten verarbeitet werden (Anonymisierungspflicht liegt beim Einsender) und die Verarbeitung ausschließlich lokal erfolgt, entfällt eine Auftragsverarbeitungsvereinbarung nach Artikel 28 DSGVO. Dennoch empfiehlt sich ein kurzer Hinweis im Einladungsschreiben.

**Backend-Ablauf:**
1. Datei-Upload über `/api/knowledge/ingest` (manuell ausgelöst, nicht im Demo-Modus zugänglich).
2. PDF-Parser extrahiert Text (Multi-Level, aus flowinvoice).
3. Chunker teilt auf, Embeddings werden in pgvector gespeichert.
4. Im Workshop: Nutzerprompt → Retrieval aus pgvector → Kontext an LLM.

**Szenario-UI:**

Kein Upload-Button im Demo-Modus — die Dokumente sind vorab eingespeist. Die Prüfer sehen beim Start: „Ihre Dokumente sind in der Wissensdatenbank geladen: 3 Dokumente, 47 Chunks." Dann stellen sie Fragen in natürlicher Sprache.

**Musterfragen für den Sprechzettel:**
- „Welche Verwendungsnachweispflichten sind im Bescheid festgelegt?"
- „Gibt es Fristen, die in den nächsten drei Monaten ablaufen?"
- „Welche Auflagen betreffen das Vergabeverfahren?"

---

### 15.3 Szenario 6 — Begünstigtenverzeichnis: Download, Auswertung, Karte

Das öffentliche Transparenzlistenverzeichnis der hessischen EFRE-Begünstigten (wirtschaft.hessen.de, Stand 15.12.2025, XLSX, ca. 225 KB) wird live heruntergeladen, durch das LLM ausgewertet und auf einer interaktiven Karte dargestellt. Rechtsgrundlage für die Veröffentlichung ist Artikel 49 Absatz 4 VO (EU) 2021/1060.

**Datenstruktur der Transparenzliste (typische Felder):**

| Feld | Inhalt |
|---|---|
| Name des Begünstigten | Unternehmens- / Institutionsname |
| Bezeichnung des Vorhabens | Projekttitel |
| Zusammenfassung | Kurzbeschreibung |
| Standort | Gemeinde / Landkreis / PLZ |
| Gesamtbetrag förderfähige Ausgaben | EUR |
| Priorität / Spezifisches Ziel | PZ 1.1, PZ 1.2, PZ 2.1 etc. |

**Demo-Ablauf im Workshop:**

Schritt 1: Download. Backend lädt die XLSX-Datei live von wirtschaft.hessen.de herunter (alternativ: lokal gecacht, falls keine Internetverbindung). Ladeindikator zeigt Dateiname, Größe, Zeilenanzahl.

Schritt 2: LLM-Auswertung. Das Modell beantwortet Fragen zur Verteilung:
- „Wie viele Vorhaben entfallen auf PZ 1 vs. PZ 2?"
- „Welche fünf Begünstigten haben den höchsten Förderbetrag?"
- „Gibt es Häufungen in bestimmten Landkreisen?"

Das LLM bekommt eine komprimierte Zusammenfassung der Tabelle (Top-Statistiken als JSON), nicht die Rohdaten — die Tabelle ist zu groß für das Kontextfenster.

Schritt 3: Kartendarstellung. Die Standortfelder werden über eine Geocoding-API (Nominatim / OpenStreetMap, lokal gecacht) in Koordinaten aufgelöst. Die Karte wird als Leaflet.js-Komponente im Frontend gerendert: Kreise skalieren mit Förderbetrag, Farbe nach Priorität.

**Didaktischer Wert:** Zeigt Datenanalyse-Kompetenz der KI bei strukturierten Daten — und die Grenzen (das Modell sieht nicht alle Zeilen gleichzeitig, es braucht vorverarbeitete Statistiken). Außerdem wird deutlich, dass öffentliche EFRE-Daten für prüfrechtliche Recherchen nutzbar sind, etwa zum Abgleich mit eigenen Prüfstichproben.

**Sprechzettel-Hinweise:**
- „Das ist alles öffentlich — Artikel 49 Absatz 4 DachVO." 
- Rückfrage „Kann man damit Betrug erkennen?" → Nein direkt, aber Ausreißeranalyse und Clusterbildung können Hinweise liefern — das ist Prüfplanung, kein Automatismus.
- Verweis auf Kohesio (kohesio.ec.europa.eu) als europaweite Entsprechung.

---

## 16. Claude Code CLI — Prompts für Szenarien 5 und 6

---

### Prompt L — RAG-Wissensdatenbank aufbauen

Im Verzeichnis `~/flowworkshop`, nach Prompt C:

```
Baue die lokale RAG-Wissensdatenbank für flowworkshop auf.

1. Installiere Abhängigkeiten:
   pip install pgvector psycopg2-binary sentence-transformers --break-system-packages
   Prüfe nach der Installation:
   python -c "import pgvector; import sentence_transformers; print('ok')"

2. Erstelle backend/services/knowledge_service.py:

   Klasse KnowledgeService mit:
   - __init__: psycopg2-Verbindung zu PostgreSQL (DATABASE_URL aus config.py).
     CREATE EXTENSION IF NOT EXISTS vector;
     Tabelle anlegen falls nicht vorhanden:
     knowledge_chunks(id SERIAL PRIMARY KEY, source TEXT,
     filename TEXT, chunk_index INT, text TEXT, char_count INT,
     embedding vector(768), ingested_at TIMESTAMPTZ DEFAULT now(),
     UNIQUE(source, chunk_index))
     IVFFlat-Index anlegen (lists=50) für schnelle ANN-Suche.
     Embedding-Modell: paraphrase-multilingual-mpnet-base-v2 (Dim. 768)
   - ingest(file_bytes, filename, source_label):
     PDF-Text extrahieren (pdf_parser.py), Chunking (700 Tokens, 150 Overlap,
     wortbasiert), Embeddings erzeugen (Dimension 768),
     UPSERT in knowledge_chunks (ON CONFLICT (source, chunk_index) DO UPDATE)
     — idempotenter Ingest, Wiederholung ist sicher.
     Metadaten je Chunk: source, filename, chunk_index, char_count.
     Rückgabe: {"chunks_stored": N, "source": filename}
   - search(query, top_k=5):
     Semantische Suche, Rückgabe:
     [{"text": "...", "source": "...", "score": 0.87}, ...]
   - stats():
     SELECT COUNT(DISTINCT source), COUNT(*) FROM knowledge_chunks.

3. Erstelle backend/scripts/ingest_knowledge.py:
   Lädt folgende öffentlich zugänglichen PDFs herunter und
   speichert sie in backend/data/knowledge_raw/:
   - VO (EU) 2021/1060 DE von EUR-Lex
   - EU AI Act VO (EU) 2024/1689 DE von EUR-Lex
   Für jede Datei: ingest() aufrufen, Fortschritt loggen.
   Am Ende: stats() ausgeben.
   Aufruf: python backend/scripts/ingest_knowledge.py

4. Ergänze backend/routers/documents.py:
   GET /api/knowledge/search?q=...&top_k=5
     → KnowledgeService.search() aufrufen, Ergebnis zurückgeben.
   GET /api/knowledge/stats
     → KnowledgeService.stats() zurückgeben.
   POST /api/knowledge/ingest (nur wenn ENV=development)
     → Datei entgegennehmen, KnowledgeService.ingest() aufrufen.

5. Passe Szenario 3 in backend/routers/workshop.py an:
   Wenn with_context=True: Vor dem LLM-Aufruf
   KnowledgeService.search(prompt, top_k=3) aufrufen.
   Die drei Chunks als Kontext in den Prompt einbauen.
   Fundstelle (source + chunk_index) in den Kontext aufnehmen.

Erstelle STATUS_knowledge.md mit Ergebnis des Ingest-Laufs.
```

---

### Prompt M — Szenario 5: Vorab-Upload

Im Verzeichnis `~/flowworkshop`, nach Prompt L:

```
Implementiere Szenario 5 — Vorab-Upload eigener Dokumente
in die Wissensdatenbank.

1. backend/routers/knowledge.py (neue Datei):
   POST /api/knowledge/ingest-upload
     - Nur erreichbar wenn ENV-Variable WORKSHOP_ADMIN=true
     - Nimmt multipart/form-data entgegen (file + source_label)
     - Ruft KnowledgeService.ingest() auf
     - Rückgabe: {"chunks_stored": N, "source": source_label,
                  "total_chunks": M}
   Sicherung: max. Dateigröße 20 MB, nur PDF akzeptieren.

2. frontend/src/pages/Szenario5.tsx:
   Zwei Modi — Moderatormodus und Teilnehmermodus.

   Moderatormodus (nur lokal, nicht im Präsentationsmodus):
   - Dropzone für PDF-Upload mit source_label-Eingabe.
   - Upload-Button → POST /api/knowledge/ingest-upload.
   - Fortschrittsanzeige: "47 Chunks gespeichert."

   Teilnehmermodus (Präsentation):
   - Kein Upload-Button sichtbar.
   - Stats-Banner: "Wissensdatenbank: 3 Dokumente · 134 Chunks"
     (Daten aus GET /api/knowledge/stats).
   - Freitextfeld für Fragen.
   - Antwort via Streaming (Szenario-3-Mechanismus mit with_context=true).
   - Quellenangaben werden als klickbare Chips unter der Antwort angezeigt.

3. Sprechzettel-Daten in frontend/src/data/sprechzettel.ts ergänzen:
   Szenario 5, Schritt 1:
     kernbotschaft: "Die Daten haben das Gerät nie verlassen."
     rueckfragen: [
       { frage: "Wie lange hat das Einlesen gedauert?",
         antwort: "Ca. 10 Sekunden je Seite auf dem NUC." },
       { frage: "Kann das Modell Dokumente speichern?",
         antwort: "Nein — nur Chunks in der Vektordatenbank,
                   kein Originaltext." }
     ]
     rechtlicher_bezug: "Art. 28 DSGVO entfällt bei lokaler Verarbeitung."
     timing_hinweis: "15–25 Sekunden je Frage bei Qwen3-14B."
```

---

### Prompt N — Szenario 6: Begünstigtenverzeichnis + Karte

Im Verzeichnis `~/flowworkshop`, nach Prompt C:

```
Implementiere Szenario 6 — Begünstigtenverzeichnis Hessen
mit LLM-Auswertung und interaktiver Karte.

DOWNLOAD UND PARSING:

1. backend/services/beneficiary_service.py:

   Klasse BeneficiaryService mit:
   - fetch_or_load():
     Prüfe ob backend/data/beneficiary_cache.json existiert
     und nicht älter als 4 Monate (Aktualisierungsrhythmus lt. DachVO).
     Falls nicht: Lade XLSX von wirtschaft.hessen.de (URL muss
     konfigurierbar sein in config.py: BENEFICIARY_URL).
     Parse mit openpyxl oder pandas, normalisiere Spaltennamen,
     speichere als JSON-Cache.
     Rückgabe: Liste von Dicts (ein Dict je Vorhaben).
   - compute_stats(data):
     Berechne:
     - Anzahl Vorhaben gesamt
     - Gesamtbetrag förderfähige Ausgaben
     - Verteilung nach Priorität / Spezifischem Ziel
     - Top 10 Begünstigte nach Förderbetrag
     - Anzahl einzigartiger Standorte (Gemeinden)
     - Durchschnittliche Fördersumme
     Rückgabe als kompaktes JSON (max. 2000 Zeichen für LLM-Kontext).
   - geocode(data):
     Für jeden einzigartigen Standort: Geocoding via Nominatim
     (https://nominatim.openstreetmap.org/search?q=...&countrycodes=de).
     Rate-Limit beachten: max. 1 Request/Sekunde (Nominatim-AGB).
     Cache in backend/data/geocode_cache.json.
     Rückgabe: Dict {standort: {lat, lon}}.

2. backend/routers/beneficiary.py:
   GET /api/beneficiary/load
     → fetch_or_load() + compute_stats() + geocode()
     → Rückgabe: {"stats": {...}, "map_data": [{name, lat, lon,
                  betrag, prioritaet, vorhaben}, ...], "rows": N}
   POST /api/beneficiary/ask
     → Body: {"question": "..."}
     → Stats als Kontext in LLM-Prompt einbauen
     → Streaming-Antwort via SSE

FRONTEND:

3. frontend/src/pages/Szenario6.tsx:

   Layout: Dreispaltiger Aufbau.
   Spalte links (250px): Steuerung (Laden-Button, Ladeindikator,
   Stats-Zusammenfassung: Vorhaben, Gesamtsumme, Landkreise).
   Spalte Mitte (flex): Leaflet-Karte.
   Spalte rechts (320px): LLM-Chat.

   Karte (Leaflet.js, CDN):
   - Hessen-Ausschnitt als Startzoom.
   - Kreis-Marker je Vorhaben: Radius proportional zu Förderbetrag
     (logarithmisch skaliert), Farbe nach Priorität:
     PZ 1 = Blau (#0066cc), PZ 2 = Grün (#00933a), Rest = Grau.
   - Tooltip bei Hover: Begünstigter, Vorhaben, Betrag (formatiert).
   - Klick öffnet Popup mit vollständiger Zeile.

   LLM-Chat (rechte Spalte):
   - Freitextfeld + Senden.
   - POST /api/beneficiary/ask → SSE-Streaming.
   - Vorbelegte Musterfragen als Chips über dem Freitextfeld:
     "Verteilung PZ 1 vs. PZ 2"
     "Top 5 Fördersummen"
     "Häufigste Standorte"
     "Durchschnittliche Projektgröße"

4. Leaflet über CDN einbinden (kein npm-Paket nötig):
   In index.html:
   <link rel="stylesheet"
     href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
   <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

5. System-Prompt für Szenario 6 in config.py:
   SYSTEM_PROMPTS[6] = """
   Du bist ein Hilfswerkzeug für EFRE-Prüfer.
   Dir liegen statistische Kennzahlen des hessischen
   EFRE-Begünstigtenverzeichnisses vor (Transparenzliste
   gemäß Art. 49 Abs. 4 VO (EU) 2021/1060, Stand 15.12.2025).
   Beantworte Fragen ausschließlich auf Basis dieser Statistiken.
   Erfinde keine Begünstigten oder Beträge.
   Weise explizit darauf hin, wenn eine Frage nicht auf Basis
   der vorliegenden Aggregatdaten beantwortet werden kann.
   Formatanweisung: Antworte in kurzen deutschen Sätzen.
   Zahlen immer mit Tausendertrennzeichen formatieren.
   """

6. Erstelle backend/docs/szenario6_notes.md mit:
   - URL der Datenquelle
   - Rechtsgrundlage (Art. 49 Abs. 4 DachVO)
   - Aktualisierungsrhythmus (alle 4 Monate)
   - Hinweis: Nominatim-Nutzungsbedingungen beachten,
     kein kommerzieller Massengebrauch.
```

---

## 17. Überarbeitete Gesamtstruktur

```
Workshop Block 1 (Kernprogramm, 95–110 Min.)
├── Szenario 1 — Dokumentenanalyse (Förderbescheid)
├── Szenario 2 — Checklisten-Unterstützung (VKO)
├── Szenario 3 — Halluzinationsdemonstration (RAG)
└── Szenario 4 — Berichtsentwurf

Workshop Block 2 (Erweiterung, 45 Min.)
├── Szenario 5 — Vorab-Upload: Eigene Dokumente der Prüfer
│   └── Nutzt: RAG-Wissensdatenbank (Prompt L)
└── Szenario 6 — Begünstigtenverzeichnis: Daten + Karte
    └── Quelle: wirtschaft.hessen.de (Art. 49 Abs. 4 DachVO)

Implementierungsreihenfolge:
A+B (parallel) → C → D → E → L → M → N → F–H → I → J+K
```

---

## 18. Build, Test und Simulation — Claude Code CLI Gesamtprompt

Dieser Abschnitt enthält den vollständigen Claude Code CLI-Prompt, der nach dem Entpacken des Grundgerüsts in `~/flowworkshop` ausgeführt wird. Claude Code CLI baut das Projekt auf, testet alle Komponenten, behebt Fehler autonom und führt eine vollständige Simulation mit synthetischen Testdaten durch — inklusive Live-Streaming gegen Ollama, sofern verfügbar.

**Aufruf:** `claude` im Verzeichnis `~/flowworkshop` starten und den folgenden Block vollständig einfügen.

---

```
Deine Aufgabe ist es, das Projekt flowworkshop vollständig aufzubauen,
zu testen und einen Simulationslauf mit Testdaten durchzuführen.
Arbeite autonom durch alle Phasen ohne Zwischenfragen.
Dokumentiere jeden Schritt und jeden Fehler in STATUS.md.

═══════════════════════════════════════════════════════════
PHASE 1 — VORAUSSETZUNGEN PRÜFEN
═══════════════════════════════════════════════════════════

Lies zunächst CLAUDE.md und README.md vollständig.

Prüfe die Verzeichnisstruktur — folgende Dateien müssen vorhanden sein:
backend/main.py, backend/config.py, backend/services/knowledge_service.py,
backend/services/ollama_service.py, backend/services/pdf_parser.py,
backend/routers/workshop.py, backend/routers/knowledge.py,
backend/routers/system.py, backend/scripts/ingest_knowledge.py,
docker-compose.yml.
Falls Dateien fehlen: sofort melden und abbrechen.

Prüfe ob Docker läuft:
    docker info
Falls nicht verfügbar: in STATUS.md notieren, weiter mit lokalem
Python-Test ohne Docker.

Prüfe ob Ollama auf dem Host erreichbar ist:
    curl -s http://localhost:11434/api/tags | python3 -c
      "import sys,json; d=json.load(sys.stdin);
       print([m['name'] for m in d.get('models',[])])"
Notiere das Ergebnis in STATUS.md. Falls Ollama nicht läuft:
Streaming-Tests überspringen, alle anderen Tests normal durchführen.

═══════════════════════════════════════════════════════════
PHASE 2 — PYTHON-UMGEBUNG UND SYNTAX
═══════════════════════════════════════════════════════════

Wechsle ins backend/-Verzeichnis. Installiere alle Dependencies:
    pip install -r requirements.txt --break-system-packages

Führe für jede Python-Datei einen Syntax-Check durch:
    python3 -m py_compile config.py main.py \
      services/knowledge_service.py services/ollama_service.py \
      services/pdf_parser.py routers/workshop.py \
      routers/knowledge.py routers/system.py \
      scripts/ingest_knowledge.py
Jeden Syntax-Fehler sofort beheben und erneut prüfen bis alles sauber ist.

Prüfe alle Imports:
    python3 -c "
    import sys; sys.path.insert(0, '.')
    from config import SYSTEM_PROMPTS, DATABASE_URL, OLLAMA_URL
    from services.knowledge_service import init_db, ingest, search, stats
    from services.ollama_service import stream, check_ollama
    from services.pdf_parser import extract
    print('Alle Imports erfolgreich.')
    "

Prüfe die FastAPI-Routen mit gemockter Datenbankverbindung:
    python3 -c "
    import sys; sys.path.insert(0, '.')
    import unittest.mock as mock
    with mock.patch('services.knowledge_service.init_db'):
        from main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    r = client.get('/health')
    assert r.status_code == 200, f'Health fehlgeschlagen: {r.text}'
    print('FastAPI startet korrekt.')
    print('Routen:', [r.path for r in app.routes])
    "

═══════════════════════════════════════════════════════════
PHASE 3 — DATENBANK-TEST
═══════════════════════════════════════════════════════════

Wechsle ins Projektwurzelverzeichnis. Starte nur den DB-Container:
    docker compose up -d db

Warte bis Healthcheck grün ist (max. 30 Sekunden):
    for i in $(seq 1 10); do
      docker exec flowworkshop-db pg_isready -U workshop && break
      echo "Warte $i/10..." && sleep 3
    done

Teste pgvector-Extension direkt im Container:
    docker exec flowworkshop-db psql -U workshop -c
      "CREATE EXTENSION IF NOT EXISTS vector;
       SELECT extname, extversion FROM pg_extension WHERE extname='vector';"
Falls vector fehlt: Image in docker-compose.yml auf pgvector/pgvector:pg16
prüfen und korrigieren.

Teste init_db() vom Backend aus gegen den Container:
    cd backend
    DATABASE_URL="postgresql://workshop:workshop@localhost:5433/workshop" \
    python3 -c "
    from services.knowledge_service import init_db, stats
    init_db()
    print('init_db() erfolgreich. Stats:', stats())
    "

═══════════════════════════════════════════════════════════
PHASE 4 — PDF-PARSER TEST
═══════════════════════════════════════════════════════════

Erstelle eine minimale Test-PDF und teste den Parser:
    python3 -c "
    import sys; sys.path.insert(0, '.')
    pdf = (
        b'%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n'
        b'2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n'
        b'3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R'
        b'/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n'
        b'4 0 obj<</Length 52>>stream\n'
        b'BT /F1 12 Tf 72 720 Td (Zuwendungsbescheid Test) Tj ET\n'
        b'endstream endobj\n'
        b'5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n'
        b'xref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n'
        b'0000000058 00000 n \n0000000115 00000 n \n0000000274 00000 n \n'
        b'0000000377 00000 n \ntrailer<</Size 6/Root 1 0 R>>\n'
        b'startxref 449\n%%EOF'
    )
    from services.pdf_parser import extract
    r = extract(pdf, 'test.pdf')
    print(f'Methode: {r[\"method\"]}, Zeichen: {r[\"char_count\"]}, Seiten: {r[\"pages\"]}')
    print(f'Warnungen: {r[\"warnings\"]}')
    print('PDF-Parser: OK')
    "

═══════════════════════════════════════════════════════════
PHASE 5 — WISSENSDATENBANK: INGEST UND SUCHE
═══════════════════════════════════════════════════════════

Schreibe synthetische Testdokumente in pgvector und teste die Suche:
    DATABASE_URL="postgresql://workshop:workshop@localhost:5433/workshop" \
    python3 -c "
    import sys, os; sys.path.insert(0, '.')
    from services.knowledge_service import init_db, ingest, search, stats

    init_db()

    text_vo = '''Artikel 74 Verwaltungsprüfungen. Die Verwaltungsbehörde
    führt Verwaltungsprüfungen durch, die risikobasiert sein können.
    Diese umfassen administrative, finanzielle, technische und physische
    Aspekte. Die risikobasierte Methode muss die Stichprobengröße und
    die Auswahl der Vorhaben gewährleisten gemäß VO EU 2021 1060.
    Verwendungsnachweis ist fristgerecht einzureichen.
    Vergabeverfahren gemäß UVgO durchzuführen.
    ''' * 8

    text_bescheid = '''Zuwendungsbescheid EFRE-2024-001.
    Auflage 1: Vergabeverfahren gemäß UVgO, Nachweis Vergabevermerk.
    Auflage 2: Verwendungsnachweis bis 31.03.2026.
    Auflage 3: EU-Emblem gemäß Art. 47 VO EU 2021 1060.
    Auflage 4: Wesentliche Änderungen vorher anzeigen.
    ''' * 8

    r1 = ingest(text_vo, source='TEST_VO', filename='test_vo.txt')
    r2 = ingest(text_bescheid, source='TEST_BESCHEID', filename='test_bescheid.txt')
    print(f'Ingest VO: {r1}')
    print(f'Ingest Bescheid: {r2}')

    s = stats()
    print(f'Datenbank: {s[\"documents\"]} Dokumente, {s[\"chunks\"]} Chunks')
    assert s['chunks'] > 0, 'Fehler: Keine Chunks gespeichert!'

    for query in ['Verwaltungsprüfungen risikobasiert',
                  'Verwendungsnachweis Frist', 'Vergabeverfahren']:
        hits = search(query, top_k=2)
        assert hits, f'Keine Treffer für: {query}'
        print(f'Query \"{query}\": {hits[0][\"score\"]:.3f} | {hits[0][\"text\"][:50]}...')

    print('Ingest und Suche: OK')
    "

═══════════════════════════════════════════════════════════
PHASE 6 — API-ENDPUNKTE TESTEN
═══════════════════════════════════════════════════════════

Starte das Backend lokal (Hintergrund):
    DATABASE_URL="postgresql://workshop:workshop@localhost:5433/workshop" \
    OLLAMA_URL="http://localhost:11434" \
    WORKSHOP_ADMIN="true" \
    uvicorn main:app --host 0.0.0.0 --port 8000 &
    BACKEND_PID=$!
    sleep 5

Teste alle Endpunkte:
    curl -sf http://localhost:8000/health && echo "Health: OK"
    curl -sf http://localhost:8000/api/knowledge/stats && echo "Stats: OK"
    curl -sf "http://localhost:8000/api/knowledge/search?q=Vergabe&top_k=2" \
      && echo "Search: OK"
    curl -sf http://localhost:8000/api/system/info && echo "System: OK"
    curl -sf http://localhost:8000/api/system/gpu && echo "GPU: OK"
    curl -sf http://localhost:8000/api/system/ollama && echo "Ollama: OK"

Teste Ingest-Endpunkt über die API (erstelle Test-PDF wie in Phase 4,
speichere als /tmp/api_test.pdf):
    curl -sf -X POST http://localhost:8000/api/knowledge/ingest \
      -F "file=@/tmp/api_test.pdf" \
      -F "source=API_TEST" \
      && echo "Ingest-API: OK"

Teste Workshop-Streaming-Endpunkt (Erreichbarkeit, Ollama-Status egal):
    curl -s -X POST http://localhost:8000/api/workshop/stream \
      -H "Content-Type: application/json" \
      -d '{"scenario":1,"prompt":"Test","documents":["Testtext"],"with_context":false}' \
      | head -5
    echo "Workshop-Stream: Endpunkt erreichbar"

Backend stoppen: kill $BACKEND_PID

═══════════════════════════════════════════════════════════
PHASE 7 — LLM-SIMULATION (nur wenn Ollama verfügbar)
═══════════════════════════════════════════════════════════

Diese Phase nur ausführen wenn Ollama in Phase 1 als erreichbar
gemeldet wurde. Sonst überspringen und in STATUS.md vermerken.

Starte Backend neu:
    DATABASE_URL="postgresql://workshop:workshop@localhost:5433/workshop" \
    OLLAMA_URL="http://localhost:11434" WORKSHOP_ADMIN="true" \
    uvicorn main:app --host 0.0.0.0 --port 8000 &
    BACKEND_PID=$! && sleep 4

Simuliere Szenario 1 — Dokumentenanalyse (gibt Token-Stream aus):
    curl -s -X POST http://localhost:8000/api/workshop/stream \
      -H "Content-Type: application/json" \
      -d '{"scenario":1,
           "prompt":"Extrahiere alle Auflagen strukturiert.",
           "documents":["Bescheid EFRE-2024-001. Auflage 1: Vergabe gemäß UVgO, Nachweis Vergabevermerk. Auflage 2: Verwendungsnachweis bis 31.03.2026."],
           "with_context":false}' \
    | python3 -c "
    import sys, json
    for line in sys.stdin:
        if line.startswith('data: '):
            try:
                d = json.loads(line[6:])
                if 'token' in d: print(d['token'], end='', flush=True)
                if d.get('done'):
                    print(f'\n→ Szenario 1: {d.get(\"token_count\",0)} Tokens, '
                          f'{d.get(\"tok_per_s\",0)} tok/s, Modell: {d.get(\"model\")}')
            except: pass
    "

Simuliere Szenario 3 ohne Kontext — zeigt Halluzinationsrisiko:
    curl -s -X POST http://localhost:8000/api/workshop/stream \
      -H "Content-Type: application/json" \
      -d '{"scenario":3,
           "prompt":"Welche Anforderungen stellt Artikel 74 der Dachverordnung an risikobasierte Verwaltungskontrollen?",
           "documents":[],"with_context":false}' \
    | python3 -c "
    import sys, json
    for line in sys.stdin:
        if line.startswith('data: '):
            try:
                d = json.loads(line[6:])
                if 'token' in d: print(d['token'], end='', flush=True)
                if d.get('done'): print('\n→ Szenario 3 ohne Kontext: OK')
            except: pass
    "

Simuliere Szenario 3 mit RAG-Kontext — zeigt korrekte Fundstellen:
    curl -s -X POST http://localhost:8000/api/workshop/stream \
      -H "Content-Type: application/json" \
      -d '{"scenario":3,
           "prompt":"Welche Anforderungen stellt Artikel 74 der Dachverordnung an risikobasierte Verwaltungskontrollen?",
           "documents":[],"with_context":true}' \
    | python3 -c "
    import sys, json
    for line in sys.stdin:
        if line.startswith('data: '):
            try:
                d = json.loads(line[6:])
                if 'token' in d: print(d['token'], end='', flush=True)
                if d.get('done'): print('\n→ Szenario 3 mit RAG: OK')
            except: pass
    "

Backend stoppen: kill $BACKEND_PID

═══════════════════════════════════════════════════════════
PHASE 8 — DOCKER VOLLSTACK
═══════════════════════════════════════════════════════════

Wechsle ins Projektwurzelverzeichnis. Starte den vollständigen Stack:
    docker compose up -d db backend
    sleep 15
    docker compose ps
    docker compose logs backend --tail=30

Prüfe Erreichbarkeit im Container:
    curl -sf http://localhost:8000/health && echo "Container-Health: OK"
Falls Fehler: docker compose logs backend ausgeben, Fehler im
Dockerfile oder docker-compose.yml beheben, dann:
    docker compose up -d --build backend

Prüfe ob Wissensdatenbank im Container leer und bereit ist
(Ingest erfolgt erst im Live-Betrieb):
    curl -sf http://localhost:8000/api/knowledge/stats
    echo "Datenbank leer und bereit: OK"

Stack stoppen: docker compose down

═══════════════════════════════════════════════════════════
PHASE 9 — ABSCHLUSSBERICHT
═══════════════════════════════════════════════════════════

Behebe alle noch offenen Fehler aus den Phasen 1–8.
Führe jeden betroffenen Test nach der Korrektur erneut aus.

Schreibe STATUS.md:

    # FlowWorkshop — Testergebnis

    ## Ergebnistabelle
    | Phase | Test | Ergebnis |
    |---|---|---|
    | 2 | Syntax alle .py | ✓/✗ |
    | 2 | Imports | ✓/✗ |
    | 2 | FastAPI-Health (gemockt) | ✓/✗ |
    | 3 | PostgreSQL + pgvector | ✓/✗ |
    | 3 | init_db() | ✓/✗ |
    | 4 | PDF-Parser | ✓/✗ |
    | 5 | Ingest synthetisch | ✓/✗ |
    | 5 | Semantische Suche | ✓/✗ |
    | 6 | Alle API-Endpunkte | ✓/✗ |
    | 7 | LLM Szenario 1 | ✓/✗/übersprungen |
    | 7 | LLM Szenario 3 ohne Kontext | ✓/✗/übersprungen |
    | 7 | LLM Szenario 3 mit RAG | ✓/✗/übersprungen |
    | 8 | Docker Vollstack | ✓/✗ |

    ## Ollama beim Test
    [Modell, URL, verfügbar ja/nein]

    ## Behobene Fehler
    [Dateiname | Problem | Korrektur]

    ## Nächste Schritte: Verordnungen und eigene Dokumente einlesen

    docker compose up -d

    # Alle EU-Verordnungen laden (einmalig, ~5 Min.):
    docker exec flowworkshop-backend \
      python scripts/ingest_knowledge.py --all

    # Eigene Dokumente vorab einlesen (Szenario 5):
    curl -X POST http://localhost:8000/api/knowledge/ingest \
      -F "file=@/pfad/zum/bescheid.pdf" \
      -F "source=foerderbescheid_musterstadt_2025"

    # Wissensdatenbank prüfen:
    curl http://localhost:8000/api/knowledge/stats

Falls alle Tests bestanden: Melde abschließend
"Grundgerüst vollständig getestet — bereit für den Live-Betrieb."
```
