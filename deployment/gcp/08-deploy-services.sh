#!/usr/bin/env bash
# Deploy all Cloud Run services (core + agents).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/00-config.sh"
require_database_url

# Load Redis connection
if [ -f "${SCRIPT_DIR}/redis-connection.env" ]; then
  source "${SCRIPT_DIR}/redis-connection.env"
else
  log_err "redis-connection.env not found. Run 03-setup-redis.sh first."
  exit 1
fi

REDIS_BASE="redis://${REDIS_HOST}:${REDIS_PORT}"

# REDIS DB INDEX LIMIT — do not reintroduce indices >= 16 here.
#
# The project's logical allocation runs 0..26 (see root CLAUDE.md), which works
# under docker-compose because redis is started with `--databases 27`.
# Memorystore for Redis does NOT expose `databases` as a tunable redisConfig,
# so the managed instance is fixed at 16 databases (0..15). Every service that
# was pointed at DB 16..26 failed with
#   "DB index is out of range"
# and — because the agent RedisManagers fail open — degraded to no caching
# silently rather than crashing. That went unnoticed from at least 2026-07-25.
#
# The 11 affected services (BPA, BAA, BPV, NTA, BSA, CAA, CGA, ADPUB, COA, ILA,
# POI) are therefore mapped onto DB 2, the existing shared, key-prefix-isolated
# pool. This is safe because each namespaces every key it writes with a
# distinct prefix: bpa:, baa:, bpv:, nta:, bsa:, caa:, cga:, adpub:, coa:,
# ila:, poi:/prompt:.

# ── Common flags ─────────────────────────────────────────────
COMMON_FLAGS=(
  --region="${GCP_REGION}"
  --service-account="${SA_EMAIL}"
  --vpc-connector="${CONNECTOR_NAME}"
  --allow-unauthenticated
  --quiet
)

# ── Helper: deploy a service ─────────────────────────────────
deploy_service() {
  local name=$1 image=$2 port=$3
  shift 3
  log "  Deploying ${name} (port ${port})..."
  gcloud run deploy "${name}" \
    --image="${AR_PREFIX}/${image}:latest" \
    --port="${port}" \
    "${COMMON_FLAGS[@]}" \
    "$@" 2>&1 | tail -1
}

# ═══════════════════════════════════════════════════════════════
# CORE SERVICES
# ═══════════════════════════════════════════════════════════════
log "Deploying core services..."

# Backend (Django/Gunicorn) — skip startup migrations, run Gunicorn directly
deploy_service zorven-backend zorven-backend 8001 \
  --memory=1Gi --cpu=1 \
  --max-instances="${CR_MAX_INSTANCES}" \
  --min-instances=0 \
  --timeout="${CR_TIMEOUT}" \
  --set-secrets="SECRET_KEY=SECRET_KEY:latest,GOOGLE_API_KEY=GOOGLE_API_KEY:latest,STRIPE_SECRET_KEY=STRIPE_SECRET_KEY:latest,STRIPE_WEBHOOK_SECRET=STRIPE_WEBHOOK_SECRET:latest,ORCHESTRATOR_SERVICE_TOKEN=ORCHESTRATOR_SERVICE_TOKEN:latest,ORCHESTRATOR_CALLBACK_TOKEN=ORCHESTRATOR_CALLBACK_TOKEN:latest,WORKER_TOKEN=WORKER_TOKEN:latest" \
  --set-env-vars="\
DATABASE_URL=${DATABASE_URL},\
REDIS_URL=${REDIS_BASE}/0,\
CELERY_BROKER_URL=${REDIS_BASE}/0,\
CELERY_RESULT_BACKEND=${REDIS_BASE}/0,\
DEBUG=False,\
KONG_ENABLED=false,\
ALLOWED_HOSTS=*,\
GUNICORN_WORKERS=2,\
GUNICORN_THREADS=2,\
GCS_AUTO_PROVISION=false,\
GS_BUCKET_NAME=zorven-raw-assets,\
GCP_PROJECT_ID=zorven-503517,\
GCP_BUCKET_NAME=zorven-raw-assets,\
RAW_GCP_BUCKET_NAME=zorven-raw-assets,\
CURATION_GCP_BUCKET_NAME=zorven-curated-assets,\
ORCHESTRATION_KAFKA_ENABLED=false,\
ONBOARDING_KAFKA_ENABLED=false,\
ANALYTICS_KAFKA_ENABLED=false,\
TITLING_KAFKA_ENABLED=false,\
VERTEX_AI_MOCK_MODE=true,\
RAG_DB_SYNC_ENABLED=false,\
ORCHESTRATOR_URL=PLACEHOLDER,\
BACKEND_URL=PLACEHOLDER,\
CALLBACK_BASE_URL=PLACEHOLDER" \
  --command="gunicorn" \
  --args="brand_automator.wsgi:application,--bind,0.0.0.0:8001,--workers,2,--threads,2,--worker-class,gthread,--timeout,120" &

