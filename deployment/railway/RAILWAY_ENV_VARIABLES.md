# Railway Environment Variables
# Copy these to your Railway project's environment variables section
# ============================================================================

# =============================================================================
# Required Variables
# =============================================================================

# Django Secret Key (CRITICAL - use a strong random value)
SECRET_KEY=<generate-a-strong-secret-key>

# Database URL (Railway provides this for Postgres plugin)
DATABASE_URL=<railway-postgres-url>

# Redis URL (Railway provides this for Redis plugin)
REDIS_URL=<railway-redis-url>
CELERY_BROKER_URL=<railway-redis-url>
CELERY_RESULT_BACKEND=<railway-redis-url>

# =============================================================================
# Kong Gateway Settings
# =============================================================================
KONG_ENABLED=true
JWT_SECRET_KEY=${SECRET_KEY}
JWT_ISSUER=ai-brand-automator
KONG_HANDLES_CORS=true

# =============================================================================
# CORS Settings
# =============================================================================
# Replace with your production frontend URLs
CORS_ALLOWED_ORIGINS=https://your-frontend.railway.app,https://yourdomain.com

# =============================================================================
# Allowed Hosts
# =============================================================================
# Include your Railway service URLs
ALLOWED_HOSTS=your-backend.railway.app,your-kong.railway.app,localhost

# =============================================================================
# Kafka Settings (Use Confluent Cloud or Upstash)
# =============================================================================
# Railway doesn't support Kafka directly - use an external managed service.
# Confluent Cloud: https://confluent.cloud/ (recommended - free tier available)
# Upstash Kafka: https://upstash.com/
#
# These env vars MUST be set on ALL Railway services that use Kafka:
#   web, ingestion-consumer, ingestion-worker, curation-consumer, curation-worker
#
# After setting these, deploy the ingestion-consumer and curation-consumer
# services using the startCommands from railway.json.

KAFKA_BOOTSTRAP_SERVERS=<confluent-cloud-bootstrap-servers>
KAFKA_SASL_USERNAME=<confluent-cloud-api-key>
KAFKA_SASL_PASSWORD=<confluent-cloud-api-secret>
KAFKA_SECURITY_PROTOCOL=SASL_SSL
KAFKA_SASL_MECHANISM=PLAIN

# Enable Kafka publishing from onboarding file uploads (default: true)
ONBOARDING_KAFKA_ENABLED=true

# Enable Celery Beat scheduled Kafka consumer tasks (default: false — set to true only after Kafka is configured)
KAFKA_CONSUMERS_ENABLED=false

# Enable analytics Kafka event emission (default: false — set to true when Kafka is available)
# Events: metrics.extracted, brand.affinity.rejected, rollup.updated
ANALYTICS_KAFKA_ENABLED=false

# =============================================================================
# Google Cloud Credentials (for pipeline workers)
# =============================================================================
# Paste the FULL JSON content of your GCS service account key.
# Used by entrypoint scripts in Docker to write /app/gcs-credentials.json.
# Required on: web, ingestion-consumer, ingestion-worker,
#              curation-consumer, curation-worker
GCS_CREDENTIALS_JSON=<paste-full-service-account-json>

# =============================================================================
# Pipeline Topic Overrides (optional — defaults shown)
# =============================================================================
# INGESTION_KAFKA_INPUT_TOPIC=raw-ingestion-topic
# INGESTION_KAFKA_OUTPUT_TOPIC=curation-needed-topic
# INGESTION_KAFKA_DLQ_TOPIC=ingestion-dlq
# CURATION_KAFKA_INPUT_TOPIC=curation-needed-topic
# CURATION_KAFKA_OUTPUT_TOPIC=rag-sync-ready-topic
# CURATION_KAFKA_DLQ_TOPIC=curation-dlq

# =============================================================================
# Media Curation AI & DLP (optional — defaults shown)
# =============================================================================
# CURATION_DLP_ENABLED=true
# CURATION_AI_PROVIDER=google
# CURATION_AI_MODEL=gemini-1.5-pro
# DLP_GCP_PROJECT_ID=<same-as-GS_PROJECT_ID>

