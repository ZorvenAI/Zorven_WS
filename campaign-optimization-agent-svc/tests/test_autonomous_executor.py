"""Tests for SKL-COA-07: Autonomous executor.

Tests guardrail enforcement blocking execution, daily action limit,
cooldown check, campaign-level always manual, and action types.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.logic.guardrails import GuardrailAction
from app.messaging.event_emitter import EventEmitter, EventType
from app.services.autonomous_executor import AutonomousExecutor
from app.services.meta_management_client import MetaManagementClient
from app.services.optimization_verifier import OptimizationVerifier


@pytest.fixture
def mock_emitter():
    emitter = AsyncMock(spec=EventEmitter)
    emitter.emit = AsyncMock()
    return emitter


@pytest.fixture
def mock_verifier():
    v = AsyncMock(spec=OptimizationVerifier)
    v.verify_action = AsyncMock(return_value={"verified": True})
    return v


@pytest.fixture
def executor(mock_meta_client, mock_verifier, mock_emitter, mock_redis):
    return AutonomousExecutor(
        meta_client=mock_meta_client,
        verifier=mock_verifier,
        event_emitter=mock_emitter,
        redis_manager=mock_redis,
    )


@pytest.fixture
def mock_camp():
    """Campaign with multiple optimizations (passes PG-10)."""
    camp = MagicMock()
    camp.campaign_id = "camp_001"
    camp.tenant_id = "tenant_001"
    camp.meta_access_token = "token_abc"
    camp.active_ad_set_count = 3
    camp.optimization_count = 5
    return camp


def _make_rec(action_type="pause", entity_type="ad_set", entity_id="adset_001", **kw):
    rec = {
        "recommendation_id": "rec_001",
        "action_type": action_type,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "current_values": kw.get("current_values", {"status": "ACTIVE"}),
        "proposed_values": kw.get("proposed_values", {"status": "PAUSED"}),
        "reason": kw.get("reason", ""),
        "requires_approval": True,
    }
    rec.update(kw)
    return rec


# ── Guardrail Blocking ──────────────────────────────────────────


class TestGuardrailBlocking:
    @pytest.mark.asyncio
    async def test_campaign_level_blocked_by_pg03(
        self, executor, mock_camp
    ):
        """Campaign-level action is blocked by PG-03 and queued for approval."""
        rec = _make_rec(
            entity_type="campaign",
            proposed_values={"status": "PAUSED"},
        )
        results = await executor.execute_autonomous(
            mock_camp, [rec], {}
        )
        assert len(results) == 1
        assert results[0]["status"] == "awaiting_approval"
        assert results[0]["executed"] is False
        assert "PG-03" in results[0]["guardrails"]

    @pytest.mark.asyncio
    async def test_first_optimization_blocked_by_pg10(
        self, mock_meta_client, mock_verifier, mock_emitter, mock_redis
    ):
        """First optimization (optimization_count=0) blocked by PG-10."""
        camp = MagicMock()
        camp.campaign_id = "camp_001"
        camp.tenant_id = "tenant_001"
        camp.meta_access_token = "token"
        camp.active_ad_set_count = 3
        camp.optimization_count = 0

        executor = AutonomousExecutor(
            meta_client=mock_meta_client,
            verifier=mock_verifier,
            event_emitter=mock_emitter,
            redis_manager=mock_redis,
        )
        rec = _make_rec()
        results = await executor.execute_autonomous(camp, [rec], {})
        assert results[0]["status"] == "awaiting_approval"
        assert "PG-10" in results[0]["guardrails"]

    @pytest.mark.asyncio
    async def test_last_ad_set_pause_blocked_by_pg04(
        self, mock_meta_client, mock_verifier, mock_emitter, mock_redis
    ):
        """Cannot pause last active ad set (PG-04)."""
        camp = MagicMock()
        camp.campaign_id = "camp_001"
        camp.tenant_id = "tenant_001"
        camp.meta_access_token = "token"
        camp.active_ad_set_count = 1
        camp.optimization_count = 5

        executor = AutonomousExecutor(
            meta_client=mock_meta_client,
            verifier=mock_verifier,
            event_emitter=mock_emitter,
            redis_manager=mock_redis,
        )
        rec = _make_rec(action_type="pause")
        results = await executor.execute_autonomous(camp, [rec], {})
        assert results[0]["status"] == "awaiting_approval"
        assert "PG-04" in results[0]["guardrails"]

    @pytest.mark.asyncio
    async def test_high_budget_blocked_by_pg02(self, executor, mock_camp):
        """Budget above approval threshold blocked by PG-02."""
        rec = _make_rec(
            action_type="adjust_budget",
            current_values={"daily_budget": 400},
            proposed_values={"daily_budget": 600},
        )
        results = await executor.execute_autonomous(
            mock_camp, [rec], {}
        )
        assert results[0]["status"] == "awaiting_approval"
        assert "PG-02" in results[0]["guardrails"]


# ── Successful Execution ─────────────────────────────────────────


class TestSuccessfulExecution:
    @pytest.mark.asyncio
    async def test_pause_executes_successfully(
        self, executor, mock_camp, mock_meta_client, mock_redis
    ):
        """Pause action calls update_ad_set_status and verifies."""
        rec = _make_rec(
            action_type="pause",
            proposed_values={"status": "PAUSED"},
        )
        results = await executor.execute_autonomous(
            mock_camp, [rec], {}
        )
        assert results[0]["status"] == "executed"
        assert results[0]["executed"] is True
        mock_meta_client.update_ad_set_status.assert_called_once()
        mock_redis.increment_action_counter.assert_called_once()

    @pytest.mark.asyncio
    async def test_scale_executes_budget_update(
        self, executor, mock_camp, mock_meta_client
    ):
        """Scale action calls update_ad_set_budget."""
        rec = _make_rec(
            action_type="scale",
            current_values={"daily_budget": 100},
            proposed_values={"budget_increase_pct": 20},
        )
        results = await executor.execute_autonomous(
            mock_camp, [rec], {}
        )
        assert results[0]["executed"] is True
        mock_meta_client.update_ad_set_budget.assert_called_once()

    @pytest.mark.asyncio
    async def test_adjust_budget_action(
        self, executor, mock_camp, mock_meta_client
    ):
        """adjust_budget action passes correct budget to Meta API."""
        rec = _make_rec(
            action_type="adjust_budget",
            current_values={"daily_budget": 100},
            proposed_values={"daily_budget": 120},
        )
        results = await executor.execute_autonomous(
            mock_camp, [rec], {}
        )
        assert results[0]["executed"] is True
        call = mock_meta_client.update_ad_set_budget.call_args
        assert call[1]["daily_budget_cents"] == 12000  # 120 * 100

    @pytest.mark.asyncio
    async def test_creative_refresh_emits_event(
        self, executor, mock_camp, mock_emitter
    ):
        """creative_refresh emits CREATIVE_REFRESH_REQUESTED event."""
        rec = _make_rec(
            action_type="creative_refresh",
            entity_type="ad",
            entity_id="ad_001",
            proposed_values={"action": "request_creative_refresh"},
            reason="creative_fatigue",
        )
        results = await executor.execute_autonomous(
            mock_camp, [rec], {}
        )
        assert results[0]["executed"] is True
        # Check that CREATIVE_REFRESH_REQUESTED was emitted
        emit_calls = mock_emitter.emit.call_args_list
        event_types = [call[0][0] for call in emit_calls]
        assert EventType.CREATIVE_REFRESH_REQUESTED in event_types


# ── Error Handling ───────────────────────────────────────────────


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_meta_api_failure_returns_failed(
        self, mock_verifier, mock_emitter, mock_redis, mock_camp
    ):
        """Meta API error results in failed status."""
        meta = AsyncMock()
        meta.update_ad_set_status = AsyncMock(
            side_effect=Exception("Meta API error")
        )
        executor = AutonomousExecutor(
            meta_client=meta,
            verifier=mock_verifier,
            event_emitter=mock_emitter,
            redis_manager=mock_redis,
        )
        rec = _make_rec()
        results = await executor.execute_autonomous(
            mock_camp, [rec], {}
        )
        assert results[0]["status"] == "failed"
        assert results[0]["executed"] is False
        assert "Meta API error" in results[0]["error"]


# ── Guardrail Event Emission ─────────────────────────────────────


class TestGuardrailEventEmission:
    @pytest.mark.asyncio
    async def test_guardrail_triggered_event(
        self, executor, mock_camp, mock_emitter
    ):
        """Blocked recommendation emits GUARDRAIL_TRIGGERED event."""
        rec = _make_rec(entity_type="campaign")
        await executor.execute_autonomous(mock_camp, [rec], {})
        emit_calls = mock_emitter.emit.call_args_list
        event_types = [call[0][0] for call in emit_calls]
        assert EventType.GUARDRAIL_TRIGGERED in event_types

    @pytest.mark.asyncio
    async def test_auto_executed_event(
        self, executor, mock_camp, mock_emitter
    ):
        """Successfully executed action emits ACTION_AUTO_EXECUTED event."""
        rec = _make_rec(action_type="pause", proposed_values={"status": "PAUSED"})
        await executor.execute_autonomous(mock_camp, [rec], {})
        emit_calls = mock_emitter.emit.call_args_list
        event_types = [call[0][0] for call in emit_calls]
        assert EventType.ACTION_AUTO_EXECUTED in event_types


# ── Redis Tracking ───────────────────────────────────────────────


class TestRedisTracking:
    @pytest.mark.asyncio
    async def test_records_last_action(
        self, executor, mock_camp, mock_redis
    ):
        """Successful execution records last action in Redis."""
        rec = _make_rec(action_type="pause", proposed_values={"status": "PAUSED"})
        await executor.execute_autonomous(mock_camp, [rec], {})
        mock_redis.set_last_action.assert_called_once()
        call_kwargs = mock_redis.set_last_action.call_args[1]
        assert call_kwargs["tenant_id"] == "tenant_001"
        assert call_kwargs["campaign_id"] == "camp_001"
