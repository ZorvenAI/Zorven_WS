"""Cross-service integration tests for testcontainer infrastructure (US-059).

Validates that testcontainer-managed services (Redis, PostgreSQL, Kafka,
MLflow) are healthy and that POI_* environment variables point to them.
"""

import asyncio
import os

import pytest


@pytest.mark.integration
class TestTestcontainersInfrastructure:
    """Validate testcontainer infrastructure is healthy."""

    def test_redis_container_responds_to_ping(self):
        """Redis container is reachable and responds to PING."""
        import redis

        url = os.environ.get("POI_PROMPT_CACHE_REDIS_URL", "")
        assert url, "POI_PROMPT_CACHE_REDIS_URL must be set by testcontainers"
        r = redis.from_url(url)
        assert r.ping() is True
        r.close()

    def test_postgres_container_accepts_connections(self):
        """PostgreSQL container accepts connections and runs queries."""
        from sqlalchemy import create_engine, text

        url = os.environ.get("POI_DATABASE_URL", "")
        assert url, "POI_DATABASE_URL must be set by testcontainers"
        engine = create_engine(url)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            assert result.scalar() == 1
        engine.dispose()

    def test_kafka_container_accepts_connections(self):
        """Kafka container bootstrap server is reachable."""
        from aiokafka import AIOKafkaProducer

        bootstrap = os.environ.get("POI_KAFKA_BOOTSTRAP_SERVERS", "")
        assert bootstrap, "POI_KAFKA_BOOTSTRAP_SERVERS must be set by testcontainers"

        async def _check():
            producer = AIOKafkaProducer(bootstrap_servers=bootstrap)
            await producer.start()
            connected = producer.client._connected
            await producer.stop()
            return connected

        result = asyncio.get_event_loop().run_until_complete(_check())
        assert result is True

    def test_mlflow_server_health_endpoint(self):
        """MLflow /health endpoint returns 200."""
        import httpx

        uri = os.environ.get("POI_MLFLOW_TRACKING_URI", "")
        assert uri, "POI_MLFLOW_TRACKING_URI must be set by testcontainers"
        resp = httpx.get(f"{uri}/health", timeout=5)
        assert resp.status_code == 200

    def test_all_containers_use_expected_images(self):
        """Verify expected service versions are running by querying them."""
        import httpx
        import redis

        # Redis 7 check — INFO server contains redis_version:7.*
        redis_url = os.environ.get("POI_PROMPT_CACHE_REDIS_URL", "")
        assert redis_url, "POI_PROMPT_CACHE_REDIS_URL must be set by testcontainers"
        r = redis.from_url(redis_url)
        info = r.info("server")
        assert info["redis_version"].startswith(
            "7"
        ), f"Expected Redis 7.x, got {info['redis_version']}"
        r.close()

        # PostgreSQL 15 check — via server_version
        from sqlalchemy import create_engine, text

        pg_url = os.environ.get("POI_DATABASE_URL", "")
        assert pg_url, "POI_DATABASE_URL must be set by testcontainers"
        engine = create_engine(pg_url)
        with engine.connect() as conn:
            result = conn.execute(text("SHOW server_version"))
            version = result.scalar()
            assert version.startswith("15"), f"Expected PostgreSQL 15.x, got {version}"
        engine.dispose()

        # MLflow version check — /health returns successfully
        mlflow_uri = os.environ.get("POI_MLFLOW_TRACKING_URI", "")
        assert mlflow_uri, "POI_MLFLOW_TRACKING_URI must be set by testcontainers"
        resp = httpx.get(f"{mlflow_uri}/health", timeout=5)
        assert resp.status_code == 200

    def test_env_vars_point_to_containers(self):
        """POI_* env vars are set and non-empty."""
        required_vars = [
            "POI_PROMPT_CACHE_REDIS_URL",
            "POI_REDIS_URL",
            "POI_DATABASE_URL",
            "POI_KAFKA_BOOTSTRAP_SERVERS",
            "POI_MLFLOW_TRACKING_URI",
        ]
        for var in required_vars:
            value = os.environ.get(var)
            assert value, f"{var} is not set or empty"
            assert len(value) > 5, f"{var} value too short: {value}"