# Pipeline status webhook auth (optional)
# PIPELINE_WEBHOOK_SECRET=<shared-secret-for-pipeline-callbacks>

# =============================================================================
# External Services
# =============================================================================

# Google AI (Gemini)
GOOGLE_API_KEY=<your-google-ai-api-key>

# Google Cloud Storage
GS_BUCKET_NAME=<your-gcs-bucket>
GS_PROJECT_ID=<your-gcp-project-id>
GS_CREDENTIALS_PATH=/app/gcs-credentials.json

# Multi-tenancy: per-tenant GCS bucket defaults
# Tenants can override via the Tenant admin model; these are global fallbacks.
RAW_GCP_BUCKET_NAME=onboarding-bucket1
CURATION_GCP_BUCKET_NAME=brandsol-curation-bucket

# Multi-tenancy: GCS bucket auto-provisioning
# Set to true in production so new tenants get GCS buckets automatically.
GCS_AUTO_PROVISION=true
GCP_PROJECT_ID=brandsol

# GCP Access Token (for Kong GCS uploads - refresh periodically)
GCP_ACCESS_TOKEN=<gcp-oauth-access-token>

# Stripe (Payment Processing)
STRIPE_SECRET_KEY=sk_live_<your-stripe-secret-key>
STRIPE_PUBLISHABLE_KEY=pk_live_<your-stripe-publishable-key>
STRIPE_WEBHOOK_SECRET=whsec_<your-webhook-signing-secret>
STRIPE_PRICE_BASIC=price_<your-basic-plan-price-id>
STRIPE_PRICE_PRO=price_<your-pro-plan-price-id>
STRIPE_PRICE_ENTERPRISE=price_<your-enterprise-plan-price-id>

# =============================================================================
# Social Media OAuth (Optional - for automation features)
# =============================================================================
LINKEDIN_CLIENT_ID=<linkedin-client-id>
LINKEDIN_CLIENT_SECRET=<linkedin-client-secret>
TWITTER_CLIENT_ID=<twitter-client-id>
TWITTER_CLIENT_SECRET=<twitter-client-secret>
FACEBOOK_APP_ID=<facebook-app-id>
FACEBOOK_APP_SECRET=<facebook-app-secret>

# =============================================================================
# Production Settings
# =============================================================================
DEBUG=false
DJANGO_SETTINGS_MODULE=brand_automator.settings
PYTHONUNBUFFERED=1

# SSL/HTTPS
SECURE_PROXY_SSL_HEADER=HTTP_X_FORWARDED_PROTO,https
USE_X_FORWARDED_HOST=true
USE_X_FORWARDED_PORT=true

# =============================================================================
# Service-to-Service Authentication (shared secrets)
# =============================================================================
# These MUST match across all services that communicate:
ORCHESTRATOR_SERVICE_TOKEN=<shared-service-token>
ORCHESTRATOR_CALLBACK_TOKEN=<shared-callback-token>
WORKER_TOKEN=<shared-worker-token>

# =============================================================================
# Pipeline Orchestrator (ORCHESTRATOR_ prefix)
# =============================================================================
ORCHESTRATOR_SERVICE_TOKEN=<same-as-backend>
ORCHESTRATOR_CALLBACK_TOKEN=<same-as-backend>
ORCHESTRATOR_REDIS_URL=<railway-redis-url>/1
ORCHESTRATOR_KAFKA_BOOTSTRAP_SERVERS=
ORCHESTRATOR_GOOGLE_API_KEY=<gemini-api-key>
ORCHESTRATOR_LOG_LEVEL=INFO
# Agent URLs (Railway internal DNS):
ORCHESTRATOR_DISCOVERY_AGENT_URL=http://discovery-agent.railway.internal:8020
ORCHESTRATOR_CONTENT_AGENT_URL=http://content-agent.railway.internal:8050
ORCHESTRATOR_SOCIAL_AGENT_URL=http://social-agent.railway.internal:8060
ORCHESTRATOR_INTELLIGENCE_AGENT_URL=http://intelligence-agent.railway.internal:8030
ORCHESTRATOR_RAG_UPLOADER_AGENT_URL=http://rag-uploader.railway.internal:8070
ORCHESTRATOR_MARKET_RESEARCH_AGENT_URL=http://market-research-agent.railway.internal:8021

