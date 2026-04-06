"""Tests for FastAPI routes (/health, /v1/* endpoints).

Covers auth (missing/invalid X-Service-Token), approval endpoints,
performance retrieval, and manual tick triggering.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── Health endpoint ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health_returns_ok(async_client):
    """GET /health returns 200 with service info."""
    with patch("app.api.routes.celery_app", create=True) as mock_celery:
        mock_inspect = MagicMock()
        mock_inspect.ping.return_value = {"worker1": {"ok": "pong"}}
        mock_celery.control.inspect.return_value = mock_inspect

        resp = await async_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "campaign-optimization-agent"
        assert data["version"] == "1.0.0"


@pytest.mark.asyncio
async def test_health_no_auth_required(async_client):
    """GET /health does not require X-Service-Token."""
    resp = await async_client.get("/health")
    assert resp.status_code == 200


# ── Auth enforcement ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_service_token_returns_422(async_client):
    """Endpoints requiring auth return 422 when header missing."""
    resp = await async_client.get("/v1/campaigns/camp_001/recommendations")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_invalid_service_token_returns_403(async_client):
    """Endpoints requiring auth return 403 for wrong token."""
    resp = await async_client.get(
        "/v1/campaigns/camp_001/recommendations",
        headers={"X-Service-Token": "wrong-token"},
    )
    assert resp.status_code == 403


# ── Recommendations endpoint ─────────────────────────────────────


@pytest.mark.asyncio
async def test_list_recommendations_empty(async_client, service_token_headers):
    """GET /v1/campaigns/{id}/recommendations returns empty when no handler."""
    resp = await async_client.get(
        "/v1/campaigns/camp_001/recommendations",
        headers=service_token_headers,
    )
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_recommendations_with_handler(async_client, service_token_headers):
    """GET /v1/campaigns/{id}/recommendations returns recs from handler."""
    mock_handler = AsyncMock()
    mock_handler.list_pending_recommendations = AsyncMock(
        return_value=[
            {
                "recommendation_id": "rec_001",
                "campaign_id": "camp_001",
                "action_type": "pause",
                "entity_type": "ad_set",
                "entity_id": "adset_003",
                "priority": "high",
                "status": "pending",
            }
        ]
    )
    from app.main import app

    app.state.approval_handler = mock_handler
    try:
        resp = await async_client.get(
            "/v1/campaigns/camp_001/recommendations",
            headers=service_token_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["recommendation_id"] == "rec_001"
    finally:
        app.state.approval_handler = None


# ── Approve endpoint ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_approve_no_handler(async_client, service_token_headers):
    """POST /v1/recommendations/{id}/approve returns error when no handler."""
    resp = await async_client.post(
        "/v1/recommendations/rec_001/approve",
        headers=service_token_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"
    assert data["recommendation_id"] == "rec_001"


@pytest.mark.asyncio
async def test_approve_success(async_client, service_token_headers):
    """POST /v1/recommendations/{id}/approve calls handler and returns result."""
    mock_handler = AsyncMock()
    mock_handler.approve_recommendation = AsyncMock(
        return_value={"status": "approved", "executed": True}
    )
    from app.main import app

    app.state.approval_handler = mock_handler
    try:
        resp = await async_client.post(
            "/v1/recommendations/rec_001/approve",
            headers=service_token_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "approved"
        assert data["executed"] is True
    finally:
        app.state.approval_handler = None


# ── Reject endpoint ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reject_no_handler(async_client, service_token_headers):
    """POST /v1/recommendations/{id}/reject returns error when no handler."""
    resp = await async_client.post(
        "/v1/recommendations/rec_001/reject",
        headers=service_token_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"


@pytest.mark.asyncio
async def test_reject_with_feedback(async_client, service_token_headers):
    """POST /v1/recommendations/{id}/reject passes feedback to handler."""
    mock_handler = AsyncMock()
    mock_handler.reject_recommendation = AsyncMock(
        return_value={"status": "rejected"}
    )
    from app.main import app

    app.state.approval_handler = mock_handler
    try:
        resp = await async_client.post(
            "/v1/recommendations/rec_001/reject",
            headers=service_token_headers,
            json={
                "recommendation_id": "rec_001",
                "decision": "reject",
                "feedback": "Too aggressive",
                "approved_by": "admin@test.com",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "rejected"
        mock_handler.reject_recommendation.assert_called_once()
        call_kwargs = mock_handler.reject_recommendation.call_args[1]
        assert call_kwargs["reason"] == "Too aggressive"
    finally:
        app.state.approval_handler = None


# ── Batch approve ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_batch_approve_no_handler(async_client, service_token_headers):
    """POST /v1/recommendations/batch-approve returns empty when no handler."""
    resp = await async_client.post(
        "/v1/recommendations/batch-approve",
        headers=service_token_headers,
        json={"campaign_id": "camp_001", "tenant_id": "tenant_001"},
    )
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_batch_approve_success(async_client, service_token_headers):
    """POST /v1/recommendations/batch-approve returns results from handler."""
    mock_handler = AsyncMock()
    mock_handler.batch_approve = AsyncMock(
        return_value=[
            {"recommendation_id": "rec_001", "status": "approved", "executed": True},
            {"recommendation_id": "rec_002", "status": "approved", "executed": True},
        ]
    )
    from app.main import app

    app.state.approval_handler = mock_handler
    try:
        resp = await async_client.post(
            "/v1/recommendations/batch-approve",
            headers=service_token_headers,
            json={"campaign_id": "camp_001", "tenant_id": "tenant_001"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
    finally:
        app.state.approval_handler = None


# ── Performance endpoint ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_performance_no_redis(async_client, service_token_headers):
    """GET /v1/campaigns/{id}/performance returns empty when no redis."""
    resp = await async_client.get(
        "/v1/campaigns/camp_001/performance",
        headers=service_token_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["campaign_id"] == "camp_001"


@pytest.mark.asyncio
async def test_performance_with_redis(async_client, service_token_headers, mock_redis):
    """GET /v1/campaigns/{id}/performance returns metrics from Redis."""
    mock_redis.get_performance_history = AsyncMock(
        return_value={
            "metrics": {"ctr": 2.5, "roas": 3.0},
            "health": "GREEN",
            "trends": {"ctr": "improving"},
        }
    )
    from app.main import app

    app.state.redis_manager = mock_redis
    try:
        resp = await async_client.get(
            "/v1/campaigns/camp_001/performance",
            headers=service_token_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["health"] == "GREEN"
        assert data["metrics"]["ctr"] == 2.5
    finally:
        app.state.redis_manager = None


# ── Tick trigger endpoint ────────────────────────────────────────


@pytest.mark.asyncio
async def test_tick_trigger_requires_auth(async_client):
    """POST /v1/tick/trigger requires X-Service-Token."""
    resp = await async_client.post("/v1/tick/trigger")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_tick_trigger_success(async_client, service_token_headers):
    """POST /v1/tick/trigger dispatches Celery task and returns tick_id."""
    mock_task = MagicMock()
    mock_task.id = "task_abc123"

    with patch("app.tasks.run_optimization_tick") as mock_fn:
        mock_fn.delay.return_value = mock_task
        resp = await async_client.post(
            "/v1/tick/trigger",
            headers=service_token_headers,
            json={"campaign_age_min_days": 7, "campaign_age_max_days": 30},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tick_id"] == "task_abc123"
        mock_fn.delay.assert_called_once_with(
            campaign_age_min_days=7, campaign_age_max_days=30
        )


# ── Modify endpoint ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_modify_no_handler(async_client, service_token_headers):
    """POST /v1/recommendations/{id}/modify returns error when no handler."""
    resp = await async_client.post(
        "/v1/recommendations/rec_001/modify",
        headers=service_token_headers,
        json={
            "recommendation_id": "rec_001",
            "decision": "modify",
            "modified_values": {"daily_budget": 100.0},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"
