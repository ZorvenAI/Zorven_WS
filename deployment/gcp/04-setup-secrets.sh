#!/usr/bin/env bash
# Create Secret Manager secrets from secrets.env file.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/00-config.sh"

SECRETS_FILE="${SCRIPT_DIR}/secrets.env"

if [ ! -f "${SECRETS_FILE}" ]; then
  log_err "secrets.env not found. Copy secrets.env.template and fill in values."
  log_err "  cp ${SCRIPT_DIR}/secrets.env.template ${SECRETS_FILE}"
  exit 1
fi

log "Creating secrets in Secret Manager..."

while IFS='=' read -r key value; do
  # Skip comments and empty lines
  [[ "$key" =~ ^#.*$ ]] && continue
  [[ -z "$key" ]] && continue
  # Strip surrounding quotes from value
  value="${value#\"}"
  value="${value%\"}"
  value="${value#\'}"
  value="${value%\'}"

  if [ -n "$value" ]; then
    if gcloud secrets describe "$key" --project="${GCP_PROJECT_ID}" >/dev/null 2>&1; then
      echo -n "$value" | gcloud secrets versions add "$key" --data-file=- --quiet 2>/dev/null
      log "  Updated: $key"
    else
      echo -n "$value" | gcloud secrets create "$key" \
        --data-file=- \
        --replication-policy=automatic \
        --project="${GCP_PROJECT_ID}" \
        --quiet 2>/dev/null
      log "  Created: $key"
    fi
  fi
done < "${SECRETS_FILE}"

log_ok "Secrets setup complete."
