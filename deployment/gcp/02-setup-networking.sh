#!/usr/bin/env bash
# Create VPC and Serverless VPC Access connector for Cloud Memorystore.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/00-config.sh"

log "Creating VPC network ${VPC_NAME}..."
gcloud compute networks describe "${VPC_NAME}" >/dev/null 2>&1 || \
  gcloud compute networks create "${VPC_NAME}" \
    --subnet-mode=auto \
    --quiet

log "Creating Serverless VPC Access connector ${CONNECTOR_NAME}..."
gcloud compute networks vpc-access connectors describe "${CONNECTOR_NAME}" \
  --region="${GCP_REGION}" >/dev/null 2>&1 || \
  gcloud compute networks vpc-access connectors create "${CONNECTOR_NAME}" \
    --region="${GCP_REGION}" \
    --network="${VPC_NAME}" \
    --range="${CONNECTOR_RANGE}" \
    --min-instances=2 \
    --max-instances=3 \
    --machine-type=e2-micro \
    --quiet

log_ok "Networking setup complete."
