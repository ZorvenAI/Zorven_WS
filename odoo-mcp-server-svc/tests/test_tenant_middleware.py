"""Tests for tenant middleware — dependency injection, 401/403 responses."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, Depends
from httpx import ASGITransport, AsyncClient

from app.services.errors import (
    OdooAuthenticationError,
    OdooAccessError,
    TenantNotFoundError,
)
from app.tenancy.middleware import get_tenant_context, tenant_resolver
from app.tenancy.models import TenantConfig, TenantContext

# ── Fixtures ──


@pytest.fixture
def sample_context():
    """A fully authenticated tenant context."""
    config = TenantConfig(
        tenant_id="test-tenant",
        odoo_url="https://test.odoo.com",
        odoo_db="test_db",
    )
    return TenantContext(
        config=config,
        odoo_uid=42,
        company_id=1,
        authenticated=True,
    )


@pytest.fixture
def test_app():
    """Minimal FastAPI app with a route that uses the tenant dependency."""
    app = FastAPI()

    @app.get("/protected")
    async def protected(ctx: TenantContext = Depends(get_tenant_context)):
        return {
            "tenant_id": ctx.config.tenant_id,
            "uid": ctx.odoo_uid,
            "authenticated": ctx.authenticated,
        }

    return app


@pytest.fixture
async def client(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Happy path ──


async def test_tenant_context_resolved(client, sample_context):
    """Successful tenant resolution returns context in the route."""
    mock_resolver = AsyncMock()
    mock_resolver.resolve = AsyncMock(return_value=sample_context)

    with patch("app.tenancy.middleware.tenant_resolver", mock_resolver):
        resp = await client.get("/protected", headers={"X-Tenant-ID": "test-tenant"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["tenant_id"] == "test-tenant"
    assert body["uid"] == 42
    assert body["authenticated"] is True
    mock_resolver.resolve.assert_called_once_with("test-tenant")


async def test_default_tenant_when_no_header(client, sample_context):
    """Missing X-Tenant-ID header defaults to 'default'."""
    mock_resolver = AsyncMock()
    mock_resolver.resolve = AsyncMock(return_value=sample_context)

    with patch("app.tenancy.middleware.tenant_resolver", mock_resolver):
        resp = await client.get("/protected")

    assert resp.status_code == 200
    mock_resolver.resolve.assert_called_once_with("default")


# ── Error: resolver not initialised ──


async def test_500_when_resolver_not_initialised(client):
    """Returns 500 if lifespan has not set up the resolver."""
    with patch("app.tenancy.middleware.tenant_resolver", None):
        resp = await client.get("/protected")

    assert resp.status_code == 500
    assert "not initialised" in resp.json()["detail"]


# ── Error: tenant not found ──


async def test_401_on_tenant_not_found(client):
    """Returns 401 when tenant is not in the registry."""
    mock_resolver = AsyncMock()
    mock_resolver.resolve = AsyncMock(
        side_effect=TenantNotFoundError("Tenant 'ghost' is not registered")
    )

    with patch("app.tenancy.middleware.tenant_resolver", mock_resolver):
        resp = await client.get("/protected", headers={"X-Tenant-ID": "ghost"})

    assert resp.status_code == 401
    assert "not found" in resp.json()["detail"]


# ── Error: authentication failure ──


async def test_401_on_auth_failure(client):
    """Returns 401 when Odoo authentication fails."""
    mock_resolver = AsyncMock()
    mock_resolver.resolve = AsyncMock(
        side_effect=OdooAuthenticationError("Invalid credentials")
    )

    with patch("app.tenancy.middleware.tenant_resolver", mock_resolver):
        resp = await client.get("/protected", headers={"X-Tenant-ID": "bad-creds"})

    assert resp.status_code == 401
    assert "Authentication failed" in resp.json()["detail"]


# ── Error: access denied ──


async def test_403_on_access_denied(client):
    """Returns 403 when tenant lacks required access."""
    mock_resolver = AsyncMock()
    mock_resolver.resolve = AsyncMock(
        side_effect=OdooAccessError("Insufficient permissions")
    )

    with patch("app.tenancy.middleware.tenant_resolver", mock_resolver):
        resp = await client.get("/protected", headers={"X-Tenant-ID": "restricted"})

    assert resp.status_code == 403
    assert "Access denied" in resp.json()["detail"]


# ── Error: unexpected exception ──


async def test_500_on_unexpected_error(client):
    """Returns 500 for unrecognised errors during resolution."""
    mock_resolver = AsyncMock()
    mock_resolver.resolve = AsyncMock(side_effect=RuntimeError("something broke"))

    with patch("app.tenancy.middleware.tenant_resolver", mock_resolver):
        resp = await client.get("/protected", headers={"X-Tenant-ID": "boom"})

    assert resp.status_code == 500
    assert "Internal error" in resp.json()["detail"]