# Backend WebSocket (Daphne)
deploy_service zorven-backend-ws zorven-backend 8002 \
  --memory=512Mi --cpu=1 \
  --max-instances="${CR_MAX_INSTANCES}" \
  --min-instances=0 \
  --session-affinity \
  --timeout="${CR_WS_TIMEOUT}" \
  --set-secrets="SECRET_KEY=SECRET_KEY:latest" \
  --set-env-vars="\
DATABASE_URL=${DATABASE_URL},\
REDIS_URL=${REDIS_BASE}/0,\
CHANNELS_REDIS_URL=${REDIS_BASE}/0,\
CELERY_BROKER_URL=${REDIS_BASE}/0,\
CELERY_RESULT_BACKEND=${REDIS_BASE}/0,\
DEBUG=False,\
KONG_ENABLED=false,\
ALLOWED_HOSTS=*" \
  --command="daphne" \
  --args="brand_automator.asgi:application,--port,8002,--bind,0.0.0.0" &

# Frontend (Next.js)
deploy_service zorven-frontend zorven-frontend 3000 \
  --memory=512Mi --cpu=1 \
  --max-instances="${CR_MAX_INSTANCES}" \
  --min-instances=0 \
  --set-env-vars="\
NODE_ENV=production,\
NEXT_PUBLIC_API_URL=PLACEHOLDER,\
NEXT_PUBLIC_BRAND_EQUITY_API_URL=PLACEHOLDER" &

# MLflow
deploy_service zorven-mlflow zorven-mlflow-server 5000 \
  --memory=512Mi --cpu=1 \
  --max-instances=1 \
  --min-instances=0 \
  --set-env-vars="\
MLFLOW_BACKEND_STORE_URI=${DATABASE_URL}" &

wait
log_ok "Core services deployed."

# ═══════════════════════════════════════════════════════════════
# CELERY (always-on)
# ═══════════════════════════════════════════════════════════════
log "Deploying Celery services (always-on)..."

# Celery Worker — wrap with health server
deploy_service zorven-celery-worker zorven-celery-worker 8080 \
  --memory=1Gi --cpu=1 \
  --max-instances=1 \
  --min-instances=1 \
  --no-cpu-throttling \
  --set-secrets="SECRET_KEY=SECRET_KEY:latest,GOOGLE_API_KEY=GOOGLE_API_KEY:latest,ORCHESTRATOR_SERVICE_TOKEN=ORCHESTRATOR_SERVICE_TOKEN:latest,ORCHESTRATOR_CALLBACK_TOKEN=ORCHESTRATOR_CALLBACK_TOKEN:latest" \
  --set-env-vars="\
DATABASE_URL=${DATABASE_URL},\
REDIS_URL=${REDIS_BASE}/0,\
CELERY_BROKER_URL=${REDIS_BASE}/0,\
CELERY_RESULT_BACKEND=${REDIS_BASE}/0,\
DEBUG=False,\
ORCHESTRATION_KAFKA_ENABLED=false,\
ONBOARDING_KAFKA_ENABLED=false,\
ANALYTICS_KAFKA_ENABLED=false,\
TITLING_KAFKA_ENABLED=false,\
VERTEX_AI_MOCK_MODE=true,\
RAG_DB_SYNC_ENABLED=false,\
GCS_AUTO_PROVISION=false,\
GS_BUCKET_NAME=zorven-raw-assets,\
GCP_PROJECT_ID=zorven-503517,\
GCP_BUCKET_NAME=zorven-raw-assets,\
RAW_GCP_BUCKET_NAME=zorven-raw-assets,\
CURATION_GCP_BUCKET_NAME=zorven-curated-assets,\
ORCHESTRATOR_URL=PLACEHOLDER,\
BACKEND_URL=PLACEHOLDER,\
CALLBACK_BASE_URL=PLACEHOLDER" \
  --command="bash" \
  --args="-c,python -m http.server \${PORT:-8080} & exec celery -A brand_automator worker --loglevel=info --concurrency=4 -Q celery,high_priority,low_priority,ingestion,curation,orchestration" &

