"""Tests for Settings — environment variable loading and defaults."""

from app.core.config import Settings


class TestSettingsDefaults:
    """Verify default values match the design document."""

    def test_port_default(self):
        s = Settings()
        assert s.PORT == 8022

    def test_redis_db_12(self):
        s = Settings()
        assert "/12" in s.REDIS_URL

    def test_max_competitors_default(self):
        s = Settings()
        assert s.MAX_COMPETITORS == 20

    def test_max_pages_per_domain_default(self):
        s = Settings()
        assert s.MAX_PAGES_PER_DOMAIN == 5

    def test_token_budget_default(self):
        s = Settings()
        assert s.TOKEN_BUDGET_PER_SESSION == 75000

    def test_confidence_threshold_default(self):
        s = Settings()
        assert s.CONFIDENCE_THRESHOLD == 0.7

    def test_output_max_chars_default(self):
        s = Settings()
        assert s.OUTPUT_MAX_CHARS == 150000

    def test_result_cache_ttl_4_hours(self):
        s = Settings()
        assert s.RESULT_CACHE_TTL == 14400

    def test_competitor_profile_ttl_24_hours(self):
        s = Settings()
        assert s.COMPETITOR_PROFILE_TTL == 86400

    def test_rbac_enabled_by_default(self):
        s = Settings()
        assert s.RBAC_ENABLED is True

    def test_rag_disabled_by_default(self):
        s = Settings()
        assert s.RAG_ENABLED is False

    def test_gcs_disabled_by_default(self):
        s = Settings()
        assert s.GCS_ENABLED is False

    def test_kafka_consumers_disabled_by_default(self):
        s = Settings()
        assert s.KAFKA_CONSUMERS_ENABLED is False

    def test_llm_model_claude_sonnet_4(self):
        s = Settings()
        assert "claude-sonnet-4" in s.LLM_MODEL

    def test_llm_temperature_conservative(self):
        s = Settings()
        assert s.LLM_TEMPERATURE == 0.3

    def test_env_prefix_cia(self):
        assert Settings.model_config["env_prefix"] == "CIA_"
