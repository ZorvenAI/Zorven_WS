# Kong Gateway Implementation Plan

> **Version**: 1.1  
> **Status**: ✅ Implementation Complete  
> **Created**: January 24, 2026  
> **Updated**: January 24, 2026  
> **Author**: GitHub Copilot  
> **Based On**: Detail Design Document - Kong Integration (v2.0)
> **Feature Branch**: `feature/integrate-kong-gateway-service`

## Implementation Progress

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 1 | Environment Setup | ✅ Complete |
| Phase 2 | Kong Core Setup | ✅ Complete |
| Phase 3 | JWT Authentication Offloading | ✅ Complete |
| Phase 4 | GCS Direct Upload | ✅ Complete |
| Phase 5 | Kafka Event Streaming | ✅ Complete |
| Phase 6 | Security & Rate Limiting | ✅ Complete |
| Phase 7 | Testing & Validation | ✅ Complete |
| Phase 8 | Documentation | ✅ Complete |

## Files Created/Modified

### New Files
- `deployment/docker/kong/Dockerfile` - Kong Gateway container
- `deployment/docker/kong/kong.yaml` - Declarative configuration (392 lines)
- `deployment/scripts/create-kafka-topics.sh` - Kafka topic creation script
- `deployment/scripts/refresh-gcp-token.sh` - GCP token refresh script
- `deployment/config/kong/.gitkeep` - Directory placeholder
- `ai-brand-automator-frontend/src/components/common/KongFileUploader.tsx` - Direct GCS upload component
- `ai-brand-automator/tests/test_kong_integration.py` - Integration tests

### Modified Files
- `deployment/docker-compose.yml` - Added Kong, Kafka, Zookeeper services
- `ai-brand-automator/docker-compose.yml` - Added Kong, updated ports
- `ai-brand-automator/brand_automator/middleware.py` - Added KongAuthenticationMiddleware
- `ai-brand-automator/brand_automator/settings.py` - Added Kong settings
- `ai-brand-automator/onboarding/views.py` - Added `confirm_gcs_upload` endpoint
- `ai-brand-automator/.env.example` - Added Kong environment variables

## Executive Summary

This implementation plan details the step-by-step integration of Kong Gateway into the AI Brand Automator MVP. The integration will:

1. **Centralize API Traffic** - All requests flow through Kong (port 8000)
2. **Offload JWT Authentication** - Kong validates tokens, Django trusts headers
3. **Enable Direct GCS Uploads** - Bypass Django for file uploads
4. **Add Kafka Event Streaming** - Audit logging and event ingestion
5. **Improve Security** - Single entry point with rate limiting

### Current vs Target Architecture

| Component | Current State | Target State |
|-----------|--------------|--------------|
| API Gateway | None (direct to Django) | Kong (DB-less) |
| JWT Validation | Django (SimpleJWT) | Kong + Django trust |
| File Uploads | Django → GCS | Kong → GCS (direct) |
| Logging | Django logs | Kafka streaming |
| Entry Point | Django :8000 | Kong :8000, Django :8001 |

---

## Phase 1: Environment Setup (Est. 2-3 hours)

### 1.1 Create Kong Configuration Directory

**Task**: Set up directory structure for Kong configuration

```
deployment/
├── docker/
│   ├── kong/
│   │   ├── Dockerfile
│   │   └── kong.yaml           # Declarative config
│   └── ... (existing)
├── config/
│   └── kong/
│       ├── kong.yaml           # Main config (mounted)
│       └── jwt-secrets/        # JWT consumer secrets
```

**Files to Create**:
- [ ] `deployment/docker/kong/Dockerfile`
- [ ] `deployment/docker/kong/kong.yaml`
- [ ] `deployment/config/kong/.gitkeep`

### 1.2 Create Docker Network

**Task**: Ensure all services can communicate

```yaml
# In docker-compose.yml
networks:
  app-network:
    driver: bridge
```

### 1.3 Kafka Setup

**Task**: Add Kafka and Zookeeper services

**Files to Create/Modify**:
- [ ] Add Kafka + Zookeeper to `docker-compose.yml`
- [ ] Create topics: `gateway-logs`, `raw-ingestion-topic`

### 1.4 Update Port Mappings

**Current**:
- Django: 8000 (exposed)
- Frontend: 3000 (exposed)

