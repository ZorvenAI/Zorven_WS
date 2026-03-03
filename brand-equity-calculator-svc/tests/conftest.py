"""Shared test fixtures."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.api import routes
from app.main import app
from app.services.brand_equity_executor import BrandEquityExecutor


@pytest.fixture
async def client():
    """Test client with executor in no-Claude mode (returns 503)."""
    executor = BrandEquityExecutor()
    routes.executor = executor
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    routes.executor = None


@pytest.fixture
def valid_payload() -> dict:
    return {
        "company_name": "Acme Corp",
        "address": "San Francisco, CA",
        "website": "https://acme.example.com",
        "industry_type": "Technology",
        "business_size": "medium",
        "scope": "national",
    }
