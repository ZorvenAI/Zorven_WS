"""Hypothesis property tests for canary manager (US-033)."""

from datetime import datetime, timedelta, timezone

from hypothesis import given, settings
from hypothesis import strategies as st

from app.logic.canary_manager import (
    CANARY_DURATION_HOURS,
    CanaryState,
    is_canary_request,
)


class TestIsCanaryRequestProperties:
    @given(st.text(min_size=1, max_size=50))
    @settings(max_examples=100, deadline=None)
    def test_deterministic(self, tenant_id):
        r1 = is_canary_request(tenant_id)
        r2 = is_canary_request(tenant_id)
        assert r1 == r2

    @given(st.text(min_size=1, max_size=50))
    @settings(max_examples=100, deadline=None)
    def test_returns_bool(self, tenant_id):
        result = is_canary_request(tenant_id)
        assert isinstance(result, bool)

    def test_distribution_approximately_10pct(self):
        total = 5000
        canary = sum(is_canary_request(f"t-{i}") for i in range(total))
        pct = canary / total
        assert 0.05 <= pct <= 0.15, f"Canary rate {pct:.1%} outside [5%, 15%]"


class TestCanaryStateProperties:
    @given(
        st.text(min_size=1, max_size=30),
        st.integers(min_value=1, max_value=100),
        st.integers(min_value=1, max_value=100),
        st.text(min_size=1, max_size=10),
    )
    @settings(max_examples=30, deadline=None)
    def test_expires_after_started(self, name, cv, pv, agent):
        now = datetime.now(timezone.utc)
        state = CanaryState(
            prompt_name=name,
            canary_version=cv,
            production_version=pv,
            started_at=now,
            expires_at=now + timedelta(hours=CANARY_DURATION_HOURS),
            agent_code=agent,
        )
        assert state.expires_at > state.started_at