**Target**:
- Kong: 8000 (exposed - new entry point)
- Django: 8001 (internal only)
- Frontend: 3000 (exposed)
- Kafka: 9092 (internal)
- Zookeeper: 2181 (internal)

---

## Phase 2: Kong Gateway Core Setup (Est. 3-4 hours)

### 2.1 Create Kong Dockerfile

**File**: `deployment/docker/kong/Dockerfile`

```dockerfile
FROM kong:3.4

# Install additional plugins if needed
# RUN luarocks install kong-plugin-kafka-log
# RUN luarocks install kong-plugin-kafka-upstream

# Copy declarative config
COPY kong.yaml /usr/local/kong/declarative/kong.yaml
```

### 2.2 Create Kong Declarative Configuration

**File**: `deployment/docker/kong/kong.yaml`

**Services to Configure**:

| Service | Upstream URL | Routes | Purpose |
|---------|-------------|--------|---------|
| `core-api-service` | `http://backend:8001` | `/api/v1/*` | Django API |
| `gcs-storage-service` | `https://storage.googleapis.com` | `/ingest/upload/*` | Direct GCS |
| `kafka-ingest-service` | (virtual) | `/ingest/event` | Kafka streaming |

**Plugins to Configure**:

| Plugin | Scope | Purpose |
|--------|-------|---------|
| `cors` | Global | Allow frontend origins |
| `jwt` | `core-api-route`, `gcs-upload-route` | Token validation |
| `request-transformer` | `core-api-route` | Inject X-User-ID headers |
| `request-transformer` | `gcs-upload-route` | Inject GCP credentials |
| `rate-limiting` | Global | Prevent abuse |
| `kafka-log` | Global | Audit logging |

### 2.3 Update Docker Compose

**File**: `ai-brand-automator/docker-compose.yml`

**Changes**:
1. Add Kong service
2. Add Kafka + Zookeeper services
3. Change Django port from 8000 to 8001
4. Add `app-network` to all services
5. Remove Django port exposure to host (internal only)

### 2.4 Environment Variables

**New Variables Required**:

```bash
# Kong
KONG_DATABASE=off
KONG_DECLARATIVE_CONFIG=/usr/local/kong/declarative/kong.yaml
KONG_PROXY_LISTEN=0.0.0.0:8000
KONG_ADMIN_LISTEN=0.0.0.0:8001  # Admin API (optional, for debugging)

# JWT
JWT_SECRET_KEY=${SECRET_KEY}  # Same as Django for token validation

# GCS Direct Upload
GCP_ACCESS_TOKEN=<generated-token>  # Short-lived, needs refresh script

# Kafka
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
```

---

## Phase 3: JWT Authentication Offloading (Est. 4-5 hours)

### 3.1 Kong JWT Plugin Configuration

**Task**: Configure Kong to validate JWT tokens

**Configuration in `kong.yaml`**:
```yaml
plugins:
  - name: jwt
    route: core-api-route
    config:
      key_claim_name: iss
      secret_is_base64: false
      claims_to_verify: [exp]
      # Anonymous routes handled via route-level skip
```

### 3.2 Anonymous Routes (Auth Bypass)

**Routes that MUST bypass JWT validation**:
- `POST /api/v1/auth/register/`
- `POST /api/v1/auth/login/`
- `POST /api/v1/auth/token/refresh/`
- `GET /health/`, `/ready/`, `/alive/`
- `POST /api/v1/subscriptions/webhook/` (Stripe webhook)

**Implementation**: Create separate routes without JWT plugin

### 3.3 Django Middleware Update

**Task**: Create `KongAuthenticationMiddleware`

**File**: `brand_automator/middleware.py`

**Logic**:
1. Check for `Authorization` header (JWT)
2. Since Kong validated the signature, decode WITHOUT verification
3. Extract `user_id` and `tenant_id` from claims
4. Load `User` from database
5. Set `request.user` and `request.tenant`

**Fallback**: If no JWT (anonymous routes), use `AnonymousUser`

### 3.4 Update Django Settings

**File**: `brand_automator/settings.py`

**Changes**:
```python
# Trust Kong proxy headers
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True

# Update ALLOWED_HOSTS to include Kong container
ALLOWED_HOSTS = ['backend', 'localhost', '127.0.0.1']

# Add Kong middleware
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django_tenants.middleware.main.TenantMainMiddleware',
    'brand_automator.middleware.KongAuthenticationMiddleware',  # NEW
    # ... rest
]
```

