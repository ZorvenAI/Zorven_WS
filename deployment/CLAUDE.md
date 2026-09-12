# CLAUDE.md — Deployment & Infrastructure

Operational details for Docker Compose, CI/CD, GCP Cloud Run, Redis allocation, and Kafka topics. The root `CLAUDE.md` covers architecture and code patterns.

## Docker Compose Profiles

```bash
cd deployment

docker compose up --build                                     # Core services
docker compose --profile with-kafka up --build                # + Kafka streaming
docker compose --profile with-kafka --profile with-db up      # + Local PostgreSQL
docker compose --profile with-odoo up --build                 # + Odoo CE + its PostgreSQL
docker compose --profile with-nginx up --build                # + Nginx reverse proxy
docker compose down -v                                        # Tear down
```

Four profiles: `with-kafka` (Zookeeper, Kafka, Kafka UI, pipeline consumers), `with-db` (local PostgreSQL on host 5433), `with-odoo` (Odoo CE on 8069/8072 + `odoo-db` on host 5434), `with-nginx`. Everything else starts unprofiled. `spike-stt-v2` is NOT in Compose.

**Frontend Docker build** requires `output: "standalone"` in `next.config.ts`. Without it, the `COPY --from=builder /app/.next/standalone` step fails.

## Service Ports

Kong 8000, Backend 8001 (internal in Docker), Frontend 3000, MLflow 5000, MLflow DB 5435, Redis 6379, Kafka UI 8080, Odoo 8069/8072, Odoo DB 5434.

Agent ports: Orchestrator 8010, Discovery 8020, Market Research 8021, Competitor Intel 8022, Audience Persona 8023, Trend Cultural 8024, VoC 8025, Intelligence 8030, Brand Positioning 8031, Brand Architecture 8032, Brand Personality 8033, Brand Naming 8034, Brand Story 8035, Titling 8040, Campaign Architecture 8041, Creative Generation 8042, Ad Publishing 8043, Campaign Optimization 8044, Intelligence Loop 8045, Content 8050, Social 8060, RAG Uploader 8070, MCP 8085, Brand Equity 8090, Odoo MCP 8095, Odoo Worker 8100, Prompt Optimization 8110, OIA 8120.

## Redis Database Allocation

DB 0: Django/Celery, DB 1: Orchestrator, DB 2: Discovery + Prompt Cache + OIA (`oia:v1:` prefix), DB 3: Intelligence, DB 4: Titling, DB 5: Content, DB 6: Social, DB 7: RAG Uploader, DB 8: Brand Equity, DB 9: Odoo MCP, DB 10: Odoo Worker, DB 11: Market Research, DB 12: Competitor Intel, DB 13: Audience Persona, DB 14: Trend Cultural, DB 15: VoC, DB 16–26: WF2/WF3/WF3.5/POI services.

Requires `databases 27` in redis.conf / `--databases 27` in docker-compose. If a service fails with `ERR DB index is out of range`, bump the Redis `databases` setting.

**Production (GCP Memorystore)**: Fixed at 16 databases (0–15). Services allocated DB 16–26 are mapped onto **DB 2** via `deployment/gcp/08-deploy-services.sh` — safe because each namespaces keys with a distinct prefix (`bpa:`, `baa:`, `bpv:`, `nta:`, `bsa:`, `caa:`, `cga:`, `adpub:`, `coa:`, `ila:`, `poi:`/`prompt:`). Do not reintroduce indices ≥ 16 in GCP deploy scripts. Agent `RedisManager`s **fail open** on connection errors — check service logs for `DB index is out of range`.

## Kafka Topics

Each service typically has audit and events topics (e.g., `bpa-positioning-audit-topic`, `bpa-positioning-events-topic`). Key topics:

| Topic | Producer → Consumer | Purpose |
|-------|---------------------|---------|
| `pipeline-trigger-topic` | Django → Orchestrator | Pipeline dispatch |
| `pipeline-result-topic` | Orchestrator → Django | Job results |
| `agent-trace-topic` | Orchestrator nodes → Django | Real-time node progress |
| `data-ingestion-topic` | data_ingestion → media_curation | File processing pipeline |
| `media-curation-topic` | media_curation → rag_index | RAG indexing pipeline |
| `chat-titling-topic` | Django → Titling worker | Chat session titling |
| `agent.optimization.creative_refresh` | COA → CGA | Creative refresh for fatigued ads |
| `agent.optimization.action_executed` | COA → ILA | Optimization learnings for RAG |
| `analytics-events` | Analytics → — | Metric extraction audit (conditional) |

Scheduled command topics follow `agent.commands.<agent-name>` pattern (consumed by Trend Cultural, Audience Persona, VoC agents).

## CI/CD

### Two-Tier Branching

Feature branch → PR into `development_main` (dev tier) → PR/sync merge into `main` (production).

`ci-cd.yml` runs on pushes/PRs to `main`, `develop`, `development_main` (plus `bugfixes/**`). 12 jobs: backend-tests, backend-property-tests, test-media-curation, orchestrator-tests, discovery-agent-tests, intelligence-agent-tests, odoo-mcp-server-tests, odoo-worker-tests, onboarding-intelligence-agent-tests, frontend-tests, integration-tests, build-images. Backend CI runs `black --check .`, `flake8 .`, `pytest --cov`.

### Docker Image Publishing

`docker-publish.yml` builds on pushes to `main` AND `development_main` and on PRs. PR builds get branch+SHA tags. Images pushed to GHCR (`ghcr.io/zorvenai`).

### Development Deployment

`development_main` images tagged `:development_main`, picked up by **Watchtower** (5-minute poll) running alongside `deployment/docker-compose.production.yml` on the dev host.

### Production Deployment (GCP Cloud Run)

Chain on `main`: `docker-publish.yml` → `deploy-gcp.yml` mirrors changed images to Artifact Registry (`us-central1-docker.pkg.dev/zorven-503517/zorven`), runs `zorven-migrations` Cloud Run job when backend changed, then `gcloud run services update` + health check.

Cloud Run services: `zorven-<service>`. Backend image feeds `zorven-backend` + `zorven-backend-ws`, with `zorven-celery-worker` and `zorven-celery-beat` as separate services.

Change detection uses `paths-filter` — adding a new microservice means adding filters in **both** `docker-publish.yml` and `deploy-gcp.yml`, plus a matrix entry.

One-time GCP infra provisioning: `deployment/gcp/` numbered scripts (`00-config.sh` … `11-verify.sh`).

**Railway is retired** — do not reintroduce.

## Manual COA Tick Trigger

Besides Celery Beat, the Optimization Dashboard exposes a manual trigger at `/api/v1/optimization/trigger-tick/`, proxying to COA (`X-Service-Token` auth). Requires `COA_SERVICE_URL` and `COA_SERVICE_TOKEN` on the Django backend.
