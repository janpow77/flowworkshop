Pruefe die Code-Qualitaet des Auditworkshop-Projekts:

1. **Frontend ESLint**:
```bash
cd auditworkshop/frontend && npm run lint
```

2. **Frontend TypeScript**:
```bash
cd auditworkshop/frontend && npx tsc -b --noEmit
```

3. **Backend Ruff** (falls installiert):
```bash
cd auditworkshop/backend && python3 -m ruff check . 2>/dev/null || echo "Ruff nicht lokal installiert — im Container pruefen: docker exec auditworkshop-backend python -m ruff check ."
```

Fasse die Ergebnisse zusammen. Bei Fehlern: zeige die betroffenen Dateien und schlage Fixes vor.