### 3.5 JWT Consumer Setup

**Task**: Register Django's JWT secret with Kong

**Option A**: Use Kong's JWT Consumer model
```yaml
consumers:
  - username: django-backend
    jwt_secrets:
      - key: django-jwt-issuer
        secret: ${JWT_SECRET_KEY}
        algorithm: HS256
```

**Option B**: Configure JWT plugin to use RS256 with public key

**Recommendation**: Use HS256 with shared secret for MVP simplicity

---

## Phase 4: GCS Direct Upload Integration (Est. 3-4 hours)

### 4.1 GCS Service Configuration

**Task**: Create Kong route for direct GCS uploads

**Route**: `/ingest/upload/{bucket}/{filename}`

**Request Flow**:
```
Client → Kong → GCS (with injected GCP token)
         │
         └── Strips user JWT
             Injects GCP Bearer token
             Transforms to GCS API format
```

### 4.2 GCP Token Management

**Challenge**: GCP access tokens expire (1 hour)

**Solutions**:

| Option | Pros | Cons |
|--------|------|------|
| Service Account JSON in Kong | Simple | Security risk |
| Token refresh script (cron) | Secure | Complexity |
| Workload Identity (GKE) | Best practice | Requires GKE |

**Recommended for MVP**: Token refresh script

**File**: `deployment/scripts/refresh-gcp-token.sh`

```bash
#!/bin/bash
# Generate new GCP token and update Kong env
TOKEN=$(gcloud auth print-access-token)
# Update Kong container env or config
```

### 4.3 Request Transformer Plugin

**Configuration**:
```yaml
plugins:
  - name: request-transformer
    route: gcs-upload-route
    config:
      remove:
        headers: ["Authorization"]  # Remove user JWT
      add:
        headers:
          - "Authorization: Bearer ${GCP_ACCESS_TOKEN}"
      replace:
        headers:
          - "Content-Type: application/octet-stream"
```

### 4.4 Frontend Upload Component Update

**File**: `ai-brand-automator-frontend/src/components/KongFileUploader.tsx`

**Changes**:
- Update upload URL from `/api/v1/files/upload/` to `/ingest/upload/{bucket}/{filename}`
- Add confirmation callback to Django after successful GCS upload
- Handle GCS response format

### 4.5 Django Asset Confirmation Endpoint

**Task**: Create endpoint for frontend to confirm upload

**Endpoint**: `POST /api/v1/assets/confirm/`

**Logic**:
1. Receive `{bucket, filename, size, content_type}`
2. Verify file exists in GCS
3. Create `Asset` record in database
4. Return asset metadata

---

## Phase 5: Kafka Event Streaming (Est. 3-4 hours)

### 5.1 Kafka Infrastructure

**Docker Compose Addition**:
```yaml
services:
  zookeeper:
    image: confluentinc/cp-zookeeper:7.5.0
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181
    networks:
      - app-network

  kafka:
    image: confluentinc/cp-kafka:7.5.0
    depends_on:
      - zookeeper
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
    networks:
      - app-network
```

### 5.2 Topic Creation

**Topics**:
- `gateway-logs` - All HTTP request/response logs
- `raw-ingestion-topic` - Event ingestion from `/ingest/event`

**Creation Script**: `deployment/scripts/create-kafka-topics.sh`

### 5.3 Kong Kafka-Log Plugin

**Configuration**:
```yaml
plugins:
  - name: kafka-log
    config:
      bootstrap_servers:
        - host: kafka
          port: 9092
      topic: gateway-logs
      timeout: 10000
      keepalive: 60000
```

### 5.4 Kong Kafka-Upstream Plugin (Event Ingestion)

**Configuration**:
```yaml
plugins:
  - name: kafka-upstream
    route: event-ingest-route
    config:
      bootstrap_servers:
        - host: kafka
          port: 9092
      topic: raw-ingestion-topic
      timeout: 1000
```

### 5.5 Event Ingestion Endpoint

**Route**: `POST /ingest/event`

**Behavior**:
- Accept JSON payload
- Return `202 Accepted` immediately
- Push to Kafka topic asynchronously

---

## Phase 6: Security & Rate Limiting (Est. 2-3 hours)

