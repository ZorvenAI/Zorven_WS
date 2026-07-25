#!/usr/bin/env bash
# Enable required GCP APIs and configure IAM for Cloud Run deployment.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/00-config.sh"

log "Setting GCP project to ${GCP_PROJECT_ID}..."
gcloud config set project "${GCP_PROJECT_ID}"

log "Enabling required APIs..."
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  redis.googleapis.com \
  vpcaccess.googleapis.com \
  compute.googleapis.com \
  --quiet

log "Creating service account ${SA_NAME}..."
gcloud iam service-accounts describe "${SA_EMAIL}" >/dev/null 2>&1 || \
  gcloud iam service-accounts create "${SA_NAME}" \
    --display-name="Zorven Cloud Run Service Account"

log "Granting IAM roles..."
ROLES=(
  roles/run.invoker
  roles/secretmanager.secretAccessor
  roles/artifactregistry.reader
  roles/redis.editor
  roles/storage.objectAdmin
  roles/logging.logWriter
  roles/monitoring.metricWriter
)

for role in "${ROLES[@]}"; do
  gcloud projects add-iam-policy-binding "${GCP_PROJECT_ID}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="${role}" \
    --quiet >/dev/null 2>&1
done

log_ok "Project setup complete. APIs enabled, service account ready."
