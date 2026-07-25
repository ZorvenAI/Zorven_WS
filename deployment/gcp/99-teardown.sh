#!/usr/bin/env bash
# Tear down all GCP resources created by the deployment scripts.
# Use this to avoid ongoing costs when the test environment is not needed.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/00-config.sh"

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  WARNING: This will delete ALL Zorven GCP resources!    ║"
echo "║  Project: ${GCP_PROJECT_ID}                             ║"
echo "║  Region:  ${GCP_REGION}                                 ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
read -rp "Type 'yes' to confirm teardown: " confirm
if [ "${confirm}" != "yes" ]; then
  log "Teardown cancelled."
  exit 0
fi

# ── Delete Cloud Run services ───────────────────────────────
log "Deleting Cloud Run services..."
for entry in "${ALL_SERVICES[@]}"; do
  IFS=':' read -r svc_name _image _port <<< "${entry}"
  gcloud run services delete "${svc_name}" \
    --region="${GCP_REGION}" --quiet 2>/dev/null && \
    log "  Deleted ${svc_name}" || \
    log "  ${svc_name} not found (skipping)"
done

# ── Delete Cloud Run migration job ──────────────────────────
log "Deleting migration job..."
gcloud run jobs delete zorven-migrations \
  --region="${GCP_REGION}" --quiet 2>/dev/null || true

# ── Delete Cloud Memorystore Redis ──────────────────────────
log "Deleting Redis instance (this may take a few minutes)..."
gcloud redis instances delete "${REDIS_INSTANCE}" \
  --region="${GCP_REGION}" --quiet 2>/dev/null || true

# ── Delete VPC Connector ────────────────────────────────────
log "Deleting VPC connector..."
gcloud compute networks vpc-access connectors delete "${CONNECTOR_NAME}" \
  --region="${GCP_REGION}" --quiet 2>/dev/null || true

# ── Delete Secret Manager secrets ───────────────────────────
log "Deleting secrets..."
SECRETS=$(gcloud secrets list --format='value(name)' 2>/dev/null || echo "")
for secret in ${SECRETS}; do
  gcloud secrets delete "${secret}" --quiet 2>/dev/null && \
    log "  Deleted secret: ${secret}" || true
done

# ── Delete Artifact Registry images ─────────────────────────
log "Deleting Artifact Registry repository..."
gcloud artifacts repositories delete "${AR_REPO}" \
  --location="${GCP_REGION}" --quiet 2>/dev/null || true

# ── Delete VPC (if no other resources depend on it) ─────────
log "Deleting VPC..."
gcloud compute networks delete "${VPC_NAME}" --quiet 2>/dev/null || \
  log "  VPC ${VPC_NAME} could not be deleted (may have dependent resources)"

# ── Clean up local env files ────────────────────────────────
log "Cleaning up local files..."
rm -f "${SCRIPT_DIR}/redis-connection.env"
rm -f "${SCRIPT_DIR}/service-urls.env"

log_ok "Teardown complete. All Zorven GCP resources deleted."
log "Note: The Neon PostgreSQL database was NOT deleted (managed externally)."
