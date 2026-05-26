"""FastAPI application for prompt-optimization-svc."""

import logging
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.cache.prompt_cache import PromptCacheManager
from app.cache.redis_manager import RedisManager
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.kafka.producer import AuditProducer, LifecycleProducer, TraceProducer
from app.logic.lifecycle import PromptLifecycleManager
from app.services.health_checker import HealthChecker
from app.services.mlflow_registry import MLflowPromptRegistry

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

    # 0. Load context variable registry into memory
    from app.registries.context_variables import CONTEXT_REGISTRY

    logger.info(
        "Context variable registry loaded: %d variables across all agents",
        len(CONTEXT_REGISTRY),
    )

    # 0b. Run database migrations
    _run_migrations()

    # 1. Redis (general cache)
    redis_manager = RedisManager(redis_url=settings.REDIS_URL)
    redis_client = await redis_manager.connect()

    # 1b. Redis DB 2 (prompt cache, locks, progress)
    prompt_cache = PromptCacheManager(redis_url=settings.PROMPT_CACHE_REDIS_URL)
    await prompt_cache.connect()

    # 2. Kafka producers
    trace_producer = TraceProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    await trace_producer.start()
    audit_producer = AuditProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    await audit_producer.start()
    lifecycle_producer = LifecycleProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    await lifecycle_producer.start()

    # 3. MLflow Prompt Registry
    registry: MLflowPromptRegistry | None = None
    try:
        registry = MLflowPromptRegistry(settings.MLFLOW_TRACKING_URI)
        logger.info(
            "MLflow prompt registry connected: %s", settings.MLFLOW_TRACKING_URI
        )
    except Exception as exc:
        logger.warning("MLflow prompt registry unavailable: %s", exc)

    # 4. Lifecycle manager
    lcm = None
    if registry:
        lcm = PromptLifecycleManager(registry, lifecycle_producer)

    # 5. Health checker
    checker = HealthChecker(redis_client=redis_client)

    # 6. Assign to routes module
    from app.api import routes

    routes.health_checker = checker
    routes.mlflow_registry = registry
    routes.lifecycle_manager = lcm

    logger.info(
        "Service initialized — MLflow=%s, Redis=%s, PromptCache=%s, Kafka=%s",
        settings.MLFLOW_TRACKING_URI,
        settings.REDIS_URL,
        settings.PROMPT_CACHE_REDIS_URL,
        settings.KAFKA_BOOTSTRAP_SERVERS or "disabled",
    )
    yield

    # Shutdown
    await lifecycle_producer.stop()
    await trace_producer.stop()
    await audit_producer.stop()
    await prompt_cache.close()
    await redis_manager.close()
    routes.health_checker = None
    routes.lifecycle_manager = None
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
        origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return 400 (not 422) for validation errors with corrective messages."""
    errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"] if loc != "body")
        errors.append({"field": field, "message": error["msg"]})
    return JSONResponse(
        status_code=400,
        content={"detail": "Validation error", "errors": errors},
    )


app.include_router(router)
