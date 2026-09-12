#!/usr/bin/env bash
# Second-pass deployment: update services with correct inter-service URLs.
# Resolves the chicken-and-egg problem where services need each other's URLs.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/00-config.sh"

URLS_FILE="${SCRIPT_DIR}/service-urls.env"
if [ ! -f "${URLS_FILE}" ]; then
  log_err "service-urls.env not found. Run 09-collect-urls.sh first."
  exit 1
fi
source "${URLS_FILE}"

log "Redeploying services with correct inter-service URLs..."

# ── Helper: update env vars on a service ────────────────────
update_service() {
  local name=$1
  shift
  log "  Updating ${name}..."
  gcloud run services update "${name}" \
    --region="${GCP_REGION}" \
    --update-env-vars="$*" \
    --quiet 2>&1 | tail -1
}

# ═══════════════════════════════════════════════════════════════
# BACKEND — needs orchestrator URL and its own URL for callbacks
# ═══════════════════════════════════════════════════════════════
update_service zorven-backend \
  "ORCHESTRATOR_URL=${ZORVEN_ORCHESTRATOR_URL},BACKEND_URL=${ZORVEN_BACKEND_URL},CALLBACK_BASE_URL=${ZORVEN_BACKEND_URL}" &

# ═══════════════════════════════════════════════════════════════
# FRONTEND — needs backend API URL and brand equity URL
# ═══════════════════════════════════════════════════════════════
update_service zorven-frontend \
  "NEXT_PUBLIC_API_URL=${ZORVEN_BACKEND_URL},NEXT_PUBLIC_BRAND_EQUITY_API_URL=${ZORVEN_BRAND_EQUITY_CALCULATOR_URL}" &

# ═══════════════════════════════════════════════════════════════
# CELERY WORKER — needs orchestrator + backend URLs
# ═══════════════════════════════════════════════════════════════
update_service zorven-celery-worker \
  "ORCHESTRATOR_URL=${ZORVEN_ORCHESTRATOR_URL},BACKEND_URL=${ZORVEN_BACKEND_URL},CALLBACK_BASE_URL=${ZORVEN_BACKEND_URL}" &

wait

# ═══════════════════════════════════════════════════════════════
# ORCHESTRATOR — needs callback URL + all agent service URLs
# ═══════════════════════════════════════════════════════════════
# NOTE: every name here must match a Settings field in
# pipeline-orchestrator-svc/app/core/config.py exactly, prefixed with
# ORCHESTRATOR_. Match the field, not a pattern — most agents are
# <NAME>_AGENT_URL, but CALLBACK_BASE_URL, MLFLOW_TRACKING_URI, ODOO_MCP_URL
# and CHAT_TITLING_URL are not, and assuming the suffix is what caused this
# incident in reverse.
#
# A wrong name does not error. Pydantic cannot warn about a variable it was
# never asked for, so the field silently keeps its docker-compose default and
# every agent call resolves to a hostname that does not exist on Cloud Run.
# Twenty of these were missing the _AGENT segment and every external node
# failed with "Name or service not known" while the console showed the URLs
# as configured. tests/test_service_url_config.py now asserts this file
# against the Settings fields in both directions.
update_service zorven-orchestrator \
  "ORCHESTRATOR_CALLBACK_BASE_URL=${ZORVEN_BACKEND_URL},\
ORCHESTRATOR_MLFLOW_TRACKING_URI=${ZORVEN_MLFLOW_URL},\
ORCHESTRATOR_DISCOVERY_AGENT_URL=${ZORVEN_DISCOVERY_AGENT_URL},\
ORCHESTRATOR_MARKET_RESEARCH_AGENT_URL=${ZORVEN_MARKET_RESEARCH_AGENT_URL},\
ORCHESTRATOR_COMPETITOR_INTEL_AGENT_URL=${ZORVEN_COMPETITOR_INTEL_AGENT_URL},\
ORCHESTRATOR_AUDIENCE_PERSONA_AGENT_URL=${ZORVEN_AUDIENCE_PERSONA_AGENT_URL},\
ORCHESTRATOR_TREND_CULTURAL_AGENT_URL=${ZORVEN_TREND_CULTURAL_AGENT_URL},\
ORCHESTRATOR_VOC_AGENT_URL=${ZORVEN_VOC_AGENT_URL},\
ORCHESTRATOR_INTELLIGENCE_AGENT_URL=${ZORVEN_INTELLIGENCE_AGENT_URL},\
ORCHESTRATOR_BRAND_POSITIONING_AGENT_URL=${ZORVEN_BRAND_POSITIONING_AGENT_URL},\
ORCHESTRATOR_BRAND_ARCHITECTURE_AGENT_URL=${ZORVEN_BRAND_ARCHITECTURE_AGENT_URL},\
ORCHESTRATOR_BRAND_PERSONALITY_AGENT_URL=${ZORVEN_BRAND_PERSONALITY_AGENT_URL},\
ORCHESTRATOR_BRAND_NAMING_AGENT_URL=${ZORVEN_BRAND_NAMING_AGENT_URL},\
ORCHESTRATOR_BRAND_STORY_AGENT_URL=${ZORVEN_BRAND_STORY_AGENT_URL},\
ORCHESTRATOR_CAMPAIGN_ARCHITECTURE_AGENT_URL=${ZORVEN_CAMPAIGN_ARCHITECTURE_AGENT_URL},\
ORCHESTRATOR_CREATIVE_GENERATION_AGENT_URL=${ZORVEN_CREATIVE_GENERATION_AGENT_URL},\
ORCHESTRATOR_AD_PUBLISHING_AGENT_URL=${ZORVEN_AD_PUBLISHING_AGENT_URL},\
ORCHESTRATOR_CAMPAIGN_OPTIMIZATION_AGENT_URL=${ZORVEN_CAMPAIGN_OPTIMIZATION_AGENT_URL},\
ORCHESTRATOR_INTELLIGENCE_LOOP_AGENT_URL=${ZORVEN_INTELLIGENCE_LOOP_AGENT_URL},\
ORCHESTRATOR_CONTENT_AGENT_URL=${ZORVEN_CONTENT_AGENT_URL},\
ORCHESTRATOR_SOCIAL_AGENT_URL=${ZORVEN_SOCIAL_AGENT_URL},\
ORCHESTRATOR_RAG_UPLOADER_AGENT_URL=${ZORVEN_RAG_UPLOADER_AGENT_URL},\
ORCHESTRATOR_CHAT_TITLING_URL=${ZORVEN_CHAT_TITLING_WORKER_URL},\
ORCHESTRATOR_ODOO_MCP_URL=${ZORVEN_ODOO_MCP_SERVER_URL},\
ORCHESTRATOR_ODOO_WORKER_AGENT_URL=${ZORVEN_ODOO_WORKER_AGENT_URL}" &

