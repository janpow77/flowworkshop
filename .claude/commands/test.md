Fuehre alle verfuegbaren Tests fuer das Auditworkshop-Projekt aus:

1. **Smoke-Tests** (Backend-Endpunkte):
```bash
BACKEND_BASE=http://localhost:8006 FRONTEND_BASE=http://localhost:3004 \
  bash auditworkshop/scripts/workshop_smoke.sh
```

2. **Frontend TypeScript-Check**:
```bash
cd auditworkshop/frontend && npx tsc -b
```

3. **Frontend Lint**:
```bash
cd auditworkshop/frontend && npm run lint
```

4. **Frontend Build** (prueft ob Produktions-Build funktioniert):
```bash
cd auditworkshop/frontend && npm run build
```

Fuehre alle Schritte nacheinander aus. Bei Fehlern: analysiere die Ursache und schlage einen Fix vor.
