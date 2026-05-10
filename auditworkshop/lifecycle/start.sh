#!/usr/bin/env bash
# start.sh — Vor-Start-Verifikation und Container-Start. Idempotent.
#
# Reihenfolge:
#   1. Erreichbarkeit von shared Postgres prüfen.
#   2. Erreichbarkeit der LLM-Endpoints prüfen
#      (NUC direkt oder llm-router-Container, abhängig von .env).
#   3. SLSA-Build-Provenance des Image-Tags verifizieren (sobald
#      Workstream A das Verfikations-Werkzeug bereitstellt).
#   4. `docker compose up -d`.
#   5. Health-Endpoint pollen, bis grün oder Timeout.

set -euo pipefail

SLUG="auditworkshop"
STACK_DIR="/opt/${SLUG}"
ENV_FILE="/etc/${SLUG}/env"

log()  { printf '[start] %s\n' "$*"; }
fail() { printf '[start] FEHLER: %s\n' "$*" >&2; exit 1; }

[[ -f "${ENV_FILE}" ]] || fail "${ENV_FILE} fehlt — bootstrap.sh zuerst ausführen"

# Werte aus .env laden (nur die paar Variablen, die wir hier brauchen).
# shellcheck disable=SC1090
set -a; source <(grep -E '^(DATABASE_URL|OLLAMA_URL|EGPU_GATEWAY_URL|IMAGE_TAG)=' "${ENV_FILE}"); set +a

# ── Postgres-Erreichbarkeit ────────────────────────────────
log "Postgres erreichbar?"
if [[ -n "${DATABASE_URL:-}" ]]; then
  pg_host=$(printf '%s' "${DATABASE_URL}" | sed -E 's|.*@([^:/?]+).*|\1|')
  pg_port=$(printf '%s' "${DATABASE_URL}" | sed -E 's|.*@[^:/?]+:([0-9]+).*|\1|')
  pg_port=${pg_port:-5432}
  if ! timeout 5 bash -c "</dev/tcp/${pg_host}/${pg_port}" 2>/dev/null; then
    fail "Postgres unter ${pg_host}:${pg_port} nicht erreichbar"
  fi
else
  fail "DATABASE_URL nicht gesetzt"
fi

# ── LLM-Endpoint-Erreichbarkeit ───────────────────────────
log "LLM-Gateway erreichbar?"
if [[ -n "${EGPU_GATEWAY_URL:-}" ]]; then
  if ! curl --max-time 5 --silent --fail --output /dev/null \
       "${EGPU_GATEWAY_URL%/}/health" 2>/dev/null; then
    log "WARN: ${EGPU_GATEWAY_URL}/health antwortet nicht — Container startet trotzdem; Backend toleriert kurzzeitige Aussetzer"
  fi
fi

# ── SLSA-Verifikation (Stub) ──────────────────────────────
if command -v cosign >/dev/null 2>&1 && [[ -n "${IMAGE_TAG:-}" ]]; then
  log "SLSA-Provenance verifizieren — sobald Workstream A den Verifier bereitstellt"
  # cosign verify-attestation --type=slsaprovenance \
  #   ghcr.io/janpow77/auditworkshop-backend:${IMAGE_TAG} \
  #   --certificate-identity-regexp=...
fi

# ── Compose-Up ────────────────────────────────────────────
log "Stack starten"
cd "${STACK_DIR}"
docker compose up -d

# ── Health-Polling ────────────────────────────────────────
log "Auf Backend-Health warten"
for i in {1..30}; do
  if docker compose exec -T auditworkshop-backend \
       python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health',timeout=2)" \
       >/dev/null 2>&1; then
    log "Backend gesund nach ${i} Versuchen"
    exit 0
  fi
  sleep 2
done
fail "Backend wurde nicht innerhalb des Timeouts gesund"
