"""Shared test fixtures for the Ad Publishing Agent service."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
def service_token_headers():
    """Auth headers for service-to-service calls."""
    return {"X-Service-Token": "dev-service-token"}


@pytest.fixture
async def async_client():
    """Async HTTP client for testing FastAPI endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def mock_redis():
    """Mock Redis manager with async methods."""
    redis = AsyncMock()
    redis.get_cached_result = AsyncMock(return_value=None)
    redis.cache_result = AsyncMock()
    redis.store_approval_request = AsyncMock()
    redis.get_approval_request = AsyncMock(return_value=None)
    redis.update_approval_request = AsyncMock()
    redis.list_pending_approvals = AsyncMock(return_value=[])
    redis.check_duplicate_campaign = AsyncMock(return_value=False)
    redis.save_campaign_registry = AsyncMock()
    redis.check_rate_limit = AsyncMock(return_value=False)
    return redis


@pytest.fixture
def mock_meta_client():
    """Mock Meta Marketing API client."""
    client = AsyncMock()
    client.validate_account = AsyncMock(
        return_value={
            "token_valid": True,
            "account_status": 1,
            "permissions": ["ads_management", "ads_read"],
            "spending_limit": 100000,
        }
    )
    client.create_campaign = AsyncMock(return_value="campaign_123")
    client.create_ad_set = AsyncMock(return_value="adset_456")
    client.upload_image = AsyncMock(
        return_value={"hash": "abc123", "url": "https://example.com/img.jpg"}
    )
    client.create_ad_creative = AsyncMock(return_value="creative_789")
    client.create_ad = AsyncMock(return_value="ad_101")
    client.update_campaign_status = AsyncMock(return_value=True)
    client.get_ad_preview = AsyncMock(return_value="<iframe>preview</iframe>")
    client.pause_entities = AsyncMock(return_value=[])
    return client


@pytest.fixture
def mock_anthropic():
    """Mock Anthropic client for targeting translation."""
    client = AsyncMock()
    client.messages = AsyncMock()
    client.messages.create = AsyncMock(
        return_value=MagicMock(
            content=[
                MagicMock(
                    text='{"geo_locations": {"countries": ["US"]}, '
                    '"age_min": 25, "age_max": 54, "genders": [1, 2], '
                    '"interests": [{"id": "123", "name": "Technology"}]}'
                )
            ]
        )
    )
    return client


@pytest.fixture
def sample_creative_package():
    """Sample CGA creative package (previous_outputs)."""
    return {
        "creative_generation": {
            "creative_packages": [
                {
                    "ad_set_name": "TOFU - Tech Enthusiasts",
                    "ad_units": [
                        {
                            "variant_label": "A",
                            "image_url": "gs://bucket/img1.jpg",
                            "headline": "Discover Innovation",
                            "primary_text": "Transform your workflow today.",
                            "cta": "LEARN_MORE",
                            "link_url": "https://example.com",
                        }
                    ],
                }
            ],
            "approval_status": "approved",
        }
    }


@pytest.fixture
def sample_campaign_blueprint():
    """Sample CAA campaign blueprint (previous_outputs)."""
    return {
        "campaign_architecture": {
            "campaign_name": "Q2 2026 Brand Awareness",
            "objective": "OUTCOME_AWARENESS",
            "total_budget_usd": 1000.0,
            "duration_days": 30,
            "funnel_stages": [
                {
                    "stage": "TOFU",
                    "budget_pct": 0.5,
                    "audiences": [
                        {
                            "name": "Tech Enthusiasts",
                            "demographics": {
                                "age_min": 25,
                                "age_max": 54,
                                "genders": ["male", "female"],
                                "countries": ["US"],
                            },
                            "interests": ["technology", "software"],
                        }
                    ],
                    "placements": ["FACEBOOK_FEED", "INSTAGRAM_FEED"],
                }
            ],
        }
    }
