# prompt-optimization-svc

## Service Identity

| Attribute | Value |
|-----------|-------|
| Name | prompt-optimization-svc |
| Port | 8110 |
| Env Prefix | `POI_` |
| Redis DB | 26 |
| Description | MLflow prompt registry + GEPA optimization for all 15 Zorven agents |

## Directory Structure

```
app/
├── api/          # FastAPI routes + Pydantic schemas
├── core/         # Config (POI_ prefix), logging
├── cache/        # RedisManager (DB 26, key prefix poi:)
├── services/     # HealthChecker, future executors
├── scorers/      # GEPA scorer implementations (EPIC-6)
├── predict_fns/  # make_predict_fn factory (EPIC-5)
├── kafka/        # Trace + audit producers
├── tasks/        # Celery tasks (EPIC-14)
└── models/       # SQLAlchemy models (EPIC-3)
```

## Key Environment Variables

```bash
POI_MLFLOW_TRACKING_URI=http://mlflow-server:5000
POI_DATABASE_URL=postgresql://mlflow:mlflow@mlflow-db:5432/mlflow
POI_REDIS_URL=redis://localhost:6379/26
POI_KAFKA_BOOTSTRAP_SERVERS=    # Empty = disabled
POI_ANTHROPIC_API_KEY=
POI_HOST=0.0.0.0
POI_PORT=8110
POI_LOG_LEVEL=INFO
POI_CORS_ORIGINS=http://localhost:3000,http://localhost:8000
POI_SERVICE_TOKEN=
```

## Build & Run

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8110 --reload

# Tests
pytest tests/ -v
pytest tests/ -m "not integration" -v

# Format
black app/ tests/
```

## Database Migrations (Alembic)

Uses `prompt_optimization` PostgreSQL schema within the shared MLflow database.

```bash
alembic upgrade head           # Apply all migrations
alembic downgrade -1           # Rollback last migration
alembic downgrade base         # Rollback all migrations
alembic revision -m "desc"     # Create new migration (manual)
alembic revision --autogenerate -m "desc"  # Auto-detect model changes
alembic current                # Show current revision
alembic history                # Show migration history
```

Migrations run automatically on service startup via `_run_migrations()` in `main.py`.

## Health Endpoint

`GET /health` returns dependency status for MLflow, Redis, Kafka, and PostgreSQL.

```json
{
  "status": "healthy",
  "dependencies": [
    {"name": "mlflow", "status": "up", "latency_ms": 12.3},
    {"name": "redis", "status": "up", "latency_ms": 1.2},
    {"name": "kafka", "status": "disabled"},
    {"name": "postgres", "status": "up", "latency_ms": 8.5}
  ]
}
```
