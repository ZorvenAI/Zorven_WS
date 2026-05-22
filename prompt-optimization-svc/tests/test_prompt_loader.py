"""Tests for ZorvenPromptLoader — three-tier resolution (§7.3)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.prompt_loader import (
    ZorvenPromptLoader,
    _convert_mlflow_template,
)


@pytest.fixture
def mock_cache():
    """Mock PromptCacheManager."""
    cache = AsyncMock()
    cache.get_prompt = AsyncMock(return_value=None)
    cache.set_prompt = AsyncMock()
    cache.invalidate_prompt = AsyncMock(return_value=0)
    return cache


@pytest.fixture
def mock_registry():
    """Mock MLflowPromptRegistry."""
    reg = MagicMock()
    reg.load_prompt_template = MagicMock(return_value=None)
    return reg


@pytest.fixture
def loader(mock_cache, mock_registry):
    """ZorvenPromptLoader with mocked dependencies."""
    return ZorvenPromptLoader(mock_cache, mock_registry)


# ------------------------------------------------------------------
# Tier 1: Redis cache (AC-1)
# ------------------------------------------------------------------


class TestTier1CacheHit:
    """Redis cache returns template — no MLflow call needed."""

    async def test_cache_hit_production(self, loader, mock_cache, mock_registry):
        """Production cache hit returns template without calling MLflow."""
        mock_cache.get_prompt.return_value = "You are a researcher for {context.brand_name}"
        result = await loader.load("zorven-wf1-mra-system")
        assert "researcher" in result
        mock_registry.load_prompt_template.assert_not_called()

    async def test_tenant_override_checked_first(self, loader, mock_cache):
        """AC-1: Tenant override cache is checked before global production."""
        call_count = 0

        async def side_effect(name, tenant_id=None):
            nonlocal call_count
            call_count += 1
            if tenant_id == "t-1" and call_count == 1:
                return "Tenant-specific prompt"
            return None

        mock_cache.get_prompt = AsyncMock(side_effect=side_effect)
        result = await loader.load("test", tenant_id="t-1")
        assert result == "Tenant-specific prompt"

    async def test_falls_through_to_global_on_tenant_miss(
        self, loader, mock_cache
    ):
        """If tenant cache misses, checks global production cache."""
        call_count = 0

        async def side_effect(name, tenant_id=None):
            nonlocal call_count
            call_count += 1
            if tenant_id is not None:
                return None  # Tenant miss
            return "Global production prompt"

        mock_cache.get_prompt = AsyncMock(side_effect=side_effect)
        result = await loader.load("test", tenant_id="t-1")
        assert result == "Global production prompt"


# ------------------------------------------------------------------
# Tier 2: MLflow API (AC-3)
# ------------------------------------------------------------------


class TestTier2MLflow:
    """Redis miss → MLflow fetch → cache write."""

    async def test_mlflow_hit_on_cache_miss(
        self, loader, mock_cache, mock_registry
    ):
        """Cache miss triggers lifecycle-aware MLflow fetch."""
        mock_cache.get_prompt.return_value = None
        mock_registry.get_prompt_by_state.return_value = None
        mock_registry.load_prompt_template.return_value = "MLflow template"

        result = await loader.load("test")
        assert result == "MLflow template"

    async def test_mlflow_result_cached_with_ttl(
        self, loader, mock_cache, mock_registry
    ):
        """AC-3: MLflow result written to Redis with setex (configurable TTL)."""
        mock_cache.get_prompt.return_value = None
        mock_registry.get_prompt_by_state.return_value = None
        mock_registry.load_prompt_template.return_value = "MLflow template"

        await loader.load("test", ttl=600)
        mock_cache.set_prompt.assert_called_once_with(
            "test", "MLflow template", ttl=600, tenant_id=None
        )

    async def test_custom_ttl_passed_to_cache(
        self, loader, mock_cache, mock_registry
    ):
        """TTL parameter flows through to cache set."""
        mock_cache.get_prompt.return_value = None
        mock_registry.get_prompt_by_state.return_value = None
        mock_registry.load_prompt_template.return_value = "t"

        await loader.load("test", ttl=120)
        assert mock_cache.set_prompt.call_args[1]["ttl"] == 120

    async def test_tenant_id_resolves_tenant_override_first(
        self, loader, mock_cache, mock_registry
    ):
        """Tier 2 with tenant_id checks TENANT_OVERRIDE before PRODUCTION."""
        mock_cache.get_prompt.return_value = None

        from app.services.mlflow_registry import PromptInfo

        tenant_info = PromptInfo(
            name="test",
            version=3,
            template="Tenant override template",
            tags={"state": "TENANT_OVERRIDE", "tenant_id": "t-1"},
        )

        def by_state(name, state, tenant_id=None):
            if state == "TENANT_OVERRIDE" and tenant_id == "t-1":
                return tenant_info
            return None

        mock_registry.get_prompt_by_state.side_effect = by_state

        result = await loader.load("test", tenant_id="t-1")
        assert result == "Tenant override template"
        # Should be cached under the tenant key
        mock_cache.set_prompt.assert_called_once_with(
            "test", "Tenant override template", ttl=300, tenant_id="t-1"
        )

    async def test_tenant_id_falls_back_to_production(
        self, loader, mock_cache, mock_registry
    ):
        """Tier 2: No tenant override → falls back to global PRODUCTION."""
        mock_cache.get_prompt.return_value = None

        from app.services.mlflow_registry import PromptInfo

        prod_info = PromptInfo(
            name="test",
            version=2,
            template="Global production",
            tags={"state": "PRODUCTION"},
        )

        def by_state(name, state, tenant_id=None):
            if state == "PRODUCTION" and tenant_id is None:
                return prod_info
            return None

        mock_registry.get_prompt_by_state.side_effect = by_state

        result = await loader.load("test", tenant_id="t-1")
        assert result == "Global production"
        # Cached under production key (tenant_id=None)
        mock_cache.set_prompt.assert_called_once_with(
            "test", "Global production", ttl=300, tenant_id=None
        )


# ------------------------------------------------------------------
# Tier 3: Fallback (AC-2)
# ------------------------------------------------------------------


class TestTier3Fallback:
    """Redis miss + MLflow failure → fallback template."""

    async def test_mlflow_failure_returns_fallback(
        self, loader, mock_cache, mock_registry
    ):
        """AC-2: MLflow exception → fallback_template returned."""
        mock_cache.get_prompt.return_value = None
        mock_registry.get_prompt_by_state.side_effect = Exception(
            "connection refused"
        )

        result = await loader.load(
            "test", fallback_template="Fallback: help with {context.task}"
        )
        assert "Fallback" in result

    async def test_mlflow_failure_logs_warning(
        self, loader, mock_cache, mock_registry, caplog
    ):
        """AC-2: Warning logged on MLflow failure."""
        mock_cache.get_prompt.return_value = None
        mock_registry.get_prompt_by_state.side_effect = Exception("timeout")

        import logging

        with caplog.at_level(logging.WARNING):
            await loader.load("test", fallback_template="fb")
        assert any("Tier 2 FAIL" in r.message for r in caplog.records)

    async def test_all_tiers_fail_returns_empty(
        self, loader, mock_cache, mock_registry
    ):
        """All tiers fail + no fallback → empty string."""
        mock_cache.get_prompt.return_value = None
        mock_registry.get_prompt_by_state.return_value = None
        mock_registry.load_prompt_template.return_value = None

        result = await loader.load("test")
        assert result == ""

    async def test_mlflow_returns_none_uses_fallback(
        self, loader, mock_cache, mock_registry
    ):
        """MLflow returns None (prompt not found) → fallback."""
        mock_cache.get_prompt.return_value = None
        mock_registry.get_prompt_by_state.return_value = None
        mock_registry.load_prompt_template.return_value = None

        result = await loader.load("test", fallback_template="default prompt")
        assert result == "default prompt"

    async def test_no_registry_uses_fallback(self, mock_cache):
        """Loader without MLflow registry goes straight to fallback."""
        loader = ZorvenPromptLoader(mock_cache, mlflow_registry=None)
        mock_cache.get_prompt.return_value = None

        result = await loader.load("test", fallback_template="fallback only")
        assert result == "fallback only"


# ------------------------------------------------------------------
# Template formatting (AC-4)
# ------------------------------------------------------------------


class TestTemplateFormatting:
    """Template formatting with str.format_map and stringified variables."""

    async def test_variables_applied(self, loader, mock_cache):
        """AC-4: Variables replace placeholders."""
        mock_cache.get_prompt.return_value = (
            "Analyze {context.brand_name} in {context.industry}"
        )
        result = await loader.load(
            "test",
            variables={
                "context.brand_name": "Acme Corp",
                "context.industry": "tech",
            },
        )
        assert "Acme Corp" in result
        assert "tech" in result

    async def test_non_string_values_stringified(self, loader, mock_cache):
        """AC-4: Non-string values converted to strings."""
        mock_cache.get_prompt.return_value = (
            "Budget: {context.budget}, Items: {context.count}"
        )
        result = await loader.load(
            "test",
            variables={"context.budget": 50000.0, "context.count": 5},
        )
        assert "50000.0" in result
        assert "5" in result

    async def test_no_variables_returns_template_as_is(
        self, loader, mock_cache
    ):
        """No variables → template returned unchanged."""
        mock_cache.get_prompt.return_value = "Plain template"
        result = await loader.load("test")
        assert result == "Plain template"

    async def test_missing_variable_handled_gracefully(
        self, loader, mock_cache
    ):
        """Missing variable doesn't crash — returns template with placeholder."""
        mock_cache.get_prompt.return_value = "Hello {name}, your {missing_var}"
        result = await loader.load(
            "test", variables={"name": "World"}
        )
        assert "Hello World" in result

    async def test_mlflow_double_brace_conversion(self, loader, mock_cache):
        """MLflow {{var}} converted to {var} for format_map."""
        mock_cache.get_prompt.return_value = (
            "Analyze {{context.brand_name}} in {{context.industry}}"
        )
        result = await loader.load(
            "test",
            variables={
                "context.brand_name": "TestBrand",
                "context.industry": "retail",
            },
        )
        assert "TestBrand" in result
        assert "retail" in result


