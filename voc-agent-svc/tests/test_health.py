"""Tests for the health endpoint."""

import pytest


@pytest.mark.unit
async def test_health_returns_ok(client):
    """Health endpoint returns ok status."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "voice-of-customer-agent"


@pytest.mark.unit
async def test_health_no_auth_required(client):
    """Health endpoint does not require authentication."""
    response = await client.get("/health")
    assert response.status_code == 200
