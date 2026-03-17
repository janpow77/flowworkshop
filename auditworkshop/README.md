# FlowWorkshop

KI-Workshop-Demo für EFRE-Prüfbehörden — sechs Szenarien,
lokale Inferenz, pgvector-Wissensdatenbank.

## Voraussetzungen

- Docker + Docker Compose
- Ollama läuft auf dem Host (`ollama serve`)
- Modell geladen: `ollama pull qwen3:14b`
- NVIDIA GPU mit aktuellen Treibern (für Ollama-GPU-Beschleunigung)

## Start

```bash
# 1. Stack starten
docker compose up -d

# 2. Verordnungen in die Wissensdatenbank einlesen (einmalig, ~5 Min.)
docker exec flowworkshop-backend python scripts/ingest_knowledge.py --all

# 3. Frontend öffnen
open http://localhost:3000

# 4. Backend-API (Swagger)
open http://localhost:8000/docs
```

## Eigene Dokumente einlesen (Szenario 5)

```bash
# Via API (WORKSHOP_ADMIN=true ist im docker-compose.yml gesetzt)
curl -X POST http://localhost:8000/api/knowledge/ingest \
  -F "file=@/pfad/zum/bescheid.pdf" \
  -F "source=foerderbescheid_musterstadt_2025"

# Oder das Skript direkt nutzen:
docker exec flowworkshop-backend \
  python scripts/ingest_knowledge.py \
  --file /app/data/mein_dokument.pdf \
  --source mein_bescheid
```

## Wissensdatenbank prüfen

```bash
# Inhalt anzeigen
curl http://localhost:8000/api/knowledge/stats

# Suche testen
curl "http://localhost:8000/api/knowledge/search?q=Verwendungsnachweis&top_k=3"

# Quelle entfernen
curl -X DELETE http://localhost:8000/api/knowledge/source/foerderbescheid_musterstadt_2025
```

## System-Status

```bash
# Ollama-Status
curl http://localhost:8000/api/system/ollama

# GPU-Metriken
curl http://localhost:8000/api/system/gpu

# System-Info (RAM, CPU, Worker)
curl http://localhost:8000/api/system/info
```

## Streaming-Endpunkt testen

```bash
curl -X POST http://localhost:8000/api/workshop/stream \
  -H "Content-Type: application/json" \
  -d '{
    "scenario": 1,
    "prompt": "Welche Auflagen enthält dieser Bescheid?",
    "documents": ["Bescheid-Text hier..."],
    "with_context": true
  }'
```

## Stoppen

```bash
docker compose down
# Mit Datenverlust (Wissensdatenbank löschen):
docker compose down -v
```
