# prompt-optimization-svc

MLflow prompt registry and GEPA (Guided Evolutionary Prompt Augmentation) optimization service for all 15 Zorven agents.

## Overview

Provides three-tier prompt resolution (Redis cache, MLflow API, fallback), automated prompt optimization via GEPA, mandatory 24-hour canary deployments, and a comprehensive lifecycle state machine.

**Port:** 8110 | **Env Prefix:** `POI_` | **Redis:** DB 2 (prompt cache), DB 26 (general)

## Quick Start

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8110 --reload
```

## Testing

```bash
pytest tests/ -v                      # All tests
pytest tests/ -m "not integration" -v # Unit only (no Redis/Kafka)
pytest tests/ -m e2e -v               # E2E tests

# Format
black app/ tests/
```

## Health Check

```bash
curl http://localhost:8110/health
```

Returns dependency status for MLflow, Redis, Kafka, and PostgreSQL.

## Documentation

- [Operational Runbook](docs/operational_runbook.md) — Incident response, recovery procedures, and operational reference for on-call engineers
- [CLAUDE.md](CLAUDE.md) — Development guide for Claude Code

## Key Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `POI_MLFLOW_TRACKING_URI` | `http://mlflow-server:5000` | MLflow server |
| `POI_PROMPT_CACHE_REDIS_URL` | `redis://localhost:6379/2` | Prompt cache |
| `POI_KAFKA_BOOTSTRAP_SERVERS` | `""` (disabled) | Kafka |
| `POI_ANTHROPIC_API_KEY` | `""` | Anthropic API |

See the [Configuration Reference](docs/operational_runbook.md#12-configuration-reference) for the full list of 26 environment variables.

## Database Migrations

```bash
alembic upgrade head           # Apply all
alembic downgrade -1           # Rollback last
alembic current                # Show current revision
```
