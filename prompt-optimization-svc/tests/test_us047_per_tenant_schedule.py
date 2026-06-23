"""Unit tests for per-tenant WF3 optimization schedule (US-047).

Tests the TenantConfig model, strict validation, schedule priority,
Pydantic field validator, and manager backward compatibility.
"""

from datetime import datetime, timezone

from pydantic import ValidationError

from app.cache.tenant_config import (
    DEFAULT_SCHEDULE,
    VALID_SCHEDULES,
    strict_validate_schedule,
    validate_schedule,
)
from app.models.tenant_config import TenantConfig
from app.tasks.optimize_wf3_pipeline import SCHEDULE_PRIORITY


# ── TenantConfig model ──


class TestTenantConfigModel:
    def test_tablename(self):
        assert TenantConfig.__tablename__ == "tenant_configs"

    def test_schema(self):
        assert TenantConfig.__table_args__["schema"] == "prompt_optimization"

    def test_has_tenant_id_column(self):
        col = TenantConfig.__table__.columns["tenant_id"]
        assert not col.nullable
        assert col.unique

    def test_has_schedule_column(self):
        col = TenantConfig.__table__.columns["wf3_optimization_schedule"]
        assert not col.nullable

    def test_has_timestamps(self):
        cols = TenantConfig.__table__.columns
        assert "created_at" in cols
        assert "updated_at" in cols

    def test_repr(self):
        tc = TenantConfig(tenant_id="t1", wf3_optimization_schedule="monthly")
        assert "t1" in repr(tc)
        assert "monthly" in repr(tc)


# ── strict_validate_schedule ──


class TestStrictValidateSchedule:
    def test_on_demand_valid(self):
        assert strict_validate_schedule("on-demand") == "on-demand"

    def test_biweekly_valid(self):
        assert strict_validate_schedule("biweekly") == "biweekly"

    def test_monthly_valid(self):
        assert strict_validate_schedule("monthly") == "monthly"

    def test_quarterly_valid(self):
        assert strict_validate_schedule("quarterly") == "quarterly"

    def test_invalid_raises(self):
        try:
            strict_validate_schedule("daily")
            assert False, "Expected ValueError"
        except ValueError as exc:
            assert "daily" in str(exc)
            assert "Must be one of" in str(exc)

    def test_empty_raises(self):
        try:
            strict_validate_schedule("")
            assert False, "Expected ValueError"
        except ValueError:
            pass

    def test_case_sensitive_raises(self):
        try:
            strict_validate_schedule("Monthly")
            assert False, "Expected ValueError"
        except ValueError:
            pass

    def test_validate_schedule_falls_back(self):
        """validate_schedule (non-strict) silently falls back to default."""
        assert validate_schedule("daily") == DEFAULT_SCHEDULE

    def test_all_valid_schedules_pass(self):
        for sched in VALID_SCHEDULES:
            assert strict_validate_schedule(sched) == sched


# ── Schedule priority ──


class TestSchedulePriority:
    def test_biweekly_most_aggressive(self):
        assert SCHEDULE_PRIORITY["biweekly"] == 0

    def test_on_demand_least_aggressive(self):
        assert SCHEDULE_PRIORITY["on-demand"] == 3

    def test_all_valid_schedules_have_priority(self):
        for sched in VALID_SCHEDULES:
            assert sched in SCHEDULE_PRIORITY

    def test_biweekly_wins_over_quarterly(self):
        schedules = {"t1": "quarterly", "t2": "biweekly"}
        most_aggressive = min(
            schedules.values(),
            key=lambda s: SCHEDULE_PRIORITY.get(s, 3),
        )
        assert most_aggressive == "biweekly"

    def test_monthly_wins_over_quarterly(self):
        schedules = {"t1": "quarterly", "t2": "monthly"}
        most_aggressive = min(
            schedules.values(),
            key=lambda s: SCHEDULE_PRIORITY.get(s, 3),
        )
        assert most_aggressive == "monthly"

    def test_single_schedule(self):
        schedules = {"t1": "quarterly"}
        most_aggressive = min(
            schedules.values(),
            key=lambda s: SCHEDULE_PRIORITY.get(s, 3),
        )
        assert most_aggressive == "quarterly"

    def test_priority_ordering(self):
        ordered = sorted(SCHEDULE_PRIORITY, key=SCHEDULE_PRIORITY.get)
        assert ordered == ["biweekly", "monthly", "quarterly", "on-demand"]


