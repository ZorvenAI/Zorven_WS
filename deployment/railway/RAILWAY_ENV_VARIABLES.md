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
# Railway doesn't support Kafka directly - use external service
# Confluent Cloud: https://confluent.cloud/
# Upstash Kafka: https://upstash.com/

KAFKA_BOOTSTRAP_SERVERS=<confluent-cloud-bootstrap-servers>
KAFKA_SASL_USERNAME=<confluent-cloud-api-key>
KAFKA_SASL_PASSWORD=<confluent-cloud-api-secret>
KAFKA_SECURITY_PROTOCOL=SASL_SSL
KAFKA_SASL_MECHANISM=PLAIN

# =============================================================================
# External Services
# =============================================================================

# Google AI (Gemini)
GOOGLE_API_KEY=<your-google-ai-api-key>

# Google Cloud Storage
GS_BUCKET_NAME=<your-gcs-bucket>
GS_PROJECT_ID=<your-gcp-project-id>
GS_CREDENTIALS_PATH=/app/gcs-credentials.json

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
