Fuehre den Workshop Smoke-Test aus und pruefe den Systemstatus:

1. **Container-Status pruefen**:
```bash
docker compose -f auditworkshop/docker-compose.yml ps
```

2. **Smoke-Tests**:
```bash
BACKEND_BASE=http://localhost:8006 FRONTEND_BASE=http://localhost:3004 \
  bash auditworkshop/scripts/workshop_smoke.sh
```

3. **Ollama-Verbindung**:
```bash
curl -s http://localhost:8006/api/system/ollama | python3 -m json.tool
```

4. **Wissensdatenbank-Status**:
```bash
curl -s http://localhost:8006/api/knowledge/stats | python3 -m json.tool
```

Falls Container nicht laufen, weise darauf hin mit dem Startbefehl:
```bash
cd auditworkshop && docker compose up -d
```
