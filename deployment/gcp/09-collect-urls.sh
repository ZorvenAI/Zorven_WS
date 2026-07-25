#!/usr/bin/env bash
# Collect all Cloud Run service URLs after first-pass deployment.
# Writes service-urls.env for use by 10-redeploy-with-urls.sh.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/00-config.sh"

OUTPUT="${SCRIPT_DIR}/service-urls.env"
> "${OUTPUT}"

log "Collecting Cloud Run service URLs..."

for entry in "${ALL_SERVICES[@]}"; do
  IFS=':' read -r svc_name _image _port <<< "${entry}"

  url=$(gcloud run services describe "${svc_name}" \
    --region="${GCP_REGION}" \
    --format='value(status.url)' 2>/dev/null || echo "")

  if [ -z "${url}" ]; then
    log_err "  ${svc_name}: URL not found (service may not be deployed)"
    continue
  fi

  # Convert service name to env-friendly key: zorven-backend → ZORVEN_BACKEND_URL
  key=$(echo "${svc_name}" | tr '[:lower:]-' '[:upper:]_')_URL
  echo "${key}=${url}" >> "${OUTPUT}"
  log "  ${svc_name} → ${url}"
done

# Count collected URLs
TOTAL=$(wc -l < "${OUTPUT}" | tr -d ' ')
log_ok "Collected ${TOTAL} service URLs → ${OUTPUT}"
