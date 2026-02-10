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
