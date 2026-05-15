"""Tests for the application configuration."""

import pytest

from app.core.config import Settings


@pytest.mark.unit
def test_default_settings():
    """Default settings are valid."""
    s = Settings()
    assert s.PORT == 8025
    assert s.REDIS_URL == "redis://localhost:6379/15"
    assert s.LLM_MODEL == "claude-sonnet-4-5-20250929"
    assert s.LLM_TEMPERATURE == 0.3
    assert s.LLM_MAX_TOKENS == 16384
    assert s.TOKEN_BUDGET_PER_SESSION == 100000
    assert s.MAX_FEEDBACK_ITEMS == 5000
    assert s.INPUT_MAX_TOKENS == 8192
    assert s.OUTPUT_MAX_CHARS == 150000
    assert s.GROUNDING_THRESHOLD == 0.8
    assert s.CONFIDENCE_THRESHOLD == 0.7
    assert s.MAX_CONCURRENT_RESEARCH == 6


@pytest.mark.unit
def test_voc_health_weights_default():
    """VoC health score weights sum to 1.0."""
    s = Settings()
    total = (
        s.VOC_HEALTH_NPS_WEIGHT
        + s.VOC_HEALTH_SENTIMENT_WEIGHT
        + s.VOC_HEALTH_THEME_WEIGHT
    )
    assert abs(total - 1.0) < 0.001


@pytest.mark.unit
def test_redis_db_15():
    """Redis URL uses DB 15."""
    s = Settings()
    assert "/15" in s.REDIS_URL


@pytest.mark.unit
def test_env_prefix_is_voca():
    """Settings use VOCA_ environment prefix."""
    assert Settings.model_config["env_prefix"] == "VOCA_"


@pytest.mark.unit
def test_ingestion_defaults():
    """Continuous ingestion settings have correct defaults."""
    s = Settings()
    assert s.INGESTION_POLL_INTERVAL == 900
    assert s.INGESTION_KAFKA_HEALTH_CHECK_INTERVAL == 60
    assert s.INGESTION_CONSUMER_GROUP == "voc-agent-ingestion-cg"


@pytest.mark.unit
def test_hash_lookup_ttl():
    """Hash lookup TTL is 90 days."""
    s = Settings()
    assert s.HASH_LOOKUP_TTL == 7776000  # 90 days in seconds