# =============================================================================
# Discovery Agent (DISCOVERY_ prefix, Redis DB 2)
# =============================================================================
DISCOVERY_REDIS_URL=<railway-redis-url>/2
DISCOVERY_KAFKA_BOOTSTRAP_SERVERS=
DISCOVERY_TAVILY_API_KEY=<tavily-api-key>
DISCOVERY_GOOGLE_API_KEY=<gemini-api-key>
DISCOVERY_GCS_PROJECT_ID=<gcp-project>
DISCOVERY_GCS_BUCKET_NAME=<bucket-name>
DISCOVERY_LOG_LEVEL=INFO

# =============================================================================
# Intelligence Agent (INTELLIGENCE_ prefix, Redis DB 3)
# =============================================================================
INTELLIGENCE_REDIS_URL=<railway-redis-url>/3
INTELLIGENCE_KAFKA_BOOTSTRAP_SERVERS=
INTELLIGENCE_GEMINI_API_KEY=<gemini-api-key>
INTELLIGENCE_GCS_PROJECT_ID=<gcp-project>
INTELLIGENCE_GCS_BUCKET_NAME=<bucket-name>
INTELLIGENCE_LOG_LEVEL=INFO

# =============================================================================
# Chat Titling Worker (TITLING_ prefix, Redis DB 4)
# =============================================================================
TITLING_REDIS_URL=<railway-redis-url>/4
TITLING_KAFKA_BOOTSTRAP_SERVERS=
TITLING_GOOGLE_API_KEY=<gemini-api-key>
TITLING_CORE_API_URL=http://backend.railway.internal:8000
TITLING_WORKER_TOKEN=<same-as-backend-WORKER_TOKEN>
TITLING_LOG_LEVEL=INFO

# =============================================================================
# Content Agent (CONTENT_ prefix, Redis DB 5)
# =============================================================================
CONTENT_REDIS_URL=<railway-redis-url>/5
CONTENT_KAFKA_BOOTSTRAP_SERVERS=
CONTENT_GOOGLE_API_KEY=<gemini-api-key>
CONTENT_GCS_PROJECT_ID=<gcp-project>
CONTENT_GCS_BUCKET_NAME=<bucket-name>
CONTENT_CORE_API_URL=http://backend.railway.internal:8000
CONTENT_CORE_API_TOKEN=<same-as-ORCHESTRATOR_SERVICE_TOKEN>
CONTENT_LOG_LEVEL=INFO

# =============================================================================
# Social Agent (SOCIAL_ prefix, Redis DB 6)
# =============================================================================
SOCIAL_REDIS_URL=<railway-redis-url>/6
SOCIAL_KAFKA_BOOTSTRAP_SERVERS=
SOCIAL_GOOGLE_API_KEY=<gemini-api-key>
SOCIAL_CORE_API_URL=http://backend.railway.internal:8000
SOCIAL_CORE_API_TOKEN=<same-as-ORCHESTRATOR_SERVICE_TOKEN>
SOCIAL_MCP_SERVER_URL=http://mcp-server.railway.internal:8085/sse
SOCIAL_LOG_LEVEL=INFO

# =============================================================================
# RAG Uploader Agent (UPLOADER_ prefix, Redis DB 7)
# =============================================================================
UPLOADER_REDIS_URL=<railway-redis-url>/7
UPLOADER_KAFKA_BOOTSTRAP_SERVERS=
UPLOADER_GOOGLE_API_KEY=<gemini-api-key>
UPLOADER_GCS_PROJECT_ID=<gcp-project>
UPLOADER_GCS_BUCKET_NAME=<bucket-name>
UPLOADER_CORE_API_URL=http://backend.railway.internal:8000
UPLOADER_CORE_API_TOKEN=<same-as-ORCHESTRATOR_SERVICE_TOKEN>
UPLOADER_LOG_LEVEL=INFO

