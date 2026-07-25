#!/usr/bin/env bash
# Create Cloud Memorystore Redis instance (27 databases).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/00-config.sh"

log "Creating Cloud Memorystore Redis instance ${REDIS_INSTANCE}..."
log "  Tier: ${REDIS_TIER}, Size: ${REDIS_SIZE_GB}GB, Version: ${REDIS_VERSION}"
log "  This may take 5-10 minutes..."

gcloud redis instances describe "${REDIS_INSTANCE}" \
  --region="${GCP_REGION}" >/dev/null 2>&1 || \
  gcloud redis instances create "${REDIS_INSTANCE}" \
    --size="${REDIS_SIZE_GB}" \
    --region="${GCP_REGION}" \
    --tier="${REDIS_TIER}" \
    --redis-version="${REDIS_VERSION}" \
    --network="${VPC_NAME}" \
    --redis-config="maxmemory-policy=allkeys-lru" \
    --quiet

# Capture Redis connection info
REDIS_HOST=$(gcloud redis instances describe "${REDIS_INSTANCE}" \
  --region="${GCP_REGION}" --format='value(host)')
REDIS_PORT=$(gcloud redis instances describe "${REDIS_INSTANCE}" \
  --region="${GCP_REGION}" --format='value(port)')

log "Redis host: ${REDIS_HOST}:${REDIS_PORT}"

# Write Redis connection info for other scripts
cat > "${SCRIPT_DIR}/redis-connection.env" <<EOF
REDIS_HOST=${REDIS_HOST}
REDIS_PORT=${REDIS_PORT}
EOF

log_ok "Redis setup complete. Connection info saved to redis-connection.env"
