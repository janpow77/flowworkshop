Lade Demo-Daten in die Auditworkshop-Anwendung:

1. **Pruefen ob Container laufen**:
```bash
docker compose -f auditworkshop/docker-compose.yml ps
```

2. **Demo-Daten laden** (25 VKO-Pruefpunkte, Beispiel-Projekt):
```bash
curl -s -X POST http://localhost:8006/api/demo/seed | python3 -m json.tool
```

3. **Wissensdatenbank einlesen** (falls leer):
```bash
STATS=$(curl -s http://localhost:8006/api/knowledge/stats)
echo "$STATS" | python3 -m json.tool
CHUNKS=$(echo "$STATS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total_chunks', 0))")
if [ "$CHUNKS" -eq 0 ]; then
  echo "Wissensdatenbank leer — starte Ingest..."
  docker exec auditworkshop-backend python scripts/ingest_knowledge.py --all
else
  echo "Wissensdatenbank hat $CHUNKS Chunks — kein Ingest noetig."
fi
```

4. **Ergebnis pruefen**:
```bash
curl -s http://localhost:8006/api/projects/ | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'{len(d)} Projekte geladen')"
```
