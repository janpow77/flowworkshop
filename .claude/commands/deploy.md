Baue und deploye den Auditworkshop Docker-Stack:

1. **Aktuelle Container stoppen**:
```bash
docker compose -f auditworkshop/docker-compose.yml down
```

2. **Images neu bauen**:
```bash
docker compose -f auditworkshop/docker-compose.yml build --no-cache
```

3. **Stack starten**:
```bash
docker compose -f auditworkshop/docker-compose.yml up -d
```

4. **Warten auf Healthchecks** (max 60 Sekunden):
```bash
echo "Warte auf Backend-Healthcheck..."
for i in $(seq 1 12); do
  STATUS=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8006/health 2>/dev/null)
  if [ "$STATUS" = "200" ]; then
    echo "Backend healthy nach $((i*5))s"
    break
  fi
  sleep 5
done
```

5. **Smoke-Test**:
```bash
BACKEND_BASE=http://localhost:8006 FRONTEND_BASE=http://localhost:3004 \
  bash auditworkshop/scripts/workshop_smoke.sh
```

**WICHTIG**: `docker compose down -v` loescht die Wissensdatenbank! Nur `down` ohne `-v` verwenden.