# =============================================================================
# Market Research Agent (MRA_ prefix, Redis DB 11)
# =============================================================================
MRA_REDIS_URL=<railway-redis-url>/11
MRA_KAFKA_BOOTSTRAP_SERVERS=
MRA_ANTHROPIC_API_KEY=<anthropic-api-key>
MRA_TAVILY_API_KEY=<tavily-api-key>
MRA_GNEWS_API_KEY=<gnews-api-key>
MRA_LLM_MODEL=claude-sonnet-4-5-20250929
MRA_LOG_LEVEL=INFO
MRA_RBAC_ENABLED=true
MRA_RAG_ENABLED=false
MRA_RAG_SERVICE_URL=http://rag-uploader-agent.railway.internal:8070
MRA_CONFIDENCE_THRESHOLD=0.7
MRA_TOKEN_BUDGET_PER_SESSION=50000

# =============================================================================
# Competitor Intelligence Agent (CIA_ prefix, Redis DB 12)
# =============================================================================
CIA_REDIS_URL=<railway-redis-url>/12
CIA_KAFKA_BOOTSTRAP_SERVERS=
CIA_ANTHROPIC_API_KEY=<anthropic-api-key>
CIA_TAVILY_API_KEY=<tavily-api-key>
CIA_LLM_MODEL=claude-sonnet-4-5-20250929
CIA_LOG_LEVEL=INFO
CIA_RBAC_ENABLED=true
CIA_RAG_ENABLED=false
CIA_RAG_SERVICE_URL=http://rag-uploader-agent.railway.internal:8070

# =============================================================================
# Audience Persona Agent (APA_ prefix, Redis DB 13)
# =============================================================================
APA_REDIS_URL=<railway-redis-url>/13
APA_KAFKA_BOOTSTRAP_SERVERS=
APA_ANTHROPIC_API_KEY=<anthropic-api-key>
APA_TAVILY_API_KEY=<tavily-api-key>
APA_LLM_MODEL=claude-sonnet-4-5-20250929
APA_LOG_LEVEL=INFO
APA_RBAC_ENABLED=true
APA_RAG_ENABLED=false
APA_RAG_SERVICE_URL=http://rag-uploader-agent.railway.internal:8070

# =============================================================================
# Trend & Cultural Insights Agent (TCIA_ prefix, Redis DB 14)
# =============================================================================
TCIA_REDIS_URL=<railway-redis-url>/14
TCIA_KAFKA_BOOTSTRAP_SERVERS=
TCIA_ANTHROPIC_API_KEY=<anthropic-api-key>
TCIA_TAVILY_API_KEY=<tavily-api-key>
TCIA_LLM_MODEL=claude-sonnet-4-5-20250929
TCIA_LOG_LEVEL=INFO

# =============================================================================
# Voice of Customer Agent (VOCA_ prefix, Redis DB 15)
# =============================================================================
VOCA_REDIS_URL=<railway-redis-url>/15
VOCA_KAFKA_BOOTSTRAP_SERVERS=
VOCA_ANTHROPIC_API_KEY=<anthropic-api-key>
VOCA_TAVILY_API_KEY=<tavily-api-key>
VOCA_LLM_MODEL=claude-sonnet-4-5-20250929
VOCA_LOG_LEVEL=INFO

# =============================================================================
# Brand Positioning Agent (BPA_ prefix, Redis DB 16)
# =============================================================================
BPA_REDIS_URL=<railway-redis-url>/16
BPA_KAFKA_BOOTSTRAP_SERVERS=
BPA_ANTHROPIC_API_KEY=<anthropic-api-key>
BPA_ANTHROPIC_MODEL=claude-sonnet-4-5-20250929
BPA_LOG_LEVEL=INFO

