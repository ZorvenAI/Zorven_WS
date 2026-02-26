# AI Brand Automator - Deployment Guide

This directory contains all the configuration files needed to deploy the AI Brand Automator to Railway.

## Architecture Overview

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│                              RAILWAY PLATFORM / LOCAL DOCKER COMPOSE               │
├───────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐          │
│  │   NGINX     │   │   NEXT.JS   │   │    KONG     │   │   DJANGO    │          │
│  │   PROXY     │──▶│  FRONTEND   │   │   GATEWAY   │──▶│   BACKEND   │          │
│  │  (Optional) │   │  :3000      │   │   :8000     │   │   :8001     │          │
│  └─────────────┘   └─────────────┘   └─────────────┘   └──────┬──────┘          │
│                                                                 │                │
│  ┌─────────────┐   ┌─────────────┐                       ┌─────▼─────┐          │
│  │   CELERY    │   │   CELERY    │                       │   REDIS   │          │
│  │   WORKER    │   │    BEAT     │                       │   :6379   │          │
│  │  (Service)  │   │  (Service)  │                       │  (7 DBs)  │          │
│  └─────────────┘   └─────────────┘                       └─────┬─────┘          │
│                                                                 │                │
│  ┌──────────────────────────────────────────────────────────────┼──────────────┐ │
│  │                    AGENT MICROSERVICES                        │              │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │              │ │
│  │  │  Orchestrator│  │  Discovery   │  │ Intelligence │       │              │ │
│  │  │  :8010       │  │  :8020       │  │  :8030       │───────┘              │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘                      │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │ │
│  │  │ Chat Titling │  │   Content    │  │    Social    │  │  MCP Server  │   │ │
│  │  │  :8040       │  │   :8050      │  │    :8060     │  │  :8085       │   │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘   │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                   │
│  ┌─────────────────┐   ┌─────────────────┐   ┌──────────────┐  (Optional)       │
│  │   POSTGRES      │   │     KAFKA       │   │  KAFKA UI    │                   │
│  │   (Neon / local)│   │     :9092       │   │  :8080       │                   │
│  └─────────────────┘   └─────────────────┘   └──────────────┘                   │
│                                                                                   │
└───────────────────────────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
deployment/
├── docker/
│   ├── backend/
│   │   └── Dockerfile           # Django API (multi-stage build)
│   ├── frontend/
│   │   └── Dockerfile           # Next.js (standalone mode)
│   ├── celery-worker/
│   │   └── Dockerfile           # Celery Worker
│   ├── celery-beat/
│   │   └── Dockerfile           # Celery Beat Scheduler
│   ├── kong/
│   │   ├── Dockerfile           # Kong Gateway (DB-less mode)
│   │   └── kong.yaml            # Declarative Kong configuration
│   └── nginx/
│       ├── Dockerfile           # Nginx Reverse Proxy
│       └── nginx.conf           # Nginx configuration
│
├── railway/
│   └── railway.toml             # Railway service configuration
│
├── scripts/
│   ├── start-backend.sh         # Django/Gunicorn startup (migrations, static, gunicorn)
│   ├── start-celery-worker.sh   # Celery worker startup (6 queues)
│   ├── start-celery-beat.sh     # Celery beat startup
│   ├── create-kafka-topics.sh   # Create Kafka topics with retention policies
│   └── health-check.sh          # Health check utility
│
├── docker-compose.yml           # Master compose: all services + profiles
├── .env.production.template     # Production env vars template
└── README.md                    # This file

# Microservice Dockerfiles (in their own directories):
# ../pipeline-orchestrator-svc/Dockerfile
# ../discovery-agent-svc/Dockerfile
# ../intelligence-agent-svc/Dockerfile
# ../chat-titling-worker/Dockerfile
# ../content-agent-service/Dockerfile
# ../social-agent-service/Dockerfile
```

## Quick Start

### 1. Local Development with Docker

```bash
# From the project root
cd deployment

# Start core services + all microservices (Kong, Django, Frontend, 6 agents, Redis, Celery)
docker compose up --build

# Include Kafka for event streaming (chat titling, pipeline triggers)
docker compose --profile with-kafka up --build

# Include local PostgreSQL (instead of Neon)
docker compose --profile with-db up --build

# Include Nginx reverse proxy
docker compose --profile with-nginx up --build

# All profiles combined
docker compose --profile with-kafka --profile with-db --profile with-nginx up --build

