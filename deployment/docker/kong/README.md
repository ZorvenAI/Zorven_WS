# Kong Gateway Integration

This directory contains the Kong Gateway configuration for the AI Brand Automator platform.

## Overview

Kong Gateway serves as the central API gateway, handling:
- **JWT Authentication Offloading** - Validates tokens before requests reach Django
- **CORS Management** - Centralized cross-origin configuration
- **Rate Limiting** - Global and per-route rate limits
- **Direct GCS Uploads** - File uploads bypass Django, go directly to GCS
- **Kafka Event Streaming** - Audit logging and event ingestion

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          EXTERNAL CLIENTS                               │
│            (Frontend, Mobile Apps, External APIs)                       │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      KONG GATEWAY (Port 8000)                           │
│  ┌─────────────┬─────────────┬─────────────┬─────────────┐             │
│  │    CORS     │     JWT     │ Rate Limit  │  Logging    │             │
│  │   Plugin    │   Plugin    │   Plugin    │   Plugin    │             │
│  └─────────────┴─────────────┴─────────────┴─────────────┘             │
└─────────────────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│   DJANGO    │      │    GCS      │      │   KAFKA     │
│   (8001)    │      │  (Storage)  │      │  (Events)   │
└─────────────┘      └─────────────┘      └─────────────┘
```

## Quick Start

### Development (Docker Compose)

```bash
# Start all services including Kong
cd ai-brand-automator
docker-compose up -d

# Or start with Kafka support
docker-compose --profile with-kafka up -d
```

### Verify Kong is Running

```bash
# Check Kong health
curl http://localhost:8000/health/

# Check Kong Admin API (debug mode only)
curl http://localhost:8002/status
```

### Access Endpoints

| Endpoint | Description | Authentication |
|----------|-------------|----------------|
| `http://localhost:8000/api/v1/auth/login/` | Login | None |
| `http://localhost:8000/api/v1/auth/register/` | Register | None |
| `http://localhost:8000/api/v1/companies/` | Companies | JWT Required |
| `http://localhost:8000/api/v1/storage/upload` | GCS Upload | JWT Required |
| `http://localhost:8000/health/` | Health Check | None |

## Configuration

### Environment Variables

```bash
# Kong Settings (in .env)
KONG_ENABLED=True
JWT_SECRET_KEY=your-jwt-secret  # Must match Django SECRET_KEY

# GCS Direct Upload
GCP_ACCESS_TOKEN=your-gcp-oauth-token
GCS_BUCKET_NAME=your-bucket-name

# Kafka (optional)
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
```

### Kong Declarative Config

The main configuration is in `docker/kong/kong.yaml`:

```yaml
_format_version: "3.0"

services:
  - name: core-api-service
    url: http://backend:8001
    routes:
      - name: core-api-route
        paths: ["/api/v1"]

consumers:
  - username: django-backend
    
jwt_secrets:
  - consumer: django-backend
    key: ai-brand-automator
    algorithm: HS256
    secret: "${JWT_SECRET_KEY}"

plugins:
  - name: cors
  - name: rate-limiting
  - name: jwt
```

## Routes

### Anonymous Routes (No Authentication)

| Route | Service | Purpose |
|-------|---------|---------|
| `/api/v1/auth/login` | auth-service | User login |
| `/api/v1/auth/register` | auth-service | User registration |
| `/api/v1/auth/token/refresh` | auth-service | Token refresh |
| `/health`, `/ready`, `/alive` | health-service | Health checks |
| `/api/v1/subscriptions/webhook` | webhook-service | Stripe webhooks |

### Protected Routes (JWT Required)

| Route | Service | Purpose |
|-------|---------|---------|
| `/api/v1/*` | core-api-service | All other API endpoints |
| `/ingest/upload` | gcs-storage-service | Direct GCS uploads |
| `/ingest/event` | kafka-ingest-service | Event ingestion |

## JWT Configuration

Kong validates JWT tokens issued by Django:

1. **Issuer Claim**: `iss: "ai-brand-automator"`
2. **Algorithm**: HS256
3. **Secret**: Shared with Django's `SECRET_KEY`
4. **Expiration**: Checked (`exp` claim)

When a valid token is presented:
1. Kong validates signature and expiration
2. Kong forwards request to Django with `X-Kong-Proxy: true` header
3. Django's `KongAuthenticationMiddleware` trusts Kong's validation
4. Django decodes token (without re-verification) to get user info

## Plugins

### CORS (Global)

```yaml
- name: cors
  config:
    origins: ["http://localhost:3000", "https://app.aibrandautomator.com"]
    methods: [GET, POST, PUT, DELETE, OPTIONS]
    credentials: true
```

### Rate Limiting (Global)

```yaml
- name: rate-limiting
  config:
    minute: 100
    hour: 1000
    policy: local
```

### JWT (Protected Routes Only)

```yaml
- name: jwt
  route: core-api-route
  config:
    key_claim_name: iss
    claims_to_verify: [exp]
```

### Kafka Log (Optional)

Uncomment in `kong.yaml` when Kafka is enabled:

```yaml
- name: kafka-log
  config:
    bootstrap_servers: [{host: kafka, port: 9092}]
    topic: gateway-logs
```

## Troubleshooting

### Kong Not Starting

```bash
# Check Kong container logs
docker logs kong-gateway

# Validate kong.yaml syntax
docker run --rm -v $(pwd)/docker/kong:/config kong:3.4 kong config parse /config/kong.yaml
```

### JWT Validation Failing

1. Check that `JWT_SECRET_KEY` matches Django's `SECRET_KEY`
2. Verify token has `iss: "ai-brand-automator"` claim
3. Check token is not expired

```bash
# Decode JWT (without verification) to inspect claims
echo "YOUR_TOKEN" | cut -d'.' -f2 | base64 -d | jq
```

### Connection Refused to Backend

1. Ensure Django is running on port 8001
2. Check Docker network connectivity
3. Verify `backend` hostname resolves to Django container

```bash
# Test from Kong container
docker exec kong-gateway ping backend
```

## Files

| File | Purpose |
|------|---------|
| `docker/kong/Dockerfile` | Kong container image |
| `docker/kong/kong.yaml` | Declarative configuration |
| `scripts/create-kafka-topics.sh` | Create Kafka topics |
| `scripts/refresh-gcp-token.sh` | Refresh GCP OAuth token |

## References

- [Kong Gateway Docs](https://docs.konghq.com/gateway/)
- [Kong DB-less Mode](https://docs.konghq.com/gateway/latest/production/deployment-topologies/db-less-and-declarative-config/)
- [Kong JWT Plugin](https://docs.konghq.com/hub/kong-inc/jwt/)
- [Kong Rate Limiting](https://docs.konghq.com/hub/kong-inc/rate-limiting/)
