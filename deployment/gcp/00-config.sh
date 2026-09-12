#!/usr/bin/env bash
# Shared configuration for Zorven GCP Cloud Run deployment.
# Source this file from all other scripts.

set -euo pipefail

# ── GCP Project ──────────────────────────────────────────────
export GCP_PROJECT_ID="${GCP_PROJECT_ID:-zorven-503517}"
export GCP_REGION="${GCP_REGION:-us-central1}"

# ── Artifact Registry ───────────────────────────────────────
export AR_REPO="zorven"
export AR_HOST="${GCP_REGION}-docker.pkg.dev"
export AR_PREFIX="${AR_HOST}/${GCP_PROJECT_ID}/${AR_REPO}"

# ── GHCR Source ──────────────────────────────────────────────
export GHCR_PREFIX="ghcr.io/zorvenai"

# ── Networking ───────────────────────────────────────────────
export VPC_NAME="zorven-vpc"
export CONNECTOR_NAME="zorven-connector"
export CONNECTOR_RANGE="10.8.0.0/28"

# ── Redis (Cloud Memorystore) ────────────────────────────────
export REDIS_INSTANCE="zorven-redis"
export REDIS_TIER="basic"
export REDIS_SIZE_GB="1"
export REDIS_VERSION="redis_7_0"

# ── Service Account ─────────────────────────────────────────
export SA_NAME="zorven-cloudrun"
export SA_EMAIL="${SA_NAME}@${GCP_PROJECT_ID}.iam.gserviceaccount.com"

# ── Cloud Run Defaults ───────────────────────────────────────
export CR_MEMORY="512Mi"
export CR_CPU="1"
export CR_TIMEOUT="300"

# Request timeout for services that hold WebSockets open.
#
# On Cloud Run a WebSocket is a single long-lived request, so the service's
# request timeout caps the connection outright — it is not an idle timeout.
# At the CR_TIMEOUT default of 300s a socket is severed after five minutes
# with no close frame, which spike A-02 measured at 301.9s
# (docs/spikes/A-02-gateway-websocket-note.md). 3600s is the platform maximum.
export CR_WS_TIMEOUT="3600"

# Max instances for user-facing services (backend, frontend, orchestrator).
# These absorb interactive traffic and keep burst headroom.
export CR_MAX_INSTANCES="2"

# Max instances for agent microservices.
#
# QUOTA: us-central1 allows 20 vCPU total (CpuAllocPerProjectRegion =
# 20000 milli vCPU). At cpu=1 each, the ~29 CR_MAX_INSTANCES services could
# request 58 vCPU on their own, which blew the ceiling and failed 4 services
# mid-rollout. Agents are invoked per-pipeline-node and rarely need to scale
# out, so they are pinned to 1 instance to cut rollout pressure roughly in
# half (61 -> 36 vCPU potential).
#
# NOTE: 32 services x 1 instance = 32 vCPU still exceeds the 20 vCPU quota.
# This reduces pressure but does NOT by itself make the ceiling safe — the
# quota increase is still required.
export CR_MAX_INSTANCES_AGENT="1"

# ── Database ─────────────────────────────────────────────────
# SECURITY: DATABASE_URL carries credentials and MUST NOT be hardcoded here.
# This file is tracked in git; secrets.env is not.
#
# Resolved at runtime, in order:
#   1. DATABASE_URL already exported in the environment (CI / one-off runs)
#   2. DATABASE_URL=... in deployment/gcp/secrets.env (gitignored)
#
# Scripts that actually need the database call require_database_url below,
# so infra-only scripts (01, 02, 05, 09) still run without secrets.env.
CONFIG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CONFIG_DIR

if [ -z "${DATABASE_URL:-}" ] && [ -f "${CONFIG_DIR}/secrets.env" ]; then
  DATABASE_URL="$(sed -n 's/^DATABASE_URL=//p' "${CONFIG_DIR}/secrets.env" | head -n1)"
  # Strip optional surrounding quotes
  DATABASE_URL="${DATABASE_URL#\"}"; DATABASE_URL="${DATABASE_URL%\"}"
  DATABASE_URL="${DATABASE_URL#\'}"; DATABASE_URL="${DATABASE_URL%\'}"
fi
export DATABASE_URL="${DATABASE_URL:-}"

# Call at the top of any script that deploys or migrates against the database.
require_database_url() {
  if [ -z "${DATABASE_URL:-}" ]; then
    echo "ERROR: DATABASE_URL is not set." >&2
    echo "  Add it to ${CONFIG_DIR}/secrets.env (see secrets.env.template):" >&2
    echo "    DATABASE_URL=postgresql://USER:PASSWORD@HOST/DB?sslmode=require&channel_binding=require" >&2
    echo "  or export it before running this script." >&2
    exit 1
  fi
}

