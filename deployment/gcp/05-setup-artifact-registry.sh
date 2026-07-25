#!/usr/bin/env bash
# Create Artifact Registry repository for Docker images.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/00-config.sh"

log "Creating Artifact Registry repository ${AR_REPO}..."

gcloud artifacts repositories describe "${AR_REPO}" \
  --location="${GCP_REGION}" >/dev/null 2>&1 || \
  gcloud artifacts repositories create "${AR_REPO}" \
    --repository-format=docker \
    --location="${GCP_REGION}" \
    --quiet

# Configure Docker to authenticate with Artifact Registry
log "Configuring Docker auth for Artifact Registry..."
gcloud auth configure-docker "${AR_HOST}" --quiet 2>/dev/null

log_ok "Artifact Registry setup complete. Repo: ${AR_PREFIX}"