# Stop all services
docker compose down -v
```

#### Verify Services

```bash
curl http://localhost:8000/health/    # Kong → Django
curl http://localhost:8010/health     # Pipeline Orchestrator
curl http://localhost:8020/health     # Discovery Agent
curl http://localhost:8030/health     # Intelligence Agent
curl http://localhost:8040/health     # Chat Titling Worker
curl http://localhost:8050/health     # Content Agent
curl http://localhost:8060/health     # Social Agent
curl http://localhost:8085/health     # MCP Server
```

### 2. Deployment to Railway

#### Prerequisites

1. Install Railway CLI: `npm install -g @railway/cli`
2. Login to Railway: `railway login`
3. Create a new project: `railway init`

#### Setup Services

1. **Create Redis Service**
   - In Railway dashboard, click "New" → "Database" → "Redis"

2. **Create Backend Service**
   ```bash
   railway add --service backend
   ```

3. **Create Frontend Service**
   ```bash
   railway add --service frontend
   ```

4. **Create Celery Worker Service**
   ```bash
   railway add --service celery-worker
   ```

5. **Create Celery Beat Service**
   ```bash
   railway add --service celery-beat
   ```

6. **Create MCP Server Service**
   ```bash
   railway add --service mcp-server
   ```

7. **Create Pipeline Orchestrator Service**
   ```bash
   railway add --service orchestrator
   ```

8. **Create Discovery Agent Service**
   ```bash
   railway add --service discovery-agent
   ```

9. **Create Intelligence Agent Service**
   ```bash
   railway add --service intelligence-agent
   ```

#### Configure Environment Variables

1. Copy `.env.production.template` and fill in your values
2. In Railway dashboard, add environment variables to each service:

**Backend Service:**
- `SECRET_KEY`
- `DEBUG=False`
- `ALLOWED_HOSTS`
- `DATABASE_URL` (your Neon connection string)
- `REDIS_URL` (Railway provides this via variable reference)
- `GOOGLE_API_KEY`
- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `CORS_ALLOWED_ORIGINS`

**Frontend Service:**
- `NEXT_PUBLIC_API_URL` (Backend service URL)

**Celery Worker & Beat:**
- Same as Backend, but without `ALLOWED_HOSTS` and `CORS_ALLOWED_ORIGINS`

**Pipeline Orchestrator:**
- `ORCHESTRATOR_SERVICE_TOKEN` (must match backend's)
- `ORCHESTRATOR_CALLBACK_TOKEN` (must match backend's)
- `ORCHESTRATOR_REDIS_URL` (Redis DB 1)

**Discovery Agent:**
- `DISCOVERY_REDIS_URL` (Redis DB 2)
- `DISCOVERY_TAVILY_API_KEY`

**Intelligence Agent:**
- `INTELLIGENCE_REDIS_URL` (Redis DB 3)
- `INTELLIGENCE_GEMINI_API_KEY`

#### Deploy

```bash
# Deploy all services
railway up

# Or deploy individual services
railway up --service backend
railway up --service frontend
```

### 3. GitHub Actions Deployment

The workflow at `.github/workflows/deploy-railway.yml` automatically deploys on push to `main`.

**Required GitHub Secrets:**
- `RAILWAY_TOKEN` - Get from Railway account settings
- `RAILWAY_BACKEND_URL` - Backend service URL (for health checks)
- `RAILWAY_FRONTEND_URL` - Frontend service URL (for health checks)

## Service Details

### Backend (Django + Gunicorn)

- **Port:** 8000
- **Health Check:** `/health/`
- **Features:**
  - Auto-runs migrations on startup
  - Collects static files
  - Waits for database connection
  - 4 Gunicorn workers with 2 threads each

### Frontend (Next.js)

- **Port:** 3000
- **Build:** Standalone mode for minimal bundle
- **Features:**
  - Optimized production build
  - Static file caching

### Celery Worker

- **Queues:** `celery`, `high_priority`, `low_priority`, `orchestration`, `ingestion`, `curation`
- **Concurrency:** 4 workers
- **Features:**
  - Auto-restarts on failure
  - Task result persistence in Redis

### Celery Beat

- **Scheduler:** Database-backed (django-celery-beat)
- **Features:**
  - Persistent schedule storage
  - Timezone aware
  - Every 60s: `publish_scheduled_posts`
  - Every 5m: `check_stale_jobs` (marks stuck pipeline jobs as FAILED)

### Agent Microservices

All 6 agent microservices are standalone FastAPI applications:

| Service | Container Name | Port | Redis DB | Dockerfile |
|---------|---------------|------|----------|------------|
| Pipeline Orchestrator | orchestrator | 8010 | 1 | `../pipeline-orchestrator-svc/Dockerfile` |
| Discovery Agent | discovery-agent | 8020 | 2 | `../discovery-agent-svc/Dockerfile` |
| Intelligence Agent | intelligence-agent | 8030 | 3 | `../intelligence-agent-svc/Dockerfile` |
| Chat Titling Worker | titling-worker | 8040 | 4 | `../chat-titling-worker/Dockerfile` |
| Content Agent | content-agent | 8050 | 5 | `../content-agent-service/Dockerfile` |
| Social Agent | social-agent | 8060 | 6 | `../social-agent-service/Dockerfile` |
| MCP Server | mcp-server | 8085 | 0 | `docker/backend/Dockerfile` |

### Redis Database Allocation

A single Redis instance is shared across all services, with each using a different database number:

| DB | Service | Environment Variable |
|----|---------|---------------------|
| 0 | Django Backend (Celery) | `REDIS_URL=redis://redis:6379/0` |
| 1 | Pipeline Orchestrator | `ORCHESTRATOR_REDIS_URL=redis://redis:6379/1` |
| 2 | Discovery Agent | `DISCOVERY_REDIS_URL=redis://redis:6379/2` |
| 3 | Intelligence Agent | `INTELLIGENCE_REDIS_URL=redis://redis:6379/3` |
| 4 | Chat Titling Worker | `TITLING_REDIS_URL=redis://redis:6379/4` |
| 5 | Content Agent | `CONTENT_REDIS_URL=redis://redis:6379/5` |
| 6 | Social Agent | `SOCIAL_REDIS_URL=redis://redis:6379/6` |