class TestMlflowTemplateConversion:
    """Test _convert_mlflow_template helper."""

    def test_double_braces_to_single(self):
        assert _convert_mlflow_template("{{var}}") == "{var}"

    def test_dotted_variables(self):
        result = _convert_mlflow_template("{{context.brand_name}}")
        assert result == "{context.brand_name}"

    def test_multiple_variables(self):
        result = _convert_mlflow_template("{{a}} and {{b.c}}")
        assert result == "{a} and {b.c}"

    def test_no_variables_unchanged(self):
        assert _convert_mlflow_template("plain text") == "plain text"

    def test_single_braces_unchanged(self):
        assert _convert_mlflow_template("{already_single}") == "{already_single}"


# ------------------------------------------------------------------
# Cache invalidation (AC-5)
# ------------------------------------------------------------------


class TestCacheInvalidation:
    """Test cache invalidation path."""

    async def test_invalidate_delegates_to_cache(
        self, loader, mock_cache
    ):
        """invalidate() calls PromptCacheManager.invalidate_prompt()."""
        mock_cache.invalidate_prompt.return_value = 3
        deleted = await loader.invalidate("zorven-wf1-mra-system")
        assert deleted == 3
        mock_cache.invalidate_prompt.assert_called_once_with(
            "zorven-wf1-mra-system"
        )

    async def test_invalidate_returns_zero_on_miss(
        self, loader, mock_cache
    ):
        """No keys to invalidate → returns 0."""
        mock_cache.invalidate_prompt.return_value = 0
        deleted = await loader.invalidate("nonexistent")
        assert deleted == 0
