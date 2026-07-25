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
export GHCR_PREFIX="ghcr.io/naveenah"

# ── Networking ───────────────────────────────────────────────
export VPC_NAME="zorven-vpc"
export CONNECTOR_NAME="zorven-connector"
export CONNECTOR_RANGE="10.8.0.0/28"

# ── Redis (Cloud Memorystore) ────────────────────────────────
export REDIS_INSTANCE="zorven-redis"
export REDIS_TIER="basic"
export REDIS_SIZE_GB="1"
export REDIS_VERSION="REDIS_7_0"

# ── Service Account ─────────────────────────────────────────
export SA_NAME="zorven-cloudrun"
export SA_EMAIL="${SA_NAME}@${GCP_PROJECT_ID}.iam.gserviceaccount.com"

# ── Cloud Run Defaults ───────────────────────────────────────
export CR_MEMORY="512Mi"
export CR_CPU="1"
export CR_MAX_INSTANCES="2"
export CR_TIMEOUT="300"

# ── Database ─────────────────────────────────────────────────
export DATABASE_URL="postgresql://neondb_owner:npg_ihO4oHanJW8e@ep-small-dawn-aevftgxm-pooler.c-2.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

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
# Used to construct per-service REDIS_URL with correct DB number
declare -A REDIS_DB_MAP=(
  ["backend"]=0
  ["celery"]=0
  ["orchestrator"]=1
  ["discovery"]=2
  ["intelligence"]=3
  ["titling"]=4
  ["content"]=5
  ["social"]=6
  ["rag-uploader"]=7
  ["brand-equity"]=8
  ["odoo-mcp"]=9
  ["odoo-worker"]=10
  ["market-research"]=11
  ["competitor-intel"]=12
  ["audience-persona"]=13
  ["trend-cultural"]=14
  ["voc"]=15
  ["brand-positioning"]=16
  ["brand-architecture"]=17
  ["brand-personality"]=18
  ["brand-naming"]=19
  ["brand-story"]=20
  ["campaign-architecture"]=21
  ["creative-generation"]=22
  ["ad-publishing"]=23
  ["campaign-optimization"]=24
  ["intelligence-loop"]=25
  ["prompt-optimization"]=26
)

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
