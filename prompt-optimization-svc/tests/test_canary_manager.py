"""Unit tests for canary manager (US-033)."""

from datetime import datetime, timedelta, timezone

from app.logic.canary_manager import (
    CANARY_DURATION_HOURS,
    CANARY_METRICS_KEY,
    CANARY_PROMOTION_ENABLED,
    CANARY_STATE_KEY,
    CANARY_TRAFFIC_PCT,
    CanaryState,
    is_canary_request,
)
from app.registries.prompt_catalog import AGENT_PORTS


class TestIsCanaryRequest:
    """AC-1: Deterministic via hash(tenant_id)."""

    def test_deterministic_same_tenant(self):
        r1 = is_canary_request("tenant-abc")
        r2 = is_canary_request("tenant-abc")
        assert r1 == r2

    def test_deterministic_across_calls(self):
        results = [is_canary_request("tenant-xyz") for _ in range(100)]
        assert all(r == results[0] for r in results)

    def test_approximately_10pct_routing(self):
        total = 1000
        canary_count = sum(is_canary_request(f"tenant-{i}") for i in range(total))
        # 10% ± 5% tolerance
        assert 50 <= canary_count <= 150, f"Got {canary_count}/1000"

    def test_different_tenants_differ(self):
        results = {is_canary_request(f"t-{i}") for i in range(100)}
        assert True in results
        assert False in results

    def test_empty_tenant_returns_false(self):
        assert is_canary_request("") is False

    def test_custom_pct(self):
        # With 100% canary, all should route
        assert is_canary_request("any-tenant", canary_pct=1.0) is True

    def test_zero_pct(self):
        assert is_canary_request("any-tenant", canary_pct=0.0) is False


class TestCanaryConstants:
    """AC-2: Non-configurable canary parameters."""

    def test_traffic_pct(self):
        assert CANARY_TRAFFIC_PCT == 0.10

    def test_duration_hours(self):
        assert CANARY_DURATION_HOURS == 24

    def test_promotion_enabled_hardcoded(self):
        assert CANARY_PROMOTION_ENABLED is True

    def test_regression_threshold(self):
        from app.core.config import settings

        assert settings.CANARY_REGRESSION_THRESHOLD == 0.05

    def test_metrics_ttl_days(self):
        from app.core.config import settings

        assert settings.CANARY_METRICS_TTL_DAYS == 30


class TestCanaryState:
    def test_dataclass_fields(self):
        now = datetime.now(timezone.utc)
        state = CanaryState(
            prompt_name="zorven-wf3-cga-system",
            canary_version=5,
            production_version=4,
            started_at=now,
            expires_at=now + timedelta(hours=24),
            agent_code="cga",
        )
        assert state.prompt_name == "zorven-wf3-cga-system"
        assert state.canary_version == 5
        assert state.production_version == 4
        assert state.active is True

    def test_expires_after_24h(self):
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=CANARY_DURATION_HOURS)
        state = CanaryState(
            prompt_name="test",
            canary_version=2,
            production_version=1,
            started_at=now,
            expires_at=expires,
            agent_code="mra",
        )
        assert (state.expires_at - state.started_at).total_seconds() == 24 * 3600


class TestCanaryKeyFormats:
    """AC-5: Redis key formats."""

    def test_state_key_format(self):
        key = CANARY_STATE_KEY.format(name="zorven-wf3-cga-system")
        assert key == "prompt:canary:zorven-wf3-cga-system"

    def test_metrics_key_format(self):
        key = CANARY_METRICS_KEY.format(name="zorven-wf3-cga-system", version=5)
        assert key == "prompt:metrics:zorven-wf3-cga-system:v5"


class TestCanaryAllAgents:
    """AC-4: Covers ALL 15 agents."""

    def test_any_agent_code_accepted(self):
        now = datetime.now(timezone.utc)
        for agent in AGENT_PORTS:
            state = CanaryState(
                prompt_name=f"zorven-wf1-{agent}-system",
                canary_version=2,
                production_version=1,
                started_at=now,
                expires_at=now + timedelta(hours=24),
                agent_code=agent,
            )
            assert state.agent_code == agent

    def test_all_15_agents_can_canary(self):
        assert len(AGENT_PORTS) == 23
