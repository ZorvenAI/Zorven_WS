"""Testcontainer fixtures for integration tests (US-059).

Session-scoped fixtures that start Redis, PostgreSQL, Kafka, and MLflow
containers once per pytest session. All integration tests use these
real services — no skip markers needed.

Environment variables POI_* are set before any app imports so that
module-level singletons (database.py engine) bind to container URLs.
"""

import os
import socket
import subprocess
import time

import pytest


def _find_free_port() -> int:
    """Find a free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _wait_for_url(url: str, timeout: int = 30) -> None:
    """Wait for an HTTP endpoint to respond with 200."""
    import httpx

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = httpx.get(url, timeout=3)
            if resp.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise TimeoutError(f"Timed out waiting for {url}")


# ── Redis Container ──


@pytest.fixture(scope="session")
def redis_container():
    """Start a Redis 7 container with 27 databases."""
    from testcontainers.redis import RedisContainer

    with RedisContainer("redis:7-alpine").with_command(
        "redis-server --databases 27"
    ) as redis:
        yield redis


@pytest.fixture(scope="session")
def tc_redis_url(redis_container):
    """Redis URL for prompt cache (DB 2)."""
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    return f"redis://{host}:{port}/2"


@pytest.fixture(scope="session")
def tc_redis_general_url(redis_container):
    """Redis URL for general cache / Celery broker (DB 26)."""
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    return f"redis://{host}:{port}/26"


# ── PostgreSQL Container ──


@pytest.fixture(scope="session")
def postgres_container():
    """Start a PostgreSQL 15 container (mlflow user/db)."""
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer(
        "postgres:15-alpine",
        username="mlflow",
        password="mlflow",
        dbname="mlflow",
    ) as pg:
        yield pg


@pytest.fixture(scope="session")
def tc_postgres_url(postgres_container):
    """PostgreSQL connection URL."""
    return postgres_container.get_connection_url()


# ── Kafka Container ──


@pytest.fixture(scope="session")
def kafka_container():
    """Start a Kafka container (includes built-in KRaft)."""
    from testcontainers.kafka import KafkaContainer

    with KafkaContainer("confluentinc/cp-kafka:7.6.0") as kafka:
        yield kafka


@pytest.fixture(scope="session")
def tc_kafka_bootstrap(kafka_container):
    """Kafka bootstrap server address."""
    return kafka_container.get_bootstrap_server()


# ── MLflow Server (subprocess) ──


@pytest.fixture(scope="session")
def tc_mlflow_uri(tc_postgres_url):
    """Start MLflow tracking server backed by testcontainer PostgreSQL."""
    port = _find_free_port()
    proc = subprocess.Popen(
        [
            "mlflow",
            "server",
            "--backend-store-uri",
            tc_postgres_url,
            "--host",
            "0.0.0.0",
            "--port",
            str(port),
            "--default-artifact-root",
            "/tmp/mlflow-test-artifacts",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    uri = f"http://localhost:{port}"
    try:
        _wait_for_url(f"{uri}/health", timeout=30)
    except TimeoutError:
        proc.terminate()
        raise
    yield uri
    proc.terminate()
    proc.wait(timeout=10)


# ── Alembic Migrations ──


@pytest.fixture(scope="session")
def tc_db_migrated(tc_postgres_url):
    """Run Alembic migrations against testcontainer PostgreSQL."""
    svc_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = os.environ.copy()
    env["POI_DATABASE_URL"] = tc_postgres_url
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=svc_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Alembic migration failed: {result.stderr}")
    return True


# ── Environment Override ──


@pytest.fixture(scope="session", autouse=True)
def tc_override_env(
    tc_redis_url,
    tc_redis_general_url,
    tc_postgres_url,
    tc_kafka_bootstrap,
    tc_mlflow_uri,
    tc_db_migrated,
):
    """Set POI_* env vars to point at testcontainer-managed services.

    This fixture is autouse + session-scoped, so it runs before any
    app imports and lasts for the entire test session.
    """
    originals = {}
    overrides = {
        "POI_PROMPT_CACHE_REDIS_URL": tc_redis_url,
        "POI_REDIS_URL": tc_redis_general_url,
        "POI_DATABASE_URL": tc_postgres_url,
        "POI_KAFKA_BOOTSTRAP_SERVERS": tc_kafka_bootstrap,
        "POI_MLFLOW_TRACKING_URI": tc_mlflow_uri,
        "POI_CELERY_BROKER_URL": tc_redis_general_url,
    }
    for key, val in overrides.items():
        originals[key] = os.environ.get(key)
        os.environ[key] = val

    yield

    for key, orig in originals.items():
        if orig is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = orig
