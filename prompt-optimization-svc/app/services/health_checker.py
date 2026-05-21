"""Multi-dependency health checker for prompt-optimization-svc."""

import asyncio
import logging
import time
from typing import Optional

import httpx
import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.api.schemas import DependencyStatus, HealthResponse
from app.core.config import settings

logger = logging.getLogger(__name__)


class HealthChecker:
    """Checks MLflow, Redis, Kafka, and PostgreSQL connectivity."""

    def __init__(
        self,
        redis_client: Optional[aioredis.Redis] = None,
    ) -> None:
        self._redis = redis_client

    async def check_mlflow(self) -> DependencyStatus:
        """Verify MLflow tracking server is reachable."""
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{settings.MLFLOW_TRACKING_URI}/health")
                latency = (time.monotonic() - start) * 1000
                if resp.status_code == 200:
                    return DependencyStatus(
                        name="mlflow", status="up", latency_ms=round(latency, 1)
                    )
                return DependencyStatus(
                    name="mlflow",
                    status="down",
                    latency_ms=round(latency, 1),
                    message=f"HTTP {resp.status_code}",
                )
        except Exception as exc:
            latency = (time.monotonic() - start) * 1000
            return DependencyStatus(
                name="mlflow",
                status="down",
                latency_ms=round(latency, 1),
                message=str(exc),
            )

    async def check_redis(self) -> DependencyStatus:
        """Verify Redis is reachable."""
        start = time.monotonic()
        try:
            if self._redis is None:
                self._redis = aioredis.from_url(
                    settings.REDIS_URL, decode_responses=True
                )
            pong = await self._redis.ping()
            latency = (time.monotonic() - start) * 1000
            if pong:
                return DependencyStatus(
                    name="redis", status="up", latency_ms=round(latency, 1)
                )
            return DependencyStatus(name="redis", status="down")
        except Exception as exc:
            latency = (time.monotonic() - start) * 1000
            return DependencyStatus(
                name="redis",
                status="down",
                latency_ms=round(latency, 1),
                message=str(exc),
            )

    async def check_kafka(self) -> DependencyStatus:
        """Verify Kafka bootstrap servers are reachable."""
        if not settings.KAFKA_BOOTSTRAP_SERVERS:
            return DependencyStatus(name="kafka", status="disabled")

        start = time.monotonic()
        try:
            from aiokafka import AIOKafkaProducer

            producer = AIOKafkaProducer(
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                request_timeout_ms=5000,
            )
            await producer.start()
            await producer.stop()
            latency = (time.monotonic() - start) * 1000
            return DependencyStatus(
                name="kafka", status="up", latency_ms=round(latency, 1)
            )
        except Exception as exc:
            latency = (time.monotonic() - start) * 1000
            return DependencyStatus(
                name="kafka",
                status="down",
                latency_ms=round(latency, 1),
                message=str(exc),
            )

    async def check_postgres(self) -> DependencyStatus:
        """Verify PostgreSQL is reachable."""
        start = time.monotonic()
        try:
            # Convert sync URL to async (postgresql:// → postgresql+asyncpg://)
            db_url = settings.DATABASE_URL
            if db_url.startswith("postgresql://"):
                db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

            engine = create_async_engine(db_url, pool_pre_ping=True)
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            await engine.dispose()
            latency = (time.monotonic() - start) * 1000
            return DependencyStatus(
                name="postgres", status="up", latency_ms=round(latency, 1)
            )
        except Exception as exc:
            latency = (time.monotonic() - start) * 1000
            return DependencyStatus(
                name="postgres",
                status="down",
                latency_ms=round(latency, 1),
                message=str(exc),
            )

    async def check_all(self) -> HealthResponse:
        """Run all dependency checks concurrently and return aggregate status."""
        deps = list(await asyncio.gather(
            self.check_mlflow(),
            self.check_redis(),
            self.check_kafka(),
            self.check_postgres(),
        ))

        down_required = [
            d for d in deps if d.status == "down" and d.name in ("mlflow", "redis")
        ]
        down_optional = [
            d
            for d in deps
            if d.status == "down" and d.name in ("kafka", "postgres")
        ]

        if down_required:
            status = "unhealthy"
        elif down_optional:
            status = "degraded"
        else:
            status = "healthy"

        return HealthResponse(status=status, dependencies=deps)
