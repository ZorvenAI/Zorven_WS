# CLAUDE.md — Social Agent Service

## Overview

FastAPI microservice (port **8060**) that adapts blog content into platform-specific social media posts using Gemini and delegates publishing to the Django backend's existing automation infrastructure.

## Architecture

- Receives blog content from content-agent-service via the pipeline orchestrator
- Adapts content to platform-specific formats (LinkedIn, Twitter/X, Facebook)
- Fetches social profiles and user roles from Django internal endpoints
- Delegates actual publishing to Django (which has SDK wrappers for each platform)
- Emits audit events to `social-audit-topic` Kafka topic

## Environment Variables

All settings use the `SOCIAL_` prefix (pydantic-settings).

| Variable | Default | Description |
|---|---|---|
| `SOCIAL_REDIS_URL` | `redis://localhost:6379/6` | Redis DB 6 |
| `SOCIAL_KAFKA_BOOTSTRAP_SERVERS` | `""` | Empty = Kafka disabled |
| `SOCIAL_GOOGLE_API_KEY` | `""` | Empty = stub mode |
| `SOCIAL_GEMINI_MODEL` | `gemini-2.0-flash` | Gemini model for content adaptation |
| `SOCIAL_CORE_API_URL` | `http://localhost:8001` | Django backend URL |
| `SOCIAL_CORE_API_TOKEN` | `dev-service-token` | Service-to-service auth token |
| `SOCIAL_RATE_LIMIT_PER_MINUTE` | `10` | Rate limit per tenant |
| `SOCIAL_PORT` | `8060` | Server port |

## Running

```bash
# Local development
pip install -r requirements-dev.txt
uvicorn app.main:app --host 0.0.0.0 --port 8060 --reload

# Docker
docker compose up --build

# Tests
pytest tests/ -v
```

## Key Patterns

- Flat `app/` layout: api, core, cache, logic, services, messaging, utils
- Lifespan-managed resources in main.py
- Module-level executor in routes.py
- Graceful degradation for all external services (Redis, Kafka, Gemini)
- Async/await everywhere, `asyncio.to_thread()` for sync Gemini calls
- `asyncio_mode = "auto"` for pytest (no decorator needed)
