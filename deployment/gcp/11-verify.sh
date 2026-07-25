#!/usr/bin/env bash
# Verify all Cloud Run services are healthy.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/00-config.sh"

URLS_FILE="${SCRIPT_DIR}/service-urls.env"
if [ ! -f "${URLS_FILE}" ]; then
  log_err "service-urls.env not found. Run 09-collect-urls.sh first."
  exit 1
fi
source "${URLS_FILE}"

PASSED=0
FAILED=0
SKIPPED=0
TOTAL=${#ALL_SERVICES[@]}

log "Verifying ${TOTAL} services..."

# Health check endpoints per service type
get_health_path() {
  local svc_name=$1
  case "${svc_name}" in
    zorven-backend|zorven-backend-ws)
      echo "/health/"
      ;;
    zorven-frontend)
      echo "/"
      ;;
    zorven-mlflow)
      echo "/health"
      ;;
    zorven-celery-worker|zorven-celery-beat)
      echo "/"  # python -m http.server serves directory listing
      ;;
    *)
      echo "/health"  # FastAPI agents all have /health
      ;;
  esac
}

for entry in "${ALL_SERVICES[@]}"; do
  IFS=':' read -r svc_name _image _port <<< "${entry}"

  # Get URL from env var
  key=$(echo "${svc_name}" | tr '[:lower:]-' '[:upper:]_')_URL
  url="${!key:-}"

  if [ -z "${url}" ]; then
    log_err "  ${svc_name}: No URL found (skipping)"
    SKIPPED=$((SKIPPED + 1))
    continue
  fi

  health_path=$(get_health_path "${svc_name}")
  full_url="${url}${health_path}"

  # curl with 30s timeout (cold start may take time)
  http_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 "${full_url}" 2>/dev/null || echo "000")

  if [ "${http_code}" -ge 200 ] && [ "${http_code}" -lt 400 ]; then
    log_ok "  ${svc_name}: ${http_code} ← ${full_url}"
    PASSED=$((PASSED + 1))
  else
    log_err "  ${svc_name}: ${http_code} ← ${full_url}"
    FAILED=$((FAILED + 1))
  fi
done

echo ""
log "Results: ${PASSED} passed, ${FAILED} failed, ${SKIPPED} skipped (${TOTAL} total)"

if [ "${FAILED}" -gt 0 ]; then
  log_err "Some services failed health checks. Check logs with:"
  log_err "  gcloud run services logs read <service-name> --region=${GCP_REGION}"
  exit 1
else
  log_ok "All services healthy!"
fi