# ── Unique GHCR images (30) ─────────────────────────────────
UNIQUE_IMAGES=(
  zorven-backend
  zorven-frontend
  zorven-celery-worker
  zorven-celery-beat
  zorven-mlflow-server
  zorven-orchestrator
  zorven-discovery-agent
  zorven-market-research-agent
  zorven-competitor-intel-agent
  zorven-audience-persona-agent
  zorven-trend-cultural-agent
  zorven-voc-agent
  zorven-intelligence-agent
  zorven-brand-positioning-agent
  zorven-brand-architecture-agent
  zorven-brand-personality-agent
  zorven-brand-naming-agent
  zorven-brand-story-agent
  zorven-campaign-architecture-agent
  zorven-creative-generation-agent
  zorven-ad-publishing-agent
  zorven-campaign-optimization-agent
  zorven-intelligence-loop-agent
  zorven-chat-titling-worker
  zorven-content-agent
  zorven-social-agent
  zorven-rag-uploader-agent
  zorven-brand-equity-calculator
  zorven-odoo-mcp-server
  zorven-odoo-worker-agent
  zorven-prompt-optimization
)

# ── All Cloud Run services ───────────────────────────────────
# Format: SERVICE_NAME:IMAGE_NAME:PORT
ALL_SERVICES=(
  # Core
  "zorven-backend:zorven-backend:8001"
  "zorven-backend-ws:zorven-backend:8002"
  "zorven-frontend:zorven-frontend:3000"
  "zorven-celery-worker:zorven-celery-worker:8080"
  "zorven-celery-beat:zorven-celery-beat:8080"
  "zorven-mlflow:zorven-mlflow-server:5000"
  # Agents
  "zorven-orchestrator:zorven-orchestrator:8010"
  "zorven-discovery-agent:zorven-discovery-agent:8020"
  "zorven-market-research-agent:zorven-market-research-agent:8021"
  "zorven-competitor-intel-agent:zorven-competitor-intel-agent:8022"
  "zorven-audience-persona-agent:zorven-audience-persona-agent:8023"
  "zorven-trend-cultural-agent:zorven-trend-cultural-agent:8024"
  "zorven-voc-agent:zorven-voc-agent:8025"
  "zorven-intelligence-agent:zorven-intelligence-agent:8030"
  "zorven-brand-positioning-agent:zorven-brand-positioning-agent:8031"
  "zorven-brand-architecture-agent:zorven-brand-architecture-agent:8032"
  "zorven-brand-personality-agent:zorven-brand-personality-agent:8033"
  "zorven-brand-naming-agent:zorven-brand-naming-agent:8034"
  "zorven-brand-story-agent:zorven-brand-story-agent:8035"
  "zorven-campaign-architecture-agent:zorven-campaign-architecture-agent:8041"
  "zorven-creative-generation-agent:zorven-creative-generation-agent:8042"
  "zorven-ad-publishing-agent:zorven-ad-publishing-agent:8043"
  "zorven-campaign-optimization-agent:zorven-campaign-optimization-agent:8044"
  "zorven-intelligence-loop-agent:zorven-intelligence-loop-agent:8045"
  "zorven-chat-titling-worker:zorven-chat-titling-worker:8040"
  "zorven-content-agent:zorven-content-agent:8050"
  "zorven-social-agent:zorven-social-agent:8060"
  "zorven-rag-uploader-agent:zorven-rag-uploader-agent:8070"
  "zorven-brand-equity-calculator:zorven-brand-equity-calculator:8090"
  "zorven-odoo-mcp-server:zorven-odoo-mcp-server:8095"
  "zorven-odoo-worker-agent:zorven-odoo-worker-agent:8100"
  "zorven-prompt-optimization:zorven-prompt-optimization:8110"
)

# ── Redis DB mapping (service → DB number) ───────────────────
# Reference only — DB numbers are hardcoded in 08-deploy-services.sh
# DB 0: backend/celery, 1: orchestrator, 2: discovery+prompt-cache,
# 3: intelligence, 4: titling, 5: content, 6: social, 7: rag-uploader,
# 8: brand-equity, 9: odoo-mcp, 10: odoo-worker, 11: market-research,
# 12: competitor-intel, 13: audience-persona, 14: trend-cultural,
# 15: voc, 16: brand-positioning, 17: brand-architecture,
# 18: brand-personality, 19: brand-naming, 20: brand-story,
# 21: campaign-architecture, 22: creative-generation, 23: ad-publishing,
# 24: campaign-optimization, 25: intelligence-loop, 26: prompt-optimization

# ── Helper: get Redis URL for a service DB ───────────────────
get_redis_url() {
  local db_num=$1
  echo "redis://${REDIS_HOST:-localhost}:${REDIS_PORT:-6379}/${db_num}"
}

# ── Helper: log with timestamp ───────────────────────────────
log() {
  echo "[$(date '+%H:%M:%S')] $*"
}

log_ok() {
  echo "[$(date '+%H:%M:%S')] ✓ $*"
}

log_err() {
  echo "[$(date '+%H:%M:%S')] ✗ $*" >&2
}
