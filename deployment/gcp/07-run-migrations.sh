#!/usr/bin/env bash
# Run Django migrations via a Cloud Run Job.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/00-config.sh"

# Load Redis connection
if [ -f "${SCRIPT_DIR}/redis-connection.env" ]; then
  source "${SCRIPT_DIR}/redis-connection.env"
else
  log_err "redis-connection.env not found. Run 03-setup-redis.sh first."
  exit 1
fi

REDIS_URL_0="redis://${REDIS_HOST}:${REDIS_PORT}/0"
IMAGE="${AR_PREFIX}/zorven-backend:latest"

log "Creating migration job..."

# Delete existing job if present (idempotent)
gcloud run jobs delete zorven-migrations \
  --region="${GCP_REGION}" --quiet 2>/dev/null || true

gcloud run jobs create zorven-migrations \
  --image="${IMAGE}" \
  --region="${GCP_REGION}" \
  --memory=1Gi \
  --cpu=1 \
  --max-retries=0 \
  --task-timeout=600 \
  --service-account="${SA_EMAIL}" \
  --vpc-connector="${CONNECTOR_NAME}" \
  --set-secrets="SECRET_KEY=SECRET_KEY:latest" \
  --set-env-vars="\
DATABASE_URL=${DATABASE_URL},\
REDIS_URL=${REDIS_URL_0},\
CELERY_BROKER_URL=${REDIS_URL_0},\
CELERY_RESULT_BACKEND=${REDIS_URL_0},\
DEBUG=False,\
ALLOWED_HOSTS=*,\
KONG_ENABLED=false,\
GCS_AUTO_PROVISION=false,\
ORCHESTRATION_KAFKA_ENABLED=false,\
ONBOARDING_KAFKA_ENABLED=false,\
ANALYTICS_KAFKA_ENABLED=false,\
TITLING_KAFKA_ENABLED=false,\
VERTEX_AI_MOCK_MODE=true,\
RAG_DB_SYNC_ENABLED=false" \
  --command="bash" \
  --args="-c,cd /app && python manage.py migrate_schemas --shared --noinput && python manage.py seed_manifests && (python manage.py seed_metrics || echo 'seed_metrics failed - non-critical') && echo 'Migrations complete'" \
  --quiet

log "Running migration job..."
gcloud run jobs execute zorven-migrations \
  --region="${GCP_REGION}" \
  --wait \
  --quiet

log_ok "Migrations complete."