# Celery Beat
deploy_service zorven-celery-beat zorven-celery-beat 8080 \
  --memory=256Mi --cpu=1 \
  --max-instances=1 \
  --min-instances=1 \
  --no-cpu-throttling \
  --set-secrets="SECRET_KEY=SECRET_KEY:latest" \
  --set-env-vars="\
DATABASE_URL=${DATABASE_URL},\
CELERY_BROKER_URL=${REDIS_BASE}/0,\
CELERY_RESULT_BACKEND=${REDIS_BASE}/0,\
DEBUG=False,\
ORCHESTRATION_KAFKA_ENABLED=false,\
RAG_DB_SYNC_ENABLED=false" \
  --command="bash" \
  --args="-c,python -m http.server \${PORT:-8080} & exec celery -A brand_automator beat --loglevel=info" &

wait
log_ok "Celery services deployed."

# ═══════════════════════════════════════════════════════════════
# AGENT MICROSERVICES (deploy in parallel batches of 8)
# ═══════════════════════════════════════════════════════════════
log "Deploying agent microservices..."

# Common agent env vars
AGENT_COMMON="\
ORCHESTRATION_KAFKA_ENABLED=false,\
KAFKA_BOOTSTRAP_SERVERS="

# ── Batch 1: Orchestrator + WF1 agents ──────────────────────
deploy_service zorven-orchestrator zorven-orchestrator 8010 \
  --memory=1Gi --cpu=1 \
  --max-instances="${CR_MAX_INSTANCES}" \
  --timeout="${CR_TIMEOUT}" \
  --set-secrets="GOOGLE_API_KEY=GOOGLE_API_KEY:latest,ORCHESTRATOR_SERVICE_TOKEN=ORCHESTRATOR_SERVICE_TOKEN:latest,ORCHESTRATOR_CALLBACK_TOKEN=ORCHESTRATOR_CALLBACK_TOKEN:latest,TAVILY_API_KEY=TAVILY_API_KEY:latest" \
  --set-env-vars="\
ORCHESTRATOR_REDIS_URL=${REDIS_BASE}/1,\
ORCHESTRATOR_PROMPT_CACHE_REDIS_URL=${REDIS_BASE}/2,\
ORCHESTRATOR_CALLBACK_BASE_URL=PLACEHOLDER,\
ORCHESTRATOR_MLFLOW_TRACKING_URI=PLACEHOLDER,\
ORCHESTRATOR_PROMPT_FALLBACK_ONLY=true,\
${AGENT_COMMON}" &

deploy_service zorven-discovery-agent zorven-discovery-agent 8020 \
  --memory="${CR_MEMORY}" --cpu="${CR_CPU}" \
  --max-instances="${CR_MAX_INSTANCES_AGENT}" \
  --set-secrets="DISCOVERY_GOOGLE_API_KEY=GOOGLE_API_KEY:latest,DISCOVERY_TAVILY_API_KEY=TAVILY_API_KEY:latest" \
  --set-env-vars="\
DISCOVERY_REDIS_URL=${REDIS_BASE}/2,\
DISCOVERY_PROMPT_CACHE_REDIS_URL=${REDIS_BASE}/2,\
DISCOVERY_MLFLOW_TRACKING_URI=PLACEHOLDER,\
DISCOVERY_PROMPT_FALLBACK_ONLY=true,\
${AGENT_COMMON}" &

deploy_service zorven-market-research-agent zorven-market-research-agent 8021 \
  --memory="${CR_MEMORY}" --cpu="${CR_CPU}" \
  --max-instances="${CR_MAX_INSTANCES_AGENT}" \
  --set-secrets="MRA_ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest,MRA_TAVILY_API_KEY=TAVILY_API_KEY:latest" \
  --set-env-vars="\
MRA_REDIS_URL=${REDIS_BASE}/11,\
MRA_PROMPT_CACHE_REDIS_URL=${REDIS_BASE}/2,\
MRA_MLFLOW_TRACKING_URI=PLACEHOLDER,\
MRA_PROMPT_FALLBACK_ONLY=true,\
${AGENT_COMMON}" &