### 6.1 Global Rate Limiting

**Configuration**:
```yaml
plugins:
  - name: rate-limiting
    config:
      minute: 100
      hour: 1000
      policy: local
      fault_tolerant: true
      hide_client_headers: false
```

### 6.2 CORS Configuration

**Configuration**:
```yaml
plugins:
  - name: cors
    config:
      origins:
        - http://localhost:3000
        - https://app.aibrandautomator.com
      methods:
        - GET
        - POST
        - PUT
        - PATCH
        - DELETE
        - OPTIONS
      headers:
        - Authorization
        - Content-Type
        - X-Requested-With
      credentials: true
      max_age: 3600
```

### 6.3 Remove Django CORS Middleware

**Task**: Since Kong handles CORS, remove from Django

**File**: `brand_automator/settings.py`

**Change**:
```python
MIDDLEWARE = [
    # 'corsheaders.middleware.CorsMiddleware',  # REMOVED - Kong handles
    'django.middleware.security.SecurityMiddleware',
    # ...
]
```

### 6.4 IP Restriction (Optional)

**For Admin Endpoints**:
```yaml
plugins:
  - name: ip-restriction
    route: admin-route
    config:
      allow:
        - 10.0.0.0/8
        - 192.168.0.0/16
```

---

## Phase 7: Testing & Validation (Est. 3-4 hours)

### 7.1 Integration Tests

**Test Cases**:

| Test ID | Description | Expected Result |
|---------|-------------|-----------------|
| T-01 | Unauthenticated request to protected route | 401 Unauthorized |
| T-02 | Valid JWT to protected route | 200 OK + Django response |
| T-03 | Request to `/api/v1/auth/login/` | 200 OK (no JWT required) |
| T-04 | File upload to `/ingest/upload/...` | 200 OK from GCS |
| T-05 | Event POST to `/ingest/event` | 202 Accepted |
| T-06 | Rate limit exceeded | 429 Too Many Requests |
| T-07 | CORS preflight from allowed origin | 200 OK with headers |
| T-08 | CORS preflight from disallowed origin | No CORS headers |

### 7.2 Kafka Verification

**Commands**:
```bash
# Consume gateway logs
kafka-console-consumer --bootstrap-server localhost:9092 --topic gateway-logs --from-beginning

# Consume ingestion events
kafka-console-consumer --bootstrap-server localhost:9092 --topic raw-ingestion-topic --from-beginning
```

### 7.3 Load Testing

**Tool**: k6 or Apache Bench

**Targets**:
- Kong throughput: 1000 req/sec for `/ingest/event`
- Gateway latency: < 20ms overhead
- GCS upload: Up to 1GB files

### 7.4 Health Check Endpoints

**Kong Health**: `GET http://localhost:8000/status`

**Backend Health**: Internal via Kong → `GET /health/`

---

## Phase 8: Documentation & Deployment (Est. 2-3 hours)

### 8.1 Update Architecture Documentation

**Files to Update**:
- `docs/ai_brand_automator_mvp_architecture.md`
- `.github/copilot-instructions.md`
- `README.md`

### 8.2 Environment Variable Documentation

**New `.env.example` additions**:
```bash
# Kong Gateway
KONG_DATABASE=off
KONG_PROXY_LISTEN=0.0.0.0:8000

# Kafka
KAFKA_BOOTSTRAP_SERVERS=kafka:9092

# GCS Direct Upload
GCP_ACCESS_TOKEN=<generated-by-script>
GCS_BUCKET_NAME=your-bucket
```

### 8.3 Railway Deployment Update

**Changes to `railway.toml`**:
- Add Kong service
- Add Kafka service (or use managed Kafka)
- Update backend port from 8000 to 8001
- Update frontend `NEXT_PUBLIC_API_URL` to Kong

### 8.4 CI/CD Pipeline Update

**Changes to `.github/workflows/deploy-railway.yml`**:
- Add Kong Docker build/push
- Add Kafka topic creation step
- Update health check endpoints

---

## Implementation Order (Critical Path)

```
Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4
   │           │           │           │
   │           │           │           ▼
   │           │           │      Phase 5
   │           │           │           │
   │           │           ▼           ▼
   │           │       Phase 6 ◄───────┘
   │           │           │
   │           ▼           ▼
   │       Phase 7 ◄───────┘
   │           │
   ▼           ▼
Phase 8 ◄──────┘
```