# ═══════════════════════════════════════════════════════════════
# AGENTS that need backend/callback URLs
# ═══════════════════════════════════════════════════════════════

# Chat titling needs backend API URL
update_service zorven-chat-titling-worker \
  "TITLING_CORE_API_URL=${ZORVEN_BACKEND_URL},TITLING_MLFLOW_TRACKING_URI=${ZORVEN_MLFLOW_URL}" &

# Content agent needs backend API URL
update_service zorven-content-agent \
  "CONTENT_CORE_API_URL=${ZORVEN_BACKEND_URL},CONTENT_MLFLOW_TRACKING_URI=${ZORVEN_MLFLOW_URL}" &

# Social agent needs backend API URL
update_service zorven-social-agent \
  "SOCIAL_CORE_API_URL=${ZORVEN_BACKEND_URL},SOCIAL_MLFLOW_TRACKING_URI=${ZORVEN_MLFLOW_URL}" &

# Onboarding intelligence needs the backend API URL (C-02).
#
# It was missing from this second pass entirely — 08-deploy-services.sh sets
# OIA_BACKEND_BASE_URL=PLACEHOLDER like every other service, but nothing ever
# replaced it, so the deployed service has held the literal string
# "PLACEHOLDER" since it was first deployed. Nothing had called the backend
# yet, so it cost nothing and stayed invisible.
update_service zorven-onboarding-intelligence-agent \
  "OIA_BACKEND_BASE_URL=${ZORVEN_BACKEND_URL}" &

wait

# ═══════════════════════════════════════════════════════════════
# Remaining agents — just need MLflow URI update
# ═══════════════════════════════════════════════════════════════
MLFLOW_AGENTS=(
  "zorven-discovery-agent:DISCOVERY_MLFLOW_TRACKING_URI"
  "zorven-market-research-agent:MRA_MLFLOW_TRACKING_URI"
  "zorven-competitor-intel-agent:CIA_MLFLOW_TRACKING_URI"
  "zorven-audience-persona-agent:APA_MLFLOW_TRACKING_URI"
  "zorven-trend-cultural-agent:TCIA_MLFLOW_TRACKING_URI"
  "zorven-voc-agent:VOCA_MLFLOW_TRACKING_URI"
  "zorven-intelligence-agent:INTELLIGENCE_MLFLOW_TRACKING_URI"
  "zorven-brand-positioning-agent:BPA_MLFLOW_TRACKING_URI"
  "zorven-brand-architecture-agent:BAA_MLFLOW_TRACKING_URI"
  "zorven-brand-personality-agent:BPV_MLFLOW_TRACKING_URI"
  "zorven-brand-naming-agent:NTA_MLFLOW_TRACKING_URI"
  "zorven-brand-story-agent:BSA_MLFLOW_TRACKING_URI"
  "zorven-campaign-architecture-agent:CAA_MLFLOW_TRACKING_URI"
  "zorven-creative-generation-agent:CGA_MLFLOW_TRACKING_URI"
  "zorven-ad-publishing-agent:ADPUB_MLFLOW_TRACKING_URI"
  "zorven-campaign-optimization-agent:COA_MLFLOW_TRACKING_URI"
  "zorven-intelligence-loop-agent:ILA_MLFLOW_TRACKING_URI"
  "zorven-rag-uploader-agent:RAG_UPLOADER_MLFLOW_TRACKING_URI"
  "zorven-odoo-worker-agent:ODOO_WORKER_MLFLOW_TRACKING_URI"
  "zorven-prompt-optimization:POI_MLFLOW_TRACKING_URI"
)

# Deploy in batches of 8
BATCH=0
for entry in "${MLFLOW_AGENTS[@]}"; do
  IFS=':' read -r svc_name env_key <<< "${entry}"
  update_service "${svc_name}" "${env_key}=${ZORVEN_MLFLOW_URL}" &
  BATCH=$((BATCH + 1))
  if [ "$BATCH" -ge 8 ]; then
    wait
    BATCH=0
  fi
done
wait

log_ok "All services updated with correct inter-service URLs."