deploy_service zorven-competitor-intel-agent zorven-competitor-intel-agent 8022 \
  --memory="${CR_MEMORY}" --cpu="${CR_CPU}" \
  --max-instances="${CR_MAX_INSTANCES_AGENT}" \
  --set-secrets="CIA_ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest,CIA_TAVILY_API_KEY=TAVILY_API_KEY:latest" \
  --set-env-vars="\
CIA_REDIS_URL=${REDIS_BASE}/12,\
CIA_PROMPT_CACHE_REDIS_URL=${REDIS_BASE}/2,\
CIA_MLFLOW_TRACKING_URI=PLACEHOLDER,\
CIA_PROMPT_FALLBACK_ONLY=true,\
${AGENT_COMMON}" &

deploy_service zorven-audience-persona-agent zorven-audience-persona-agent 8023 \
  --memory="${CR_MEMORY}" --cpu="${CR_CPU}" \
  --max-instances="${CR_MAX_INSTANCES_AGENT}" \
  --set-secrets="APA_ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest" \
  --set-env-vars="\
APA_REDIS_URL=${REDIS_BASE}/13,\
APA_PROMPT_CACHE_REDIS_URL=${REDIS_BASE}/2,\
APA_MLFLOW_TRACKING_URI=PLACEHOLDER,\
APA_PROMPT_FALLBACK_ONLY=true,\
${AGENT_COMMON}" &

deploy_service zorven-trend-cultural-agent zorven-trend-cultural-agent 8024 \
  --memory="${CR_MEMORY}" --cpu="${CR_CPU}" \
  --max-instances="${CR_MAX_INSTANCES_AGENT}" \
  --set-secrets="TCIA_ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest,TCIA_TAVILY_API_KEY=TAVILY_API_KEY:latest" \
  --set-env-vars="\
TCIA_REDIS_URL=${REDIS_BASE}/14,\
TCIA_PROMPT_CACHE_REDIS_URL=${REDIS_BASE}/2,\
TCIA_MLFLOW_TRACKING_URI=PLACEHOLDER,\
TCIA_PROMPT_FALLBACK_ONLY=true,\
${AGENT_COMMON}" &

deploy_service zorven-voc-agent zorven-voc-agent 8025 \
  --memory="${CR_MEMORY}" --cpu="${CR_CPU}" \
  --max-instances="${CR_MAX_INSTANCES_AGENT}" \
  --set-secrets="VOCA_ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest" \
  --set-env-vars="\
VOCA_REDIS_URL=${REDIS_BASE}/15,\
VOCA_PROMPT_CACHE_REDIS_URL=${REDIS_BASE}/2,\
VOCA_MLFLOW_TRACKING_URI=PLACEHOLDER,\
VOCA_PROMPT_FALLBACK_ONLY=true,\
${AGENT_COMMON}" &

deploy_service zorven-intelligence-agent zorven-intelligence-agent 8030 \
  --memory="${CR_MEMORY}" --cpu="${CR_CPU}" \
  --max-instances="${CR_MAX_INSTANCES_AGENT}" \
  --set-secrets="INTELLIGENCE_GEMINI_API_KEY=GOOGLE_API_KEY:latest" \
  --set-env-vars="\
INTELLIGENCE_REDIS_URL=${REDIS_BASE}/3,\
INTELLIGENCE_PROMPT_CACHE_REDIS_URL=${REDIS_BASE}/2,\
INTELLIGENCE_MLFLOW_TRACKING_URI=PLACEHOLDER,\
INTELLIGENCE_PROMPT_FALLBACK_ONLY=true,\
${AGENT_COMMON}" &

wait
log "  Batch 1 complete."

# ── Batch 2: WF2 agents ─────────────────────────────────────
deploy_service zorven-brand-positioning-agent zorven-brand-positioning-agent 8031 \
  --memory="${CR_MEMORY}" --cpu="${CR_CPU}" \
  --max-instances="${CR_MAX_INSTANCES_AGENT}" \
  --set-secrets="BPA_ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest" \
  --set-env-vars="\
BPA_REDIS_URL=${REDIS_BASE}/2,\
BPA_PROMPT_CACHE_REDIS_URL=${REDIS_BASE}/2,\
BPA_MLFLOW_TRACKING_URI=PLACEHOLDER,\
BPA_PROMPT_FALLBACK_ONLY=true,\
${AGENT_COMMON}" &