### Dependencies

| Phase | Depends On | Can Parallelize With |
|-------|------------|---------------------|
| Phase 1 | - | - |
| Phase 2 | Phase 1 | - |
| Phase 3 | Phase 2 | Phase 4 (after Kong base) |
| Phase 4 | Phase 2 | Phase 3 |
| Phase 5 | Phase 2 | Phase 3, Phase 4 |
| Phase 6 | Phase 2 | Phase 3, Phase 4, Phase 5 |
| Phase 7 | Phase 3, 4, 5, 6 | - |
| Phase 8 | Phase 7 | - |

---

## Estimated Timeline

| Phase | Description | Estimated Time |
|-------|-------------|----------------|
| Phase 1 | Environment Setup | 2-3 hours |
| Phase 2 | Kong Core Setup | 3-4 hours |
| Phase 3 | JWT Offloading | 4-5 hours |
| Phase 4 | GCS Direct Upload | 3-4 hours |
| Phase 5 | Kafka Streaming | 3-4 hours |
| Phase 6 | Security & Rate Limiting | 2-3 hours |
| Phase 7 | Testing & Validation | 3-4 hours |
| Phase 8 | Documentation & Deployment | 2-3 hours |
| **Total** | | **22-30 hours** |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| JWT secret mismatch | Medium | High | Test thoroughly in dev |
| GCP token expiration | High | Medium | Implement refresh script |
| Kafka connectivity issues | Medium | Medium | Add retry logic |
| Breaking frontend uploads | Medium | High | Implement behind feature flag |
| Rate limiting too aggressive | Low | Medium | Start with high limits |

---

## Rollback Plan

If Kong integration causes issues:

1. **Immediate**: Update frontend `NEXT_PUBLIC_API_URL` back to Django direct
2. **Docker**: Comment out Kong service, expose Django port 8000
3. **DNS**: Point domain back to Django service
4. **Timeline**: ~15 minutes to full rollback

---

## Files to Create (Summary)

### New Files

| File | Purpose |
|------|---------|
| `deployment/docker/kong/Dockerfile` | Kong container |
| `deployment/docker/kong/kong.yaml` | Kong declarative config |
| `deployment/scripts/refresh-gcp-token.sh` | GCP token refresh |
| `deployment/scripts/create-kafka-topics.sh` | Kafka topic setup |
| `ai-brand-automator/brand_automator/kong_middleware.py` | Kong auth middleware |
| `ai-brand-automator-frontend/src/components/KongFileUploader.tsx` | Direct GCS upload |
| `docs/KONG_GATEWAY_IMPLEMENTATION_PLAN.md` | This document |

### Files to Modify

| File | Changes |
|------|---------|
| `ai-brand-automator/docker-compose.yml` | Add Kong, Kafka, Zookeeper |
| `deployment/docker-compose.yml` | Add Kong, Kafka services |
| `ai-brand-automator/brand_automator/settings.py` | Kong trust, middleware |
| `ai-brand-automator/brand_automator/middleware.py` | Add Kong middleware |
| `.github/copilot-instructions.md` | Update architecture docs |
| `docs/ai_brand_automator_mvp_architecture.md` | Add Kong section |
| `deployment/railway/railway.toml` | Add Kong service |
| `.github/workflows/deploy-railway.yml` | Add Kong deployment |

---

## Approval Checklist

- [ ] Phase 1: Environment Setup - Approved
- [ ] Phase 2: Kong Core Setup - Approved
- [ ] Phase 3: JWT Offloading - Approved
- [ ] Phase 4: GCS Direct Upload - Approved
- [ ] Phase 5: Kafka Streaming - Approved
- [ ] Phase 6: Security & Rate Limiting - Approved
- [ ] Phase 7: Testing & Validation - Approved
- [ ] Phase 8: Documentation & Deployment - Approved

---

## Next Steps After Approval

1. **Create feature branch**: `feature/kong-gateway-integration`
2. **Implement Phase 1**: Environment setup
3. **Test locally**: Verify Kong routes traffic correctly
4. **Iterate**: Complete remaining phases
5. **PR Review**: Create pull request with all changes
6. **Deploy**: Roll out to Railway production

---

**Awaiting your approval to proceed with implementation.**
