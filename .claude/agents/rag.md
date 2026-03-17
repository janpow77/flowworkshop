---
name: rag
description: "Automatisch aktiv bei RAG-, Embedding-, Chunking- oder Wissensdatenbank-Aufgaben. Triggert bei 'pgvector', 'embedding', 'chunk', 'ingest', 'knowledge', 'RAG', 'Wissensdatenbank', 'Verordnung' oder bei Aenderungen an knowledge_service.py, file_parser.py, pdf_parser.py."
tools:
  - Read
  - Write
  - Edit
  - Bash
  - Grep
  - Glob
---

# RAG Agent — pgvector Wissensdatenbank

## Fokus-Dateien
- `auditworkshop/backend/services/knowledge_service.py` — pgvector RAG-Pipeline
- `auditworkshop/backend/services/file_parser.py` — Multi-Format-Parser
- `auditworkshop/backend/services/pdf_parser.py` — PDF-Parsing (PyMuPDF + pdfplumber + OCR)
- `auditworkshop/backend/routers/knowledge.py` — Ingest + Suche API
- `auditworkshop/backend/scripts/ingest_knowledge.py` — Verordnungen einlesen
- `auditworkshop/backend/scripts/ingest_all.py` — Komplett-Ingest
- `auditworkshop/backend/config.py` — Embedding-Config (EMBEDDING_MODEL, CHUNK_WORDS, CHUNK_OVERLAP)

## Regeln
- Embedding-Modell: `paraphrase-multilingual-mpnet-base-v2` (768 Dimensionen, CPU)
- Chunking: 700 Woerter Zielgroesse, 150 Woerter Overlap (wortbasiert)
- knowledge_service.py nutzt raw psycopg2, NICHT SQLAlchemy
- pgvector IVFFlat-Index NICHT entfernen
- Unterstuetzte Formate: PDF, XLSX, XLS, XLSM, DOCX, DOCM, HTML, RTF, TXT
- PDF-Parsing: 3-Stufen-Fallback (PyMuPDF → pdfplumber → Tesseract OCR)

## Standard-Checks
```bash
# Wissensdatenbank-Status
curl -s http://localhost:8006/api/knowledge/stats | python3 -m json.tool

# Semantische Suche testen
curl -s "http://localhost:8006/api/knowledge/search?q=Verwendungsnachweis&top_k=3" | python3 -m json.tool

# Verordnungen einlesen (im Container)
docker exec auditworkshop-backend python scripts/ingest_knowledge.py --all
```
