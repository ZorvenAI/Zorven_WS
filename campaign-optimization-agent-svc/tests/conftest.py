"""Shared test fixtures for the Campaign Optimization Agent service."""

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
    async with AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        yield client


@pytest.fixture
def mock_redis():
    """Mock Redis manager with async methods."""
    redis = AsyncMock()
    redis.available = True
    redis.connect = AsyncMock()
    redis.close = AsyncMock()
    redis.get_performance_history = AsyncMock(return_value={})
    redis.append_performance_history = AsyncMock()
    redis.set_ctr_peak = AsyncMock()
    redis.get_ctr_peaks = AsyncMock(return_value={})
    redis.set_last_action = AsyncMock()
    redis.get_last_action = AsyncMock(return_value=None)
    redis.store_recommendation = AsyncMock()
    redis.get_recommendations = AsyncMock(return_value=[])
    redis.clear_recommendations = AsyncMock()
    redis.increment_action_counter = AsyncMock(return_value=1)
    redis.get_action_counter = AsyncMock(return_value=0)
    redis.add_spend_milestone = AsyncMock(return_value=True)
    redis.get_spend_milestones = AsyncMock(return_value=set())
    redis.set_hourly_perf = AsyncMock()
    redis.get_hourly_perf = AsyncMock(return_value={})
    redis.set_tenant_config = AsyncMock()
    redis.get_tenant_config = AsyncMock(return_value={})
    redis.set_json = AsyncMock()
    redis.get_json = AsyncMock(return_value=None)
    return redis


@pytest.fixture
def mock_kafka():
    """Mock Kafka producers."""
    trace = AsyncMock()
    trace.start = AsyncMock()
    trace.stop = AsyncMock()
    trace.send_trace = AsyncMock()
    audit = AsyncMock()
    audit.start = AsyncMock()
    audit.stop = AsyncMock()
    audit.send_event = AsyncMock()
    event = AsyncMock()
    event.start = AsyncMock()
    event.stop = AsyncMock()
    event.send_event = AsyncMock()
    return {"trace": trace, "audit": audit, "event": event}


@pytest.fixture
def mock_meta_client():
    """Mock Meta Management API client."""
    client = AsyncMock()
    client.update_ad_set_status = AsyncMock(return_value=True)
    client.update_ad_set_budget = AsyncMock(return_value=True)
    client.update_ad_set_targeting = AsyncMock(return_value=True)
    client.update_campaign_status = AsyncMock(return_value=True)
    client.read_back_entity = AsyncMock(
        return_value={
            "id": "entity_123",
            "status": "ACTIVE",
            "sandbox": True,
        }
    )
    return client


@pytest.fixture
def mock_anthropic():
    """Mock Anthropic client for analysis narratives."""
    client = AsyncMock()
    client.messages = AsyncMock()
    client.messages.create = AsyncMock(
        return_value=MagicMock(
            content=[
                MagicMock(
                    text="Campaign health is GREEN. All metrics within "
                    "acceptable ranges. CTR at 2.5% is above benchmark. "
                    "ROAS of 3.2x indicates strong return on ad spend."
                )
            ]
        )
    )
    return client


@pytest.fixture
def sample_campaign():
    """Sample active campaign for testing."""
    return {
        "campaign_id": "camp_001",
        "tenant_id": "tenant_001",
        "meta_campaign_id": "meta_camp_123",
        "meta_ad_account_id": "act_123456",
        "meta_access_token": "test_token_123",
        "campaign_name": "Q2 2026 Brand Awareness",
        "status": "active",
        "objective": "OUTCOME_AWARENESS",
        "daily_budget": 100.0,
        "total_spend_usd": 500.0,
        "total_impressions": 50000,
        "created_at": "2026-03-01T00:00:00+00:00",
        "last_optimized_at": "",
        "optimization_count": 0,
        "sandbox_mode": True,
        "active_ad_set_count": 3,
        "ad_sets": [],
        "ads": [],
        "targets": {"cpa_target": 25.0, "roas_target": 2.0},
        "daily_action_count": 0,
    }