deploy_service zorven-brand-architecture-agent zorven-brand-architecture-agent 8032 \
  --memory="${CR_MEMORY}" --cpu="${CR_CPU}" \
  --max-instances="${CR_MAX_INSTANCES_AGENT}" \
  --set-secrets="BAA_ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest" \
  --set-env-vars="\
BAA_REDIS_URL=${REDIS_BASE}/2,\
BAA_PROMPT_CACHE_REDIS_URL=${REDIS_BASE}/2,\
BAA_MLFLOW_TRACKING_URI=PLACEHOLDER,\
BAA_PROMPT_FALLBACK_ONLY=true,\
${AGENT_COMMON}" &

deploy_service zorven-brand-personality-agent zorven-brand-personality-agent 8033 \
  --memory="${CR_MEMORY}" --cpu="${CR_CPU}" \
  --max-instances="${CR_MAX_INSTANCES_AGENT}" \
  --set-secrets="BPV_ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest" \
  --set-env-vars="\
BPV_REDIS_URL=${REDIS_BASE}/2,\
BPV_PROMPT_CACHE_REDIS_URL=${REDIS_BASE}/2,\
BPV_MLFLOW_TRACKING_URI=PLACEHOLDER,\
BPV_PROMPT_FALLBACK_ONLY=true,\
${AGENT_COMMON}" &

deploy_service zorven-brand-naming-agent zorven-brand-naming-agent 8034 \
  --memory="${CR_MEMORY}" --cpu="${CR_CPU}" \
  --max-instances="${CR_MAX_INSTANCES_AGENT}" \
  --set-secrets="NTA_ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest" \
  --set-env-vars="\
NTA_REDIS_URL=${REDIS_BASE}/2,\
NTA_PROMPT_CACHE_REDIS_URL=${REDIS_BASE}/2,\
NTA_MLFLOW_TRACKING_URI=PLACEHOLDER,\
NTA_PROMPT_FALLBACK_ONLY=true,\
${AGENT_COMMON}" &

deploy_service zorven-brand-story-agent zorven-brand-story-agent 8035 \
  --memory="${CR_MEMORY}" --cpu="${CR_CPU}" \
  --max-instances="${CR_MAX_INSTANCES_AGENT}" \
  --set-secrets="BSA_ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest" \
  --set-env-vars="\
BSA_REDIS_URL=${REDIS_BASE}/2,\
BSA_PROMPT_CACHE_REDIS_URL=${REDIS_BASE}/2,\
BSA_MLFLOW_TRACKING_URI=PLACEHOLDER,\
BSA_PROMPT_FALLBACK_ONLY=true,\
${AGENT_COMMON}" &

deploy_service zorven-chat-titling-worker zorven-chat-titling-worker 8040 \
  --memory="${CR_MEMORY}" --cpu="${CR_CPU}" \
  --max-instances="${CR_MAX_INSTANCES_AGENT}" \
  --set-secrets="TITLING_GOOGLE_API_KEY=GOOGLE_API_KEY:latest,TITLING_WORKER_TOKEN=WORKER_TOKEN:latest" \
  --set-env-vars="\
TITLING_REDIS_URL=${REDIS_BASE}/4,\
TITLING_PROMPT_CACHE_REDIS_URL=${REDIS_BASE}/2,\
TITLING_MLFLOW_TRACKING_URI=PLACEHOLDER,\
TITLING_PROMPT_FALLBACK_ONLY=true,\
TITLING_CORE_API_URL=PLACEHOLDER,\
TITLING_KAFKA_ENABLED=false,\
${AGENT_COMMON}" &

deploy_service zorven-content-agent zorven-content-agent 8050 \
  --memory="${CR_MEMORY}" --cpu="${CR_CPU}" \
  --max-instances="${CR_MAX_INSTANCES_AGENT}" \
  --set-secrets="CONTENT_GOOGLE_API_KEY=GOOGLE_API_KEY:latest,CONTENT_CORE_API_TOKEN=ORCHESTRATOR_SERVICE_TOKEN:latest" \
  --set-env-vars="\
CONTENT_REDIS_URL=${REDIS_BASE}/5,\
CONTENT_PROMPT_CACHE_REDIS_URL=${REDIS_BASE}/2,\
CONTENT_MLFLOW_TRACKING_URI=PLACEHOLDER,\
CONTENT_PROMPT_FALLBACK_ONLY=true,\
CONTENT_CORE_API_URL=PLACEHOLDER,\
${AGENT_COMMON}" &

