"""Tests for the configuration module."""

from app.core.config import Settings, settings


class TestConfig:
    def test_settings_singleton_exists(self):
        """Module-level settings singleton is initialized."""
        assert settings is not None

    def test_default_port(self):
        """Default port is 8023."""
        assert settings.PORT == 8023

    def test_default_redis_db(self):
        """Default Redis URL uses DB 13."""
        assert "/13" in settings.REDIS_URL

    def test_env_prefix(self):
        """Settings use APA_ prefix."""
        s = Settings()
        assert s.model_config["env_prefix"] == "APA_"

    def test_default_llm_model(self):
        """Default LLM model is Claude Sonnet 4."""
        assert "claude-sonnet" in settings.LLM_MODEL

    def test_guardrail_defaults(self):
        """Guardrail defaults are set."""
        assert settings.INPUT_MAX_TOKENS == 16000
        assert settings.OUTPUT_MAX_CHARS == 120000
        assert settings.CONFIDENCE_THRESHOLD == 0.7
        assert settings.TOKEN_BUDGET_PER_SESSION == 80000
        assert settings.MAX_PERSONAS == 5
        assert settings.MAX_PERSONAS_LIMIT == 8
        assert settings.MAX_CONCURRENT_WEB_REQUESTS == 5

    def test_rate_limit_default(self):
        """Default rate limit is 10/min."""
        assert settings.RATE_LIMIT_PER_MINUTE == 10

    def test_odoo_disabled_by_default(self):
        """Odoo integration is disabled by default."""
        assert settings.ODOO_ENABLED is False

    def test_circuit_breaker_defaults(self):
        """Circuit breaker thresholds are set."""
        assert settings.CB_FAILURE_THRESHOLD == 5
        assert settings.CB_RECOVERY_TIMEOUT == 30
        assert settings.CB_LLM_FAILURE_THRESHOLD == 3
        assert settings.CB_LLM_RECOVERY_TIMEOUT == 60
        assert settings.CB_ODOO_FAILURE_THRESHOLD == 3
        assert settings.CB_ODOO_RECOVERY_TIMEOUT == 60