@pytest.fixture
def sample_insights():
    """Sample campaign insights for testing."""
    from app.services.meta_insights_client import (
        AdInsights,
        AdSetInsights,
        CampaignInsights,
    )

    return CampaignInsights(
        campaign_id="camp_001",
        impressions=50000,
        clicks=1500,
        spend=500.0,
        ctr=3.0,
        cpm=10.0,
        frequency=2.1,
        reach=35000,
        conversions=30,
        cost_per_action=16.67,
        purchase_roas=3.0,
        ad_sets=[
            AdSetInsights(
                ad_set_id="adset_001",
                ad_set_name="TOFU - Tech Enthusiasts",
                impressions=25000,
                clicks=750,
                spend=250.0,
                ctr=3.0,
                cpm=10.0,
                frequency=1.8,
                reach=18000,
                conversions=20,
                cost_per_action=12.5,
                purchase_roas=4.0,
            ),
            AdSetInsights(
                ad_set_id="adset_002",
                ad_set_name="MOFU - Decision Makers",
                impressions=15000,
                clicks=450,
                spend=150.0,
                ctr=3.0,
                cpm=10.0,
                frequency=2.5,
                reach=10000,
                conversions=8,
                cost_per_action=18.75,
                purchase_roas=2.5,
            ),
            AdSetInsights(
                ad_set_id="adset_003",
                ad_set_name="BOFU - Retargeting",
                impressions=10000,
                clicks=300,
                spend=100.0,
                ctr=3.0,
                cpm=10.0,
                frequency=3.2,
                reach=7000,
                conversions=2,
                cost_per_action=50.0,
                purchase_roas=1.0,
            ),
        ],
        ads=[
            AdInsights(
                ad_id="ad_001",
                ad_name="Ad 1",
                ad_set_id="adset_001",
                impressions=12000,
                clicks=400,
                spend=120.0,
                ctr=3.33,
                frequency=1.5,
            ),
            AdInsights(
                ad_id="ad_002",
                ad_name="Ad 2",
                ad_set_id="adset_001",
                impressions=13000,
                clicks=350,
                spend=130.0,
                ctr=2.69,
                frequency=2.0,
            ),
            AdInsights(
                ad_id="ad_003",
                ad_name="Ad 3",
                ad_set_id="adset_002",
                impressions=15000,
                clicks=450,
                spend=150.0,
                ctr=3.0,
                frequency=2.5,
            ),
        ],
        date_start="2026-03-29",
        date_stop="2026-04-05",
    )


@pytest.fixture
def sample_analysis():
    """Sample campaign analysis for testing."""
    from app.services.performance_analyzer import (
        AdSetAnalysis,
        CampaignAnalysis,
    )

    return CampaignAnalysis(
        campaign_id="camp_001",
        overall_health="YELLOW",
        ad_set_analyses=[
            AdSetAnalysis(
                ad_set_id="adset_001",
                ad_set_name="TOFU - Tech Enthusiasts",
                cpa_status="SCALE",
                cpa_actual=12.5,
                cpa_target=25.0,
                roas_status="SCALE",
                roas_actual=4.0,
                roas_target=2.0,
                overall_health="GREEN",
            ),
            AdSetAnalysis(
                ad_set_id="adset_002",
                ad_set_name="MOFU - Decision Makers",
                cpa_status="OK",
                cpa_actual=18.75,
                cpa_target=25.0,
                overall_health="GREEN",
            ),
            AdSetAnalysis(
                ad_set_id="adset_003",
                ad_set_name="BOFU - Retargeting",
                cpa_status="KILL",
                cpa_actual=50.0,
                cpa_target=25.0,
                frequency_status="HIGH",
                frequency=3.2,
                overall_health="RED",
            ),
        ],
        red_count=1,
        yellow_count=0,
        green_count=2,
    )
