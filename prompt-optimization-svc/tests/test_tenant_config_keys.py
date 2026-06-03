"""Unit tests for tenant configuration keys (US-041)."""

from app.cache.tenant_config import (
    DEFAULT_AUTO_PROMOTION,
    DEFAULT_OPTIMIZATION_BUDGET,
    DEFAULT_OPTIMIZATION_ENABLED,
    DEFAULT_OPTIMIZATION_MODEL,
    DEFAULT_PROMOTION_THRESHOLD,
    DEFAULT_SCHEDULE,
    MAX_OPTIMIZATION_BUDGET,
    MIN_OPTIMIZATION_BUDGET,
    VALID_SCHEDULES,
    clamp_optimization_budget,
    validate_schedule,
)


class TestDefaults:
    """AC-2: Defaults applied when keys are missing."""

    def test_optimization_enabled_default(self):
        assert DEFAULT_OPTIMIZATION_ENABLED is True

    def test_auto_promotion_default(self):
        assert DEFAULT_AUTO_PROMOTION is True

    def test_optimization_model_default(self):
        assert DEFAULT_OPTIMIZATION_MODEL == "claude-sonnet-4-6"

    def test_optimization_budget_default(self):
        assert DEFAULT_OPTIMIZATION_BUDGET == 200

    def test_promotion_threshold_default(self):
        assert DEFAULT_PROMOTION_THRESHOLD == 0.05

    def test_schedule_default(self):
        assert DEFAULT_SCHEDULE == "monthly"


class TestScheduleValidation:
    """AC-3: Schedule validated against allowed values."""

    def test_on_demand_valid(self):
        assert validate_schedule("on-demand") == "on-demand"

    def test_biweekly_valid(self):
        assert validate_schedule("biweekly") == "biweekly"

    def test_monthly_valid(self):
        assert validate_schedule("monthly") == "monthly"

    def test_quarterly_valid(self):
        assert validate_schedule("quarterly") == "quarterly"

    def test_invalid_returns_default(self):
        assert validate_schedule("daily") == DEFAULT_SCHEDULE

    def test_empty_returns_default(self):
        assert validate_schedule("") == DEFAULT_SCHEDULE

    def test_valid_schedules_tuple(self):
        assert VALID_SCHEDULES == ("on-demand", "biweekly", "monthly", "quarterly")


class TestBudgetClamping:
    def test_below_min(self):
        assert clamp_optimization_budget(10) == MIN_OPTIMIZATION_BUDGET

    def test_above_max(self):
        assert clamp_optimization_budget(5000) == MAX_OPTIMIZATION_BUDGET

    def test_in_range(self):
        assert clamp_optimization_budget(300) == 300

    def test_at_min(self):
        assert clamp_optimization_budget(50) == 50

    def test_at_max(self):
        assert clamp_optimization_budget(1000) == 1000


class TestSchemas:
    def test_config_response_defaults(self):
        from app.api.schemas import TenantOptimizationConfig

        config = TenantOptimizationConfig(tenant_id="t1")
        assert config.prompt_optimization_enabled is True
        assert config.prompt_auto_promotion is True
        assert config.prompt_optimization_model == "claude-sonnet-4-6"
        assert config.prompt_optimization_budget == 200
        assert config.wf3_optimization_schedule == "monthly"

    def test_update_request_all_optional(self):
        from app.api.schemas import TenantConfigUpdateRequest

        req = TenantConfigUpdateRequest()
        assert req.prompt_optimization_enabled is None
        assert req.wf3_optimization_schedule is None

    def test_update_request_partial(self):
        from app.api.schemas import TenantConfigUpdateRequest

        req = TenantConfigUpdateRequest(
            prompt_optimization_enabled=False,
            wf3_optimization_schedule="quarterly",
        )
        assert req.prompt_optimization_enabled is False
        assert req.wf3_optimization_schedule == "quarterly"
        assert req.prompt_optimization_model is None
