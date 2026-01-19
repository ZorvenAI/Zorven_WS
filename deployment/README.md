# AI Brand Automator - Deployment Guide

This directory contains all the configuration files needed to deploy the AI Brand Automator to Railway.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              RAILWAY PLATFORM                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐    │
│  │   NGINX     │   │   NEXT.JS   │   │   DJANGO    │   │   CELERY    │    │
│  │   PROXY     │──▶│  FRONTEND   │   │   BACKEND   │   │   WORKER    │    │
│  │  (Optional) │   │  (Service)  │   │  (Service)  │   │  (Service)  │    │
│  └─────────────┘   └─────────────┘   └──────┬──────┘   └──────┬──────┘    │
│                                              │                  │          │
│  ┌─────────────┐                      ┌──────▼──────────────────▼──────┐   │
│  │   CELERY    │                      │           REDIS               │   │
│  │    BEAT     │─────────────────────▶│         (Plugin)              │   │
│  │  (Service)  │                      │    Broker + Result Backend    │   │
│  └─────────────┘                      └───────────────────────────────┘   │
│                                                                             │
│                           ┌─────────────────┐                              │
│                           │   POSTGRES      │                              │
│                           │   (Neon DB)     │                              │
│                           │   External      │                              │
│                           └─────────────────┘                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
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
│   └── nginx/
│       ├── Dockerfile           # Nginx Reverse Proxy
│       └── nginx.conf           # Nginx configuration
│
├── railway/
│   └── railway.toml             # Railway service configuration
│
├── scripts/
│   ├── start-backend.sh         # Django/Gunicorn startup
│   ├── start-celery-worker.sh   # Celery worker startup
│   ├── start-celery-beat.sh     # Celery beat startup
│   └── health-check.sh          # Health check utility
│
├── docker-compose.yml           # Local development orchestration
├── .env.production.template     # Production env vars template
└── README.md                    # This file
```

## Quick Start

### 1. Local Development with Docker

```bash
# From the project root directory
cd deployment

# Start all services (uses local PostgreSQL)
docker-compose --profile with-db up --build

# Or, if using external Neon database
docker-compose up --build

# Stop all services
docker-compose down
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

- **Queues:** `celery`, `high_priority`, `low_priority`
- **Concurrency:** 4 workers
- **Features:**
  - Auto-restarts on failure
  - Task result persistence in Redis

### Celery Beat

- **Scheduler:** Database-backed (django-celery-beat)
- **Features:**
  - Persistent schedule storage
  - Timezone aware

## Estimated Costs

| Service | Estimated Monthly Cost |
|---------|------------------------|
| Backend (Django) | $5-20 |
| Frontend (Next.js) | $5-15 |
| Celery Worker | $5-15 |
| Celery Beat | $5 |
| Redis | $5-10 |
| **Total** | **~$25-65** |

*Note: Costs vary based on usage and scaling requirements*

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
