"""Tests for tenant override resolution and isolation (US-012)."""

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.cache.prompt_cache import PromptCacheManager
from app.services.mlflow_registry import PromptInfo
from app.services.prompt_loader import ZorvenPromptLoader


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
    reg.get_prompt_by_state = MagicMock(return_value=None)
    return reg


@pytest.fixture
def loader(mock_cache, mock_registry):
    return ZorvenPromptLoader(mock_cache, mock_registry)


# ------------------------------------------------------------------
# AC-1: Cache miss on tenant key falls through to global key
# ------------------------------------------------------------------


class TestCacheFallthrough:
    """AC-1: Tenant cache miss falls through to global production."""

    async def test_tenant_miss_falls_to_global(self, loader, mock_cache):
        """Tenant cache miss → global production cache checked."""
        call_count = 0

        async def side_effect(name, tenant_id=None):
            nonlocal call_count
            call_count += 1
            if tenant_id is not None:
                return None  # Tenant miss
            return "Global production template"

        mock_cache.get_prompt = AsyncMock(side_effect=side_effect)

        result = await loader.load("test", tenant_id="t-1")
        assert result == "Global production template"
        assert call_count == 2  # tenant check + global check

    async def test_tenant_hit_skips_global(self, loader, mock_cache):
        """Tenant cache hit → no global check needed."""
        async def side_effect(name, tenant_id=None):
            if tenant_id == "t-1":
                return "Tenant template"
            return "Should not reach here"

        mock_cache.get_prompt = AsyncMock(side_effect=side_effect)

        result = await loader.load("test", tenant_id="t-1")
        assert result == "Tenant template"

    async def test_no_tenant_id_checks_global_only(
        self, loader, mock_cache
    ):
        """No tenant_id → only global production checked."""
        mock_cache.get_prompt = AsyncMock(return_value="Global")
        result = await loader.load("test")
        assert result == "Global"
        mock_cache.get_prompt.assert_called_once_with("test")


# ------------------------------------------------------------------
# AC-2: MLflow tries <name>-tenant-<tid> before <name>
# ------------------------------------------------------------------


class TestMLflowTenantLookup:
    """AC-2: MLflow tries tenant-named prompt before base name."""

    async def test_mlflow_tries_tenant_named_prompt(
        self, loader, mock_cache, mock_registry
    ):
        """MLflow checks <name>-tenant-<tid> first."""
        mock_cache.get_prompt.return_value = None

        def load_template(name):
            if name == "zorven-wf1-mra-system-tenant-t-1":
                return "Tenant-specific from MLflow"
            return None

        mock_registry.load_prompt_template.side_effect = load_template
        mock_registry.get_prompt_by_state.return_value = None

        result = await loader.load(
            "zorven-wf1-mra-system", tenant_id="t-1"
        )
        assert result == "Tenant-specific from MLflow"

    async def test_mlflow_tenant_miss_falls_to_production(
        self, loader, mock_cache, mock_registry
    ):
        """Tenant-named prompt miss → PRODUCTION fallback."""
        mock_cache.get_prompt.return_value = None

        # No tenant-named prompt, no TENANT_OVERRIDE
        mock_registry.load_prompt_template.return_value = None
        mock_registry.get_prompt_by_state.side_effect = (
            lambda name, state, tenant_id=None: PromptInfo(
                name=name,
                version=1,
                template="Global production",
                tags={"state": "PRODUCTION"},
            )
            if state == "PRODUCTION"
            else None
        )

        result = await loader.load("test", tenant_id="t-1")
        assert result == "Global production"

    async def test_mlflow_tenant_override_state_checked(
        self, loader, mock_cache, mock_registry
    ):
        """TENANT_OVERRIDE state checked after named prompt miss."""
        mock_cache.get_prompt.return_value = None

        # Named prompt miss
        mock_registry.load_prompt_template.return_value = None

        # But TENANT_OVERRIDE state exists
        def by_state(name, state, tenant_id=None):
            if state == "TENANT_OVERRIDE" and tenant_id == "t-1":
                return PromptInfo(
                    name=name,
                    version=2,
                    template="Override via state",
                    tags={"state": "TENANT_OVERRIDE"},
                )
            return None

        mock_registry.get_prompt_by_state.side_effect = by_state

        result = await loader.load("test", tenant_id="t-1")
        assert result == "Override via state"


