# Auditworkshop — CLAUDE.md

## Zweck
Standalone Workshop-Demo: „KI und LLMs in der EFRE-Prüfbehörde".
Sechs Live-Szenarien mit lokalem Qwen3-14B via Ollama auf RTX 5070 Ti (eGPU).
Das Projekt dient gleichzeitig als Optimierungsfeld — bewährte Verbesserungen
werden per Patch in flowinvoice und audit_designer zurückgespielt.

## Stack
- Backend:  FastAPI (Python 3.12), Port 8000
- Frontend: React + TypeScript + Tailwind, Port 3000 (via nginx)
- Datenbank: PostgreSQL 16 + pgvector, Port 5434 extern
- LLM:      Ollama auf dem Host, http://host.docker.internal:11434
- Modell:   qwen3:14b (primär), Fallback: qwen3:8b → llama3.1:8b
- Embeddings: paraphrase-multilingual-mpnet-base-v2 (768 Dim., CPU)

## Wichtige Pfade
| Pfad | Inhalt |
|---|---|
| backend/config.py | ALLE System-Prompts und Einstellungen |
| backend/services/knowledge_service.py | pgvector RAG |
| backend/services/ollama_service.py | LLM-Streaming |
| backend/routers/workshop.py | Szenarien 1–6 |
| backend/routers/knowledge.py | Ingest + Suche |
| backend/scripts/ingest_knowledge.py | Verordnungen einlesen |
| backend/data/knowledge_raw/ | Heruntergeladene PDFs |

## Szenarien
1. Dokumentenanalyse — Auflagen aus Förderbescheid extrahieren
2. Checklisten-Unterstützung — VKO-Einschätzung als JSON
3. Halluzinationsdemonstration — mit/ohne RAG-Kontext
4. Berichtsentwurf — Feststellungen → Berichtpassage
5. Vorab-Upload — eigene Dokumente der Prüfer (pgvector)
6. Begünstigtenverzeichnis — XLSX + LLM + Leaflet-Karte

## Start
```bash
docker compose up -d
# Verordnungen einlesen (einmalig):
docker exec flowworkshop-backend python scripts/ingest_knowledge.py --all
```

## Was NICHT geändert werden soll
- System-Prompts in config.py ohne Absprache verändern
- Demo-Dokumente mit echten personenbezogenen Daten befüllen
- WORKSHOP_ADMIN auf false setzen während des Workshops
- Den pgvector IVFFlat-Index entfernen

## Architektur-Entscheidungen
- Kein Auth — lokale Demo-Anwendung, kein Internetzugang im Workshop
- Kein persistenter Session-State — alle Daten sind request-basiert
- Streaming via Server-Sent-Events (kein WebSocket)
- pgvector statt ChromaDB — ein Dienst weniger, SQL-auditierbar
- Ollama läuft auf dem Host (nicht in Docker) — GPU-Anbindung stabiler
- WORKSHOP_ADMIN steuert Ingest-Endpunkt — kein separates Auth-System

## Bekannte Constraints
- Thunderbolt 4 eGPU braucht ~2 Min. zum Initialisieren nach Kaltstart
- Qwen3-14B Q8 belegt ~15 GB VRAM der RTX 5070 Ti (16 GB)
- Nominatim-API: max. 1 Request/s (Szenario 6 Geocoding)

## Zusammenhang mit anderen Projekten
Aus flowinvoice übernommen: pdf_parser.py (Multi-Level), Ollama-Streaming-Muster
Aus audit_designer übernommen: Checklisten-Schema, pgvector-Nutzung, System-Prompt-Struktur
Optimierungen fließen per Patch zurück (Prompts J + K im Planungsdokument).
