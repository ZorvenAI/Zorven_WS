"""
Unit tests for ai_services.prompt_cache module.
Tests layered prompt building, caching, hashing, and metrics.
"""

import pytest
from unittest.mock import patch, MagicMock

from ai_services.prompt_cache import (
    build_layer_1,
    build_layer_2,
    build_layer_3,
    compute_prefix_hash,
    get_or_create_prompt_snapshot,
    build_system_prompt_from_snapshot,
    get_cache_metrics,
    CHAT_TOOLS,
    _FIELD_LABELS,
)


@pytest.mark.unit
class TestBuildLayers:
    """Tests for individual layer builders."""

    def test_layer_1_returns_static_instructions(self):
        result = build_layer_1()
        assert "Zorven AI" in result
        assert "brand strategy assistant" in result

    def test_layer_1_is_deterministic(self):
        assert build_layer_1() == build_layer_1()

    def test_layer_2_includes_all_tools(self):
        result = build_layer_2()
        for tool in CHAT_TOOLS:
            assert tool["name"] in result
            assert tool["description"] in result

    def test_layer_2_is_deterministic(self):
        assert build_layer_2() == build_layer_2()

    def test_layer_3_with_company_data(self):
        data = {"name": "Acme Corp", "industry": "Technology"}
        result = build_layer_3(data)
        assert "Company: Acme Corp" in result
        assert "Industry: Technology" in result

    def test_layer_3_empty_company_data(self):
        result = build_layer_3({})
        assert result == ""

    def test_layer_3_skips_none_values(self):
        data = {"name": "Acme Corp", "industry": None, "website": ""}
        result = build_layer_3(data)
        assert "Company: Acme Corp" in result
        assert "Industry" not in result
        assert "Website" not in result

    def test_layer_3_uses_all_field_labels(self):
        # Provide every field with a value
        data = {field: f"val_{field}" for field in _FIELD_LABELS}
        result = build_layer_3(data)
        for label in _FIELD_LABELS.values():
            assert label in result


@pytest.mark.unit
class TestComputePrefixHash:
    """Tests for hash computation."""

    def test_hash_is_deterministic(self):
        h1 = compute_prefix_hash("a", "b", "c")
        h2 = compute_prefix_hash("a", "b", "c")
        assert h1 == h2

    def test_hash_length_is_16(self):
        h = compute_prefix_hash("a", "b", "c")
        assert len(h) == 16

    def test_hash_changes_on_different_input(self):
        h1 = compute_prefix_hash("a", "b", "c")
        h2 = compute_prefix_hash("a", "b", "d")
        assert h1 != h2

    def test_hash_is_hex(self):
        h = compute_prefix_hash("x", "y", "z")
        int(h, 16)  # Should not raise


@pytest.mark.django_db
@pytest.mark.unit
class TestGetOrCreatePromptSnapshot:
    """Tests for snapshot creation and caching."""

    def test_creates_snapshot_on_miss(self):
        company_data = {"name": "Test Co", "industry": "Tech"}
        snapshot = get_or_create_prompt_snapshot(1, "sess-123", company_data)

        assert "layer_1" in snapshot
        assert "layer_2" in snapshot
        assert "layer_3" in snapshot
        assert "prefix_hash" in snapshot
        assert "Zorven AI" in snapshot["layer_1"]
        assert "Company: Test Co" in snapshot["layer_3"]

    def test_returns_cached_on_hit(self):
        company_data = {"name": "Test Co"}
        # First call — creates
        s1 = get_or_create_prompt_snapshot(2, "sess-456", company_data)
        # Second call — should be cached
        s2 = get_or_create_prompt_snapshot(2, "sess-456", company_data)
        assert s1 == s2

    def test_different_sessions_get_different_keys(self):
        data_a = {"name": "Alpha"}
        data_b = {"name": "Beta"}
        s1 = get_or_create_prompt_snapshot(3, "sess-a", data_a)
        s2 = get_or_create_prompt_snapshot(3, "sess-b", data_b)
        # Different company data → different layer_3/hash
        assert s1["prefix_hash"] != s2["prefix_hash"]

    @patch("ai_services.prompt_cache.cache")
    def test_fail_open_on_redis_read_error(self, mock_cache):
        mock_cache.get.side_effect = Exception("Redis down")
        mock_cache.set = MagicMock()
        mock_cache.incr = MagicMock()

        snapshot = get_or_create_prompt_snapshot(4, "sess-err", {"name": "Err Co"})
        # Should still return a valid snapshot
        assert "layer_1" in snapshot
        assert "prefix_hash" in snapshot

    @patch("ai_services.prompt_cache.cache")
    def test_fail_open_on_redis_write_error(self, mock_cache):
        mock_cache.get.return_value = None
        mock_cache.set.side_effect = Exception("Redis down")
        mock_cache.incr.side_effect = Exception("Redis down")

        snapshot = get_or_create_prompt_snapshot(
            5, "sess-write-err", {"name": "Write Err"}
        )
        assert "layer_1" in snapshot


@pytest.mark.django_db
@pytest.mark.unit
class TestBuildSystemPromptFromSnapshot:
    """Tests for assembling the system prompt."""

    def test_assembles_all_layers(self):
        snapshot = {
            "layer_1": "L1 text",
            "layer_2": "L2 text",
            "layer_3": "L3 text",
            "prefix_hash": "abc123",
        }
        result = build_system_prompt_from_snapshot(snapshot)
        assert "L1 text" in result
        assert "L2 text" in result
        assert "L3 text" in result

    def test_skips_empty_layer_3(self):
        snapshot = {
            "layer_1": "L1",
            "layer_2": "L2",
            "layer_3": "",
            "prefix_hash": "abc",
        }
        result = build_system_prompt_from_snapshot(snapshot)
        assert "L1" in result
        assert "L2" in result
        # Only two parts joined
        assert result.count("\n\n") == 1


@pytest.mark.django_db
@pytest.mark.unit
class TestCacheMetrics:
    """Tests for hit/miss counters and metrics retrieval."""

    def test_metrics_increment_on_miss(self):
        company_data = {"name": "Metrics Co"}
        get_or_create_prompt_snapshot(100, "met-miss", company_data)

        metrics = get_cache_metrics()
        assert metrics["global"]["misses"] >= 1

    def test_metrics_increment_on_hit(self):
        company_data = {"name": "Hit Co"}
        get_or_create_prompt_snapshot(101, "met-hit", company_data)
        # Second call should be a hit
        get_or_create_prompt_snapshot(101, "met-hit", company_data)

        metrics = get_cache_metrics()
        assert metrics["global"]["hits"] >= 1

    def test_metrics_health_levels(self):
        # Test the health calculation logic directly
        from ai_services.prompt_cache import get_cache_metrics

        metrics = get_cache_metrics()
        assert metrics["global"]["health"] in ("healthy", "warning", "critical")

    def test_tenant_metrics(self):
        company_data = {"name": "Tenant Metrics"}
        get_or_create_prompt_snapshot(200, "tm-1", company_data)

        metrics = get_cache_metrics(tenant_id=200)
        assert "tenant" in metrics
        assert metrics["tenant"]["misses"] >= 1

    @patch("ai_services.prompt_cache.cache")
    def test_metrics_fail_open(self, mock_cache):
        mock_cache.get.side_effect = Exception("Redis down")

        metrics = get_cache_metrics()
        assert metrics["global"]["hits"] == 0
        assert metrics["global"]["health"] == "critical"