deploy_service zorven-social-agent zorven-social-agent 8060 \
  --memory="${CR_MEMORY}" --cpu="${CR_CPU}" \
  --max-instances="${CR_MAX_INSTANCES_AGENT}" \
  --set-secrets="SOCIAL_GOOGLE_API_KEY=GOOGLE_API_KEY:latest,SOCIAL_CORE_API_TOKEN=ORCHESTRATOR_SERVICE_TOKEN:latest" \
  --set-env-vars="\
SOCIAL_REDIS_URL=${REDIS_BASE}/6,\
SOCIAL_PROMPT_CACHE_REDIS_URL=${REDIS_BASE}/2,\
SOCIAL_MLFLOW_TRACKING_URI=PLACEHOLDER,\
SOCIAL_PROMPT_FALLBACK_ONLY=true,\
SOCIAL_CORE_API_URL=PLACEHOLDER,\
${AGENT_COMMON}" &

wait
log "  Batch 2 complete."

# ── Batch 3: WF3 + remaining agents ─────────────────────────
deploy_service zorven-campaign-architecture-agent zorven-campaign-architecture-agent 8041 \
  --memory="${CR_MEMORY}" --cpu="${CR_CPU}" \
  --max-instances="${CR_MAX_INSTANCES_AGENT}" \
  --set-secrets="CAA_ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest" \
  --set-env-vars="\
CAA_REDIS_URL=${REDIS_BASE}/2,\
CAA_PROMPT_CACHE_REDIS_URL=${REDIS_BASE}/2,\
CAA_MLFLOW_TRACKING_URI=PLACEHOLDER,\
CAA_PROMPT_FALLBACK_ONLY=true,\
${AGENT_COMMON}" &

deploy_service zorven-creative-generation-agent zorven-creative-generation-agent 8042 \
  --memory="${CR_MEMORY}" --cpu="${CR_CPU}" \
  --max-instances="${CR_MAX_INSTANCES_AGENT}" \
  --set-secrets="CGA_ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest" \
  --set-env-vars="\
CGA_REDIS_URL=${REDIS_BASE}/2,\
CGA_PROMPT_CACHE_REDIS_URL=${REDIS_BASE}/2,\
CGA_MLFLOW_TRACKING_URI=PLACEHOLDER,\
CGA_PROMPT_FALLBACK_ONLY=true,\
${AGENT_COMMON}" &

deploy_service zorven-ad-publishing-agent zorven-ad-publishing-agent 8043 \
  --memory="${CR_MEMORY}" --cpu="${CR_CPU}" \
  --max-instances="${CR_MAX_INSTANCES_AGENT}" \
  --set-secrets="ADPUB_ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest" \
  --set-env-vars="\
ADPUB_REDIS_URL=${REDIS_BASE}/2,\
ADPUB_PROMPT_CACHE_REDIS_URL=${REDIS_BASE}/2,\
ADPUB_MLFLOW_TRACKING_URI=PLACEHOLDER,\
ADPUB_PROMPT_FALLBACK_ONLY=true,\
${AGENT_COMMON}" &

deploy_service zorven-campaign-optimization-agent zorven-campaign-optimization-agent 8044 \
  --memory="${CR_MEMORY}" --cpu="${CR_CPU}" \
  --max-instances="${CR_MAX_INSTANCES_AGENT}" \
  --set-secrets="COA_ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest" \
  --set-env-vars="\
COA_REDIS_URL=${REDIS_BASE}/2,\
COA_PROMPT_CACHE_REDIS_URL=${REDIS_BASE}/2,\
COA_MLFLOW_TRACKING_URI=PLACEHOLDER,\
COA_PROMPT_FALLBACK_ONLY=true,\
${AGENT_COMMON}" &

deploy_service zorven-intelligence-loop-agent zorven-intelligence-loop-agent 8045 \
  --memory="${CR_MEMORY}" --cpu="${CR_CPU}" \
  --max-instances="${CR_MAX_INSTANCES_AGENT}" \
  --set-secrets="ILA_ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest" \
  --set-env-vars="\
ILA_REDIS_URL=${REDIS_BASE}/2,\
ILA_PROMPT_CACHE_REDIS_URL=${REDIS_BASE}/2,\
ILA_MLFLOW_TRACKING_URI=PLACEHOLDER,\
ILA_PROMPT_FALLBACK_ONLY=true,\
${AGENT_COMMON}" &

