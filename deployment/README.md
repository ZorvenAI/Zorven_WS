# AI Brand Automator - Deployment Guide

This directory contains the configuration needed to run Zorven locally with Docker Compose and to deploy it to **Google Cloud Run** (project `zorven-503517`, region `us-central1`, served at [zorven.ai](https://zorven.ai)).

## Architecture Overview

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│                            GCP CLOUD RUN / LOCAL DOCKER COMPOSE                    │
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
├── gcp/
│   ├── 00-config.sh             # Shared config (project, region, service list)
│   ├── 01..11-*.sh              # Numbered provisioning steps
│   ├── deploy-all.sh            # Run the full provisioning sequence
│   ├── 99-teardown.sh           # Tear down GCP resources
│   └── secrets.env.template     # Copy to secrets.env (gitignored) and fill in
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
curl http://localhost:8070/health     # RAG Uploader Agent
curl http://localhost:8085/health     # MCP Server
```

### 2. Deployment to GCP Cloud Run

#### Prerequisites

1. Install the gcloud CLI and authenticate: `gcloud auth login`
2. Set the project: `gcloud config set project zorven-503517`
3. Copy `gcp/secrets.env.template` to `gcp/secrets.env` and fill in every value,
   including `DATABASE_URL`. This file is gitignored — never commit it.

#### First-time provisioning

The numbered scripts in `gcp/` are idempotent and run in order:

```bash
cd deployment/gcp
./deploy-all.sh          # Or run 01..11 individually
```

| Script | Purpose |
|--------|---------|
| `01-setup-project.sh` | Enable APIs, create the service account |
| `02-setup-networking.sh` | VPC + `zorven-connector` Serverless VPC connector |
| `03-setup-redis.sh` | Memorystore instance `zorven-redis` |
| `04-setup-secrets.sh` | Push `secrets.env` into Secret Manager |
| `05-setup-artifact-registry.sh` | Create the `zorven` Artifact Registry repo |
| `06-mirror-images.sh` | Mirror GHCR images into Artifact Registry |
| `07-run-migrations.sh` | Run `migrate_schemas` as a Cloud Run Job |
| `08-deploy-services.sh` | Deploy all Cloud Run services |
| `09-collect-urls.sh` | Collect assigned service URLs |
| `10-redeploy-with-urls.sh` | Re-deploy with inter-service URLs wired in |
| `11-verify.sh` | Health-check every service |

#### Ongoing deploys

Ongoing deploys are automatic — see GitHub Actions below. To deploy a single
service by hand:

```bash
gcloud run services update zorven-backend \
  --region=us-central1 \
  --image=us-central1-docker.pkg.dev/zorven-503517/zorven/zorven-backend:latest
```

### 3. GitHub Actions Deployment

Two chained workflows deploy on push to `main`:

1. **`docker-publish.yml`** builds changed images and pushes them to GHCR
   (`ghcr.io/zorvenai`).
2. **`deploy-gcp.yml`** runs on that workflow's success. It mirrors only the
   changed images into Artifact Registry, runs the `zorven-migrations` Cloud Run
   Job when the backend changed, updates each affected Cloud Run service, and
   health-checks it.

Change detection uses `paths-filter`. **Adding a new service means adding a
filter in both workflows**, plus a matrix entry mapping image → Cloud Run
service(s).

**Required GitHub Secrets / config:**
- Workload Identity Federation provider + service account (`id-token: write`)
- `GHCR` read access via the built-in `GITHUB_TOKEN`

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

All 7 agent microservices are standalone FastAPI applications:

| Service | Container Name | Port | Redis DB | Dockerfile |
|---------|---------------|------|----------|------------|
| Pipeline Orchestrator | orchestrator | 8010 | 1 | `../pipeline-orchestrator-svc/Dockerfile` |
| Discovery Agent | discovery-agent | 8020 | 2 | `../discovery-agent-svc/Dockerfile` |
| Intelligence Agent | intelligence-agent | 8030 | 3 | `../intelligence-agent-svc/Dockerfile` |
| Chat Titling Worker | titling-worker | 8040 | 4 | `../chat-titling-worker/Dockerfile` |
| Content Agent | content-agent | 8050 | 5 | `../content-agent-service/Dockerfile` |
| Social Agent | social-agent | 8060 | 6 | `../social-agent-service/Dockerfile` |
| RAG Uploader Agent | rag-uploader | 8070 | 7 | `../rag-uploader-agent-service/Dockerfile` |
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
| 7 | RAG Uploader Agent | `UPLOADER_REDIS_URL=redis://redis:6379/7` |

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

*Note: Costs vary based on usage and scaling requirements. Services can be scaled to zero when idle on Cloud Run.*

## Troubleshooting

### Backend won't start
1. Check DATABASE_URL is correctly set
2. Verify Redis is running
3. Check logs: `gcloud run services logs read zorven-backend --region=us-central1`

### Frontend build fails
1. Ensure NEXT_PUBLIC_API_URL is set at build time
2. Check for TypeScript errors
3. Verify all dependencies are installed

### Celery tasks not running
1. Verify Redis connection
2. Check worker logs: `gcloud run services logs read zorven-celery-worker --region=us-central1`
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

Cloud Run performs rolling updates automatically. To force a redeployment:

```bash
gcloud run services update zorven-backend --region=us-central1 \
  --image=us-central1-docker.pkg.dev/zorven-503517/zorven/zorven-backend:latest
```

### Rollback

Cloud Run keeps every revision, so rollback is a traffic change:

```bash
# View revision history
gcloud run revisions list --service=zorven-backend --region=us-central1

# Send 100% of traffic back to a known-good revision
gcloud run services update-traffic zorven-backend \
  --region=us-central1 --to-revisions=<REVISION>=100
```

### Scaling

Per-service limits are set in `gcp/00-config.sh` (`CR_MEMORY`, `CR_CPU`,
`CR_MAX_INSTANCES`, `CR_TIMEOUT`) and applied by `08-deploy-services.sh`.
Adjust a single service directly:

```bash
gcloud run services update zorven-backend --region=us-central1 \
  --min-instances=1 --max-instances=10 --memory=1Gi
```
