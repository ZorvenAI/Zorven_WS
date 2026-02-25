# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Service Does

`chat-titling-worker` is a lightweight FastAPI microservice (port 8040) that auto-titles new chat sessions. It consumes events from Kafka (`chat-titling-topic`), generates concise 3-5 word titles using Gemini Flash, and PATCHes them back to the Django backend via an internal endpoint. Redis provides deduplication to prevent duplicate title generation.

## Build & Run Commands

```bash
# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run the service
uvicorn app.main:app --host 0.0.0.0 --port 8040

# Run all tests
pytest tests/ -v

# Run unit tests only (no Redis needed)
pytest tests/ -m "not integration" -v

# Run a single test file
pytest tests/test_handler.py -v

# Format code
black app/ tests/

# Docker Compose (standalone dev)
docker compose up --build
```

## Architecture

Flat `app/` layout following the discovery-agent-svc pattern:

- **`app/api/`** — FastAPI routes (health check). Module-level `consumer` variable set by lifespan.
- **`app/core/`** — Config (`Settings` with `TITLING_` env prefix) and structured logging.
- **`app/cache/`** — `RedisManager` with dedup key (`titling:processed:{session_id}`, 24h TTL). Fails open on Redis error.
- **`app/messaging/`** — `TitlingConsumer` (Kafka consumer for `chat-titling-topic`), `TitlingEvent` schema.
- **`app/logic/`** — `TitleGenerator` (Gemini Flash + stub fallback), `TitlingHandler` (orchestrates dedup → generate → callback).
- **`app/services/`** — `CoreApiClient` (HTTP PATCH to Django internal endpoint with `X-Worker-Token` auth).

## Event Flow

```
Kafka (chat-titling-topic) → TitlingConsumer
    → TitlingHandler.handle(event)
        → RedisManager.is_processed()     [dedup check]
        → TitleGenerator.generate()        [Gemini Flash / stub]
        → CoreApiClient.update_title()     [PATCH to Django]
        → RedisManager.mark_processed()    [dedup flag]
```

## Environment Variables

All prefixed with `TITLING_`. Key ones:
- `TITLING_GOOGLE_API_KEY` — empty = stub mode (first 5 words of message)
- `TITLING_REDIS_URL` — default `redis://localhost:6379/4` (DB 4)
- `TITLING_KAFKA_BOOTSTRAP_SERVERS` — default `localhost:9092`
- `TITLING_KAFKA_TOPIC` — default `chat-titling-topic`
- `TITLING_CORE_API_URL` — default `http://localhost:8001`
- `TITLING_WORKER_TOKEN` — shared secret for Django auth

## Testing Conventions

- `asyncio_mode = "auto"` in pyproject.toml — no `@pytest.mark.asyncio` decorators needed
- Integration tests require Redis and are marked `@pytest.mark.integration`
- All external dependencies (Redis, Kafka, Gemini, httpx) are mocked in unit tests
- `pytest-httpx` for HTTP client testing

## Redis Key Patterns

- `titling:processed:{session_id}` — dedup flag, 24h TTL