### Kafka Setup (Optional)

Kafka and Zookeeper are optional, gated behind the `with-kafka` profile:

```bash
docker compose --profile with-kafka up --build
# Access Kafka UI at http://localhost:8080
```

Kafka is used for:
- **Data pipeline**: ingestion → curation → RAG indexing
- **Orchestration**: pipeline trigger, agent trace, pipeline result topics
- **Chat**: auto-titling topic

When Kafka is not running, the system falls back to:
- HTTP dispatch for orchestration (`OrchestratorDispatcher`)
- Celery tasks for data pipeline
- No auto-titling (or synchronous fallback)

## Estimated Costs

| Service | Estimated Monthly Cost |
|---------|------------------------|
| Backend (Django) | $5-20 |
| Frontend (Next.js) | $5-15 |
| Celery Worker | $5-15 |
| Celery Beat | $5 |
| MCP Server | $5 |
| Pipeline Orchestrator | $5-10 |
| Discovery Agent | $5-10 |
| Intelligence Agent | $5-10 |
| Chat Titling Worker | $5 |
| Content Agent | $5-10 |
| Social Agent | $5-10 |
| Redis | $5-10 |
| **Total** | **~$60-125** |

*Note: Costs vary based on usage and scaling requirements. Services can be scaled to zero when idle on Railway.*

## Troubleshooting

### Backend won't start
1. Check DATABASE_URL is correctly set
2. Verify Redis is running
3. Check logs: `railway logs --service backend`

### Frontend build fails
1. Ensure NEXT_PUBLIC_API_URL is set at build time
2. Check for TypeScript errors
3. Verify all dependencies are installed

### Celery tasks not running
1. Verify Redis connection
2. Check worker logs: `railway logs --service celery-worker`
3. Ensure tasks are discovered: check `autodiscover_tasks()` in celery.py

### Database connection issues
1. Verify Neon database is accessible
2. Check connection string includes `?sslmode=require`
3. Verify IP allowlist if configured

### Pipeline orchestration not working
1. Verify `ORCHESTRATOR_URL` points to the running orchestrator service
2. Check `ORCHESTRATOR_SERVICE_TOKEN` matches between backend and orchestrator
3. Check `ORCHESTRATOR_CALLBACK_TOKEN` matches between orchestrator and backend
4. Check orchestrator logs: `docker compose logs -f orchestrator`
5. Verify Redis is accessible on DB 1

### Microservice not responding
1. Check health endpoint: `curl http://localhost:<PORT>/health`
2. Verify Redis connection for the service's assigned DB
3. Check logs: `docker compose logs -f <service-name>`
4. Verify environment variables are set (each service has its own prefix)

## Maintenance

### Rolling Updates

Railway performs rolling updates automatically. To force a redeployment:

```bash
railway redeploy --service backend
```

### Rollback

```bash
# View deployment history
railway deployments --service backend

# Rollback to previous deployment
railway rollback --service backend
```

### Scaling

In Railway dashboard, adjust service replicas and resource limits as needed.
