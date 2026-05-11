#!/usr/bin/env bash
# start.sh — Vor-Start-Verifikation und Container-Start. Idempotent.
#
# Reihenfolge:
#   1. Postgres-Erreichbarkeit prüfen.
#   2. LLM-Endpoint-Erreichbarkeit prüfen (Soft-Check).
#   3. SLSA-Verify (delegiert an _common.sh, nur wenn IMAGE_TAG neu).
#   4. docker compose up -d.
#   5. Health-Polling 5 Min mit automatischem Rollback bei Timeout
#      (MIG-07).

set -euo pipefail

COMMON_SLUG="auditworkshop"
STACK_DIR="/opt/${COMMON_SLUG}"
ENV_FILE="/etc/${COMMON_SLUG}/env"

# shellcheck disable=SC1091
source "$(dirname "$0")/_common.sh"

GHCR_OWNER="${GHCR_OWNER:-janpow77}"

[[ -f "${ENV_FILE}" ]] || fail "${ENV_FILE} fehlt — bootstrap.sh zuerst ausführen"

# Werte aus .env laden
# shellcheck disable=SC1090
set -a; source <(grep -E '^(DATABASE_URL|OLLAMA_URL|EGPU_GATEWAY_URL|IMAGE_TAG)=' "${ENV_FILE}"); set +a

# ── 1. Postgres-Erreichbarkeit ────────────────────────────
require_env DATABASE_URL
log "Postgres erreichbar?"
pg_host=$(printf '%s' "${DATABASE_URL}" | sed -E 's|.*@([^:/?]+).*|\1|')
pg_port=$(printf '%s' "${DATABASE_URL}" | sed -E 's|.*@[^:/?]+:([0-9]+).*|\1|')
pg_port=${pg_port:-5432}
if ! timeout 5 bash -c "</dev/tcp/${pg_host}/${pg_port}" 2>/dev/null; then
  fail "Postgres unter ${pg_host}:${pg_port} nicht erreichbar"
fi

# ── 2. LLM-Gateway Soft-Check ─────────────────────────────
if [[ -n "${EGPU_GATEWAY_URL:-}" ]]; then
  log "LLM-Gateway probieren"
  curl --max-time 5 --silent --fail --output /dev/null \
       "${EGPU_GATEWAY_URL%/}/health" 2>/dev/null \
    || warn "${EGPU_GATEWAY_URL}/health antwortet nicht — Backend startet trotzdem"
fi

# ── 3. SLSA-Verify ────────────────────────────────────────
if [[ -n "${IMAGE_TAG:-}" ]]; then
  verify_slsa_or_die "ghcr.io/${GHCR_OWNER}/auditworkshop-backend:${IMAGE_TAG}"  "${GHCR_OWNER}"
  verify_slsa_or_die "ghcr.io/${GHCR_OWNER}/auditworkshop-frontend:${IMAGE_TAG}" "${GHCR_OWNER}"
fi

# ── 4. Compose-Up ─────────────────────────────────────────
log "Stack starten"
cd "${STACK_DIR}"
PREVIOUS_IMAGE_TAG="${PREVIOUS_IMAGE_TAG:-}"
docker compose up -d

# ── 5. Health-Polling mit Rollback ────────────────────────
rollback_to_previous() {
  if [[ -z "$PREVIOUS_IMAGE_TAG" ]]; then
    warn "Kein PREVIOUS_IMAGE_TAG verfügbar — Rollback übersprungen"
    return 1
  fi
  warn "Rollback auf ${PREVIOUS_IMAGE_TAG}"
  IMAGE_TAG="$PREVIOUS_IMAGE_TAG" docker compose up -d
}

# Probiere zunächst den Container-Endpunkt; wenn das Backend nicht
# antwortet, polle den Health-Endpoint extern (über das Frontend).
HEALTH_URL="${HEALTH_URL:-http://localhost:8000/health}"
log "Backend-Health-Endpoint: ${HEALTH_URL} (Timeout 5 Min, MIG-07)"

# Versuche aus dem Backend-Container heraus zu pollen — das geht ohne
# Caddy-Vorschaltung und ist netzwerk-unabhängig vom Host.
docker_health_probe() {
  docker compose exec -T auditworkshop-backend \
    python3 -c "import urllib.request,sys,json; \
                r=urllib.request.urlopen('http://localhost:8000/health',timeout=3); \
                d=json.load(r); sys.exit(0 if d.get('status')=='ready' else 2)" \
    >/dev/null 2>&1
}

deadline=$(( $(date +%s) + 300 ))
attempt=0
while [[ $(date +%s) -lt $deadline ]]; do
  attempt=$(( attempt + 1 ))
  if docker_health_probe; then
    log "Backend status=ready nach ${attempt} Versuchen"
    exit 0
  fi
  sleep 2
done

warn "Backend wurde nicht innerhalb 5 Minuten 'ready' — Rollback (MIG-07)"
rollback_to_previous
fail "Backend-Start fehlgeschlagen — siehe docker logs auditworkshop-backend"
