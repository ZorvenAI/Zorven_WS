"""Hypothesis property tests for rollback manager (US-035)."""

from datetime import datetime, timedelta, timezone

from hypothesis import given, settings
from hypothesis import strategies as st

from app.logic.rollback_manager import (
    ARCHIVE_RETENTION_DAYS,
    RollbackResult,
    is_within_retention_window,
)


class TestRetentionWindowProperties:
    @given(st.integers(min_value=0, max_value=29))
    @settings(max_examples=30, deadline=None)
    def test_recent_always_within_window(self, days_ago):
        ts = datetime.now(timezone.utc) - timedelta(days=days_ago)
        assert is_within_retention_window(ts) is True

    @given(st.integers(min_value=31, max_value=365))
    @settings(max_examples=30, deadline=None)
    def test_old_always_outside_window(self, days_ago):
        ts = datetime.now(timezone.utc) - timedelta(days=days_ago)
        assert is_within_retention_window(ts) is False


class TestRollbackResultProperties:
    @given(
        st.text(min_size=1, max_size=30),
        st.integers(min_value=1, max_value=100),
        st.integers(min_value=1, max_value=100),
    )
    @settings(max_examples=30, deadline=None)
    def test_fields_always_valid(self, name, old_v, new_v):
        r = RollbackResult(
            prompt_name=name,
            rolled_back_version=old_v,
            restored_version=new_v,
        )
        assert isinstance(r.success, bool)
        assert isinstance(r.cache_invalidated, bool)
        assert isinstance(r.error, str)


class TestRetentionConstant:
    def test_positive_integer(self):
        assert isinstance(ARCHIVE_RETENTION_DAYS, int)
        assert ARCHIVE_RETENTION_DAYS > 0
