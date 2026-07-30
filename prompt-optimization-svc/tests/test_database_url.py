"""Tests for get_async_url() query-parameter sanitisation.

Regression coverage for a production failure: POI_DATABASE_URL was pointed at
a Neon endpoint, whose URLs always carry ?sslmode=require&channel_binding=require.
get_async_url() only swapped the driver, so SQLAlchemy forwarded those libpq
params to asyncpg.connect() and every async query failed with

    connect() got an unexpected keyword argument 'sslmode'

The bug was invisible locally because the default URL
(postgresql://mlflow:mlflow@mlflow-db:5432/mlflow) has no query string, and
invisible in migrations because Alembic uses the sync psycopg2 driver.
"""

from urllib.parse import parse_qs, urlsplit

import pytest

from app.models.database import get_async_url

NEON = (
    "postgresql://user:pw@ep-x-pooler.c-2.us-east-2.aws.neon.tech/neondb"
    "?sslmode=require&channel_binding=require"
)


def _params(url):
    return parse_qs(urlsplit(url).query)


@pytest.mark.unit
def test_swaps_driver_to_asyncpg():
    assert get_async_url(NEON).startswith("postgresql+asyncpg://")


@pytest.mark.unit
def test_strips_the_params_asyncpg_rejects():
    """The exact failure: sslmode and channel_binding must not survive."""
    params = _params(get_async_url(NEON))
    assert "sslmode" not in params
    assert "channel_binding" not in params


@pytest.mark.unit
def test_translates_sslmode_require_into_asyncpg_ssl():
    """TLS intent must be preserved, not silently dropped."""
    assert _params(get_async_url(NEON))["ssl"] == ["require"]


@pytest.mark.unit
@pytest.mark.parametrize("mode", ["disable", "allow"])
def test_non_tls_sslmode_does_not_request_ssl(mode):
    url = get_async_url(f"postgresql://u:p@h/db?sslmode={mode}")
    assert "ssl" not in _params(url)


@pytest.mark.unit
@pytest.mark.parametrize("mode", ["require", "verify-ca", "verify-full", "prefer"])
def test_tls_sslmode_variants_request_ssl(mode):
    url = get_async_url(f"postgresql://u:p@h/db?sslmode={mode}")
    assert _params(url)["ssl"] == ["require"]


@pytest.mark.unit
def test_preserves_credentials_host_and_database():
    parts = urlsplit(get_async_url(NEON))
    assert parts.username == "user"
    assert parts.password == "pw"
    assert parts.hostname == "ep-x-pooler.c-2.us-east-2.aws.neon.tech"
    assert parts.path == "/neondb"


@pytest.mark.unit
def test_local_default_url_is_unchanged_apart_from_driver():
    """The docker-compose default has no query string — must stay clean."""
    result = get_async_url("postgresql://mlflow:mlflow@mlflow-db:5432/mlflow")
    assert result == "postgresql+asyncpg://mlflow:mlflow@mlflow-db:5432/mlflow"


@pytest.mark.unit
def test_unknown_but_valid_params_are_kept():
    """Only libpq-specific params are dropped; genuine driver args survive."""
    url = get_async_url(
        "postgresql://u:p@h/db?sslmode=require&prepared_statement_cache_size=0"
    )
    params = _params(url)
    assert params["prepared_statement_cache_size"] == ["0"]
    assert params["ssl"] == ["require"]


@pytest.mark.unit
def test_explicit_ssl_param_is_not_overridden():
    url = get_async_url("postgresql://u:p@h/db?ssl=verify-full&sslmode=require")
    assert _params(url)["ssl"] == ["verify-full"]


@pytest.mark.unit
def test_already_async_url_is_left_alone_but_still_sanitised():
    url = get_async_url("postgresql+asyncpg://u:p@h/db?sslmode=require")
    assert url.startswith("postgresql+asyncpg://")
    assert "sslmode" not in _params(url)


@pytest.mark.unit
def test_non_postgres_url_passes_through():
    assert get_async_url("sqlite+aiosqlite:///./local.db") == (
        "sqlite+aiosqlite:///./local.db"
    )