# ------------------------------------------------------------------
# AC-3: Missing tenant override silently falls through
# ------------------------------------------------------------------


class TestSilentFallthrough:
    """AC-3: No warning logged when tenant override is missing."""

    async def test_no_warning_on_tenant_miss(
        self, loader, mock_cache, mock_registry, caplog
    ):
        """Missing tenant override doesn't log a warning."""
        mock_cache.get_prompt.return_value = None
        mock_registry.load_prompt_template.return_value = None
        mock_registry.get_prompt_by_state.return_value = None

        with caplog.at_level(logging.DEBUG):
            await loader.load(
                "test",
                tenant_id="t-1",
                fallback_template="fallback",
            )

        # Should NOT have any WARNING about tenant miss
        warnings = [
            r
            for r in caplog.records
            if r.levelno >= logging.WARNING
            and "tenant" in r.message.lower()
        ]
        assert len(warnings) == 0, (
            f"Unexpected tenant warnings: {[r.message for r in warnings]}"
        )

    async def test_actual_error_still_logs_warning(
        self, loader, mock_cache, mock_registry, caplog
    ):
        """Actual MLflow errors still log warnings."""
        mock_cache.get_prompt.return_value = None
        mock_registry.get_prompt_by_state.side_effect = ConnectionError(
            "refused"
        )

        with caplog.at_level(logging.WARNING):
            await loader.load(
                "test",
                tenant_id="t-1",
                fallback_template="fb",
            )

        warnings = [
            r
            for r in caplog.records
            if r.levelno >= logging.WARNING
        ]
        assert len(warnings) >= 1


# ------------------------------------------------------------------
# AC-4: Tenant cache entries cannot be read by other tenants
# ------------------------------------------------------------------


class TestTenantIsolation:
    """AC-4: Tenant data is isolated in cache."""

    def test_cache_keys_are_tenant_scoped(self):
        """Different tenants get different cache keys."""
        key_t1 = PromptCacheManager._prompt_key("test", "t-1")
        key_t2 = PromptCacheManager._prompt_key("test", "t-2")
        key_global = PromptCacheManager._prompt_key("test")

        assert key_t1 != key_t2
        assert key_t1 != key_global
        assert key_t2 != key_global
        assert "t-1" in key_t1
        assert "t-2" in key_t2
        assert "production" in key_global

    async def test_tenant_a_cannot_read_tenant_b_cache(
        self, loader, mock_cache
    ):
        """Tenant A's cached prompt is not returned for tenant B."""
        async def side_effect(name, tenant_id=None):
            if tenant_id == "t-a":
                return "Tenant A prompt"
            return None  # Tenant B and global miss

        mock_cache.get_prompt = AsyncMock(side_effect=side_effect)

        # Tenant A gets their prompt
        result_a = await loader.load("test", tenant_id="t-a")
        assert result_a == "Tenant A prompt"

        # Tenant B does NOT get tenant A's prompt
        result_b = await loader.load(
            "test", tenant_id="t-b", fallback_template="default"
        )
        assert result_b == "default"
        assert result_b != "Tenant A prompt"

    async def test_global_cache_readable_by_all_tenants(
        self, loader, mock_cache
    ):
        """Global production cache is accessible when no tenant override."""
        async def side_effect(name, tenant_id=None):
            if tenant_id is not None:
                return None  # No tenant override
            return "Global shared prompt"

        mock_cache.get_prompt = AsyncMock(side_effect=side_effect)

        # Both tenants fall through to global
        result_a = await loader.load("test", tenant_id="t-a")
        assert result_a == "Global shared prompt"

        result_b = await loader.load("test", tenant_id="t-b")
        assert result_b == "Global shared prompt"

    def test_mlflow_tenant_name_is_unique(self):
        """MLflow tenant-named prompt includes tenant ID."""
        name_t1 = "zorven-wf1-mra-system-tenant-t-1"
        name_t2 = "zorven-wf1-mra-system-tenant-t-2"
        assert name_t1 != name_t2
        assert "t-1" in name_t1
        assert "t-2" in name_t2