# ── Pydantic validator (AC-3) ──


class TestPydanticValidator:
    def test_invalid_schedule_raises_validation_error(self):
        from app.api.schemas import TenantConfigUpdateRequest

        try:
            TenantConfigUpdateRequest(wf3_optimization_schedule="daily")
            assert False, "Expected ValidationError"
        except ValidationError as exc:
            assert "daily" in str(exc)

    def test_valid_biweekly_passes(self):
        from app.api.schemas import TenantConfigUpdateRequest

        req = TenantConfigUpdateRequest(wf3_optimization_schedule="biweekly")
        assert req.wf3_optimization_schedule == "biweekly"

    def test_none_passes(self):
        from app.api.schemas import TenantConfigUpdateRequest

        req = TenantConfigUpdateRequest(wf3_optimization_schedule=None)
        assert req.wf3_optimization_schedule is None

    def test_empty_string_raises(self):
        from app.api.schemas import TenantConfigUpdateRequest

        try:
            TenantConfigUpdateRequest(wf3_optimization_schedule="")
            assert False, "Expected ValidationError"
        except ValidationError:
            pass

    def test_all_valid_schedules_pass(self):
        from app.api.schemas import TenantConfigUpdateRequest

        for sched in VALID_SCHEDULES:
            req = TenantConfigUpdateRequest(wf3_optimization_schedule=sched)
            assert req.wf3_optimization_schedule == sched

    def test_omitted_field_passes(self):
        from app.api.schemas import TenantConfigUpdateRequest

        req = TenantConfigUpdateRequest()
        assert req.wf3_optimization_schedule is None


# ── Manager backward compatibility ──


class TestManagerBackwardCompat:
    def test_constructor_without_db_session_factory(self):
        from app.cache.prompt_cache import PromptCacheManager
        from app.cache.tenant_config import TenantConfigManager

        cache = PromptCacheManager(redis_url="redis://localhost:6379/2")
        mgr = TenantConfigManager(cache)
        assert mgr.db_session_factory is None

    def test_constructor_with_db_session_factory(self):
        from app.cache.prompt_cache import PromptCacheManager
        from app.cache.tenant_config import TenantConfigManager
        from app.models.database import async_session_factory

        cache = PromptCacheManager(redis_url="redis://localhost:6379/2")
        mgr = TenantConfigManager(cache, db_session_factory=async_session_factory)
        assert mgr.db_session_factory is async_session_factory

    def test_prompt_cache_attribute(self):
        from app.cache.prompt_cache import PromptCacheManager
        from app.cache.tenant_config import TenantConfigManager

        cache = PromptCacheManager(redis_url="redis://localhost:6379/2")
        mgr = TenantConfigManager(cache)
        assert mgr.prompt_cache is cache


# ── Migration ──


class TestMigration003:
    def _load_migration(self):
        import importlib.util
        from pathlib import Path

        path = (
            Path(__file__).parent.parent
            / "alembic"
            / "versions"
            / "003_create_tenant_config.py"
        )
        spec = importlib.util.spec_from_file_location("migration_003", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_migration_file_exists(self):
        mod = self._load_migration()
        assert mod.revision == "003"
        assert mod.down_revision == "002"

    def test_migration_has_upgrade_downgrade(self):
        mod = self._load_migration()
        assert callable(mod.upgrade)
        assert callable(mod.downgrade)