# Onboarding Intelligence Agent (OIA).
#
# --timeout is the WebSocket one, not the default: LIVE mode holds a socket for
# a 45-minute meeting, and on Cloud Run a WebSocket is a single long-lived
# request capped by this value. Spike A-02 measured the 300s default severing a
# socket at 301.9s. --session-affinity is best-effort only; session state lives
# in Redis because sockets land on different instances.
#
# Redis is DB 2 with the oia:v1: key prefix (ERRATA-01), not DB 27 — Memorystore
# is fixed at 16 databases and DB 27 does not exist there.
deploy_service zorven-onboarding-intelligence-agent zorven-onboarding-intelligence-agent 8120 \
  --memory="${CR_MEMORY}" --cpu="${CR_CPU}" \
  --max-instances="${CR_MAX_INSTANCES_AGENT}" \
  --timeout="${CR_WS_TIMEOUT}" \
  --session-affinity \
  --set-secrets="OIA_GEMINI_KEY=GOOGLE_API_KEY:latest" \
  --set-env-vars="\
OIA_REDIS_URL=${REDIS_BASE}/2,\
OIA_REDIS_DB=2,\
OIA_POI_PROMPT_CACHE_DB=2,\
OIA_BACKEND_BASE_URL=PLACEHOLDER,\
OIA_GCS_BUCKET=zorven-raw-assets,\
${AGENT_COMMON}" &

deploy_service zorven-rag-uploader-agent zorven-rag-uploader-agent 8070 \
  --memory="${CR_MEMORY}" --cpu="${CR_CPU}" \
  --max-instances="${CR_MAX_INSTANCES_AGENT}" \
  --set-env-vars="\
RAG_UPLOADER_REDIS_URL=${REDIS_BASE}/7,\
RAG_UPLOADER_PROMPT_CACHE_REDIS_URL=${REDIS_BASE}/2,\
RAG_UPLOADER_MLFLOW_TRACKING_URI=PLACEHOLDER,\
RAG_UPLOADER_PROMPT_FALLBACK_ONLY=true,\
${AGENT_COMMON}" &

deploy_service zorven-brand-equity-calculator zorven-brand-equity-calculator 8090 \
  --memory="${CR_MEMORY}" --cpu="${CR_CPU}" \
  --max-instances="${CR_MAX_INSTANCES_AGENT}" \
  --set-secrets="BRAND_EQUITY_ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest" \
  --set-env-vars="\
BRAND_EQUITY_REDIS_URL=${REDIS_BASE}/8,\
${AGENT_COMMON}" &

deploy_service zorven-odoo-mcp-server zorven-odoo-mcp-server 8095 \
  --memory="${CR_MEMORY}" --cpu="${CR_CPU}" \
  --max-instances="${CR_MAX_INSTANCES_AGENT}" \
  --set-env-vars="\
ODOO_MCP_REDIS_URL=${REDIS_BASE}/9,\
${AGENT_COMMON}" &

deploy_service zorven-odoo-worker-agent zorven-odoo-worker-agent 8100 \
  --memory="${CR_MEMORY}" --cpu="${CR_CPU}" \
  --max-instances="${CR_MAX_INSTANCES_AGENT}" \
  --set-env-vars="\
ODOO_WORKER_REDIS_URL=${REDIS_BASE}/10,\
ODOO_WORKER_PROMPT_CACHE_REDIS_URL=${REDIS_BASE}/2,\
ODOO_WORKER_MLFLOW_TRACKING_URI=PLACEHOLDER,\
ODOO_WORKER_PROMPT_FALLBACK_ONLY=true,\
${AGENT_COMMON}" &

deploy_service zorven-prompt-optimization zorven-prompt-optimization 8110 \
  --memory="${CR_MEMORY}" --cpu="${CR_CPU}" \
  --max-instances="${CR_MAX_INSTANCES_AGENT}" \
  --set-secrets="POI_ANTHROPIC_API_KEY=POI_ANTHROPIC_API_KEY:latest" \
  --set-env-vars="\
POI_REDIS_URL=${REDIS_BASE}/2,\
POI_MLFLOW_TRACKING_URI=PLACEHOLDER,\
POI_DATABASE_URL=${DATABASE_URL},\
${AGENT_COMMON}" &

wait
log_ok "All agent microservices deployed."
