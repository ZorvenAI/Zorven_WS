"""FastAPI application for prompt-optimization-svc."""

import logging
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.cache.redis_manager import RedisManager
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.kafka.producer import AuditProducer, TraceProducer
from app.services.health_checker import HealthChecker

logger = logging.getLogger(__name__)


def _run_migrations() -> None:
    """Run Alembic migrations on startup. Fails fast on error."""
    alembic_ini = Path(__file__).resolve().parents[1] / "alembic.ini"
    if not alembic_ini.exists():
        logger.warning("alembic.ini not found at %s — skipping migrations", alembic_ini)
        return
    try:
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            cwd=str(alembic_ini.parent),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            logger.info("Alembic migrations applied successfully")
            if result.stdout:
                logger.debug("Alembic stdout: %s", result.stdout)
        else:
            logger.error(
                "Alembic migration failed (exit %d)\nstdout: %s\nstderr: %s",
                result.returncode,
                result.stdout,
                result.stderr,
            )
            raise RuntimeError(
                f"Alembic migration failed (exit {result.returncode}): {result.stderr}"
            )
    except subprocess.TimeoutExpired:
        raise RuntimeError("Alembic migration timed out after 60 seconds")
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Alembic migration error: {exc}") from exc


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown hooks."""
    setup_logging()
    logger.info(
        "prompt-optimization-svc starting on %s:%d", settings.HOST, settings.PORT
    )

    # 0. Run database migrations
    _run_migrations()

    # 1. Redis
    redis_manager = RedisManager(redis_url=settings.REDIS_URL)
    redis_client = await redis_manager.connect()

    # 2. Kafka producers
    trace_producer = TraceProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    await trace_producer.start()
    audit_producer = AuditProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    await audit_producer.start()

    # 3. Health checker
    checker = HealthChecker(redis_client=redis_client)

    # 4. Assign to routes module
    from app.api import routes

    routes.health_checker = checker

    logger.info(
        "Service initialized — MLflow=%s, Redis=%s, Kafka=%s",
        settings.MLFLOW_TRACKING_URI,
        settings.REDIS_URL,
        settings.KAFKA_BOOTSTRAP_SERVERS or "disabled",
    )
    yield

    # Shutdown
    await trace_producer.stop()
    await audit_producer.stop()
    await redis_manager.close()
    routes.health_checker = None
    logger.info("prompt-optimization-svc shut down")


app = FastAPI(
    title="Prompt Optimization Service",
    description="MLflow prompt registry + GEPA optimization for Zorven AI agents",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in settings.CORS_ORIGINS.split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
