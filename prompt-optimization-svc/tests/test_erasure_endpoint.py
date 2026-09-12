"""M-02 · POI erasure endpoint tests."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def service_token():
    return "test-poi-service-token"


@pytest.fixture
def app_with_token(service_token):
    import os

    os.environ["POI_SERVICE_TOKEN"] = service_token
    os.environ.setdefault("POI_DATABASE_URL", "sqlite:///test.db")
    os.environ.setdefault("POI_MLFLOW_TRACKING_URI", "http://localhost:5000")

    from importlib import reload

    import app.core.config as config_mod

    reload(config_mod)

    from app.auth.deps import verify_service_token  # noqa: F401
    from app.main import app

    return app


@pytest.mark.asyncio
async def test_erasure_rejects_missing_token(app_with_token):
    async with AsyncClient(
        transport=ASGITransport(app=app_with_token),
        base_url="http://test",
    ) as client:
        resp = await client.request(
            "DELETE",
            "/v1/admin/erasure",
            json={"tenant_id": "t", "session_ids": ["s"]},
        )
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_erasure_rejects_wrong_token(app_with_token, service_token):
    async with AsyncClient(
        transport=ASGITransport(app=app_with_token),
        base_url="http://test",
    ) as client:
        resp = await client.request(
            "DELETE",
            "/v1/admin/erasure",
            json={"tenant_id": "t", "session_ids": ["s"]},
            headers={"X-Service-Token": "wrong"},
        )
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_erasure_empty_sessions_returns_zero(app_with_token, service_token):
    async with AsyncClient(
        transport=ASGITransport(app=app_with_token),
        base_url="http://test",
    ) as client:
        resp = await client.request(
            "DELETE",
            "/v1/admin/erasure",
            json={"tenant_id": "t", "session_ids": []},
            headers={"X-Service-Token": service_token},
        )
        assert resp.status_code == 200
        assert resp.json()["deactivated"] == 0