# =============================================================================
# Brand Architecture Agent (BAA_ prefix, Redis DB 17)
# =============================================================================
BAA_REDIS_URL=<railway-redis-url>/17
BAA_KAFKA_BOOTSTRAP_SERVERS=
BAA_ANTHROPIC_API_KEY=<anthropic-api-key>
BAA_ANTHROPIC_MODEL=claude-sonnet-4-5-20250929
BAA_LOG_LEVEL=INFO

# =============================================================================
# Brand Personality Agent (BPV_ prefix, Redis DB 18)
# =============================================================================
BPV_REDIS_URL=<railway-redis-url>/18
BPV_KAFKA_BOOTSTRAP_SERVERS=
BPV_ANTHROPIC_API_KEY=<anthropic-api-key>
BPV_ANTHROPIC_MODEL=claude-sonnet-4-5-20250929
BPV_LOG_LEVEL=INFO

# =============================================================================
# Brand Naming Agent (NTA_ prefix, Redis DB 19)
# =============================================================================
NTA_REDIS_URL=<railway-redis-url>/19
NTA_KAFKA_BOOTSTRAP_SERVERS=
NTA_ANTHROPIC_API_KEY=<anthropic-api-key>
NTA_ANTHROPIC_MODEL=claude-sonnet-4-5-20250929
NTA_LOG_LEVEL=INFO

# =============================================================================
# Brand Story Agent (BSA_ prefix, Redis DB 20)
# =============================================================================
BSA_REDIS_URL=<railway-redis-url>/20
BSA_KAFKA_BOOTSTRAP_SERVERS=
BSA_ANTHROPIC_API_KEY=<anthropic-api-key>
BSA_ANTHROPIC_MODEL=claude-sonnet-4-5-20250929
BSA_LOG_LEVEL=INFO

# =============================================================================
# Campaign Architecture Agent (CAA_ prefix, Redis DB 21)
# =============================================================================
CAA_REDIS_URL=<railway-redis-url>/21
CAA_KAFKA_BOOTSTRAP_SERVERS=
CAA_ANTHROPIC_API_KEY=<anthropic-api-key>
CAA_ANTHROPIC_MODEL=claude-sonnet-4-5-20250929
CAA_LOG_LEVEL=INFO

# =============================================================================
# Creative Generation Agent (CGA_ prefix, Redis DB 22)
# =============================================================================
CGA_REDIS_URL=<railway-redis-url>/22
CGA_KAFKA_BOOTSTRAP_SERVERS=
CGA_ANTHROPIC_API_KEY=<anthropic-api-key>
CGA_ANTHROPIC_MODEL=claude-sonnet-4-5-20250929
CGA_LOG_LEVEL=INFO

# =============================================================================
# Ad Publishing Agent (ADPUB_ prefix, Redis DB 23)
# =============================================================================
ADPUB_REDIS_URL=<railway-redis-url>/23
ADPUB_KAFKA_BOOTSTRAP_SERVERS=
ADPUB_ANTHROPIC_API_KEY=<anthropic-api-key>
ADPUB_ANTHROPIC_MODEL=claude-sonnet-4-5-20250929
ADPUB_LOG_LEVEL=INFO

# =============================================================================
# Campaign Optimization Agent (COA_ prefix, Redis DB 24)
# =============================================================================
COA_REDIS_URL=<railway-redis-url>/24
COA_KAFKA_BOOTSTRAP_SERVERS=
COA_ANTHROPIC_API_KEY=<anthropic-api-key>
COA_ANTHROPIC_MODEL=claude-sonnet-4-5-20250929
COA_LOG_LEVEL=INFO

# =============================================================================
# Intelligence Loop Agent (ILA_ prefix, Redis DB 25)
# =============================================================================
ILA_REDIS_URL=<railway-redis-url>/25
ILA_KAFKA_BOOTSTRAP_SERVERS=
ILA_ANTHROPIC_API_KEY=<anthropic-api-key>
ILA_ANTHROPIC_MODEL=claude-sonnet-4-5-20250929
ILA_LOG_LEVEL=INFO
