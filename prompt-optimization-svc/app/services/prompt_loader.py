"""ZorvenPromptLoader — three-tier prompt resolution (§7.3).

Resolution order:
    1. Redis cache (sub-ms) — tenant override first, then global production
    2. MLflow API (~50ms) — lifecycle-aware fetch, write to cache
    3. Hardcoded fallback — return fallback_template with warning
"""

import asyncio
import logging
import re
import time
from typing import Any, Optional

from app.cache.prompt_cache import PromptCacheManager
from app.cache.tenant_config import DEFAULT_TTL, TenantConfigManager
from app.core.config import settings
from app.logic.circuit_breaker import CircuitBreakerConfig, MLflowCircuitBreaker
from app.metrics import PROMPT_CACHE_HIT, PROMPT_FALLBACK_USAGE, PROMPT_LOAD_LATENCY
from app.services.mlflow_registry import MLflowPromptRegistry

logger = logging.getLogger(__name__)

# MLflow uses {{var}} but Python needs {var}
_MLFLOW_VAR_PATTERN = re.compile(r"\{\{(\w[\w.]*)\}\}")

# Single-pass placeholder pattern for safe substitution
_PLACEHOLDER_PATTERN = re.compile(r"\{([\w.]+)\}")

# Module-level singleton — shared across all loader instances in this process
_default_circuit_breaker = MLflowCircuitBreaker(
    CircuitBreakerConfig(
        failure_threshold_seconds=settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD_SECONDS,
        half_open_interval_seconds=settings.CIRCUIT_BREAKER_HALF_OPEN_INTERVAL_SECONDS,
    )
)


def _convert_mlflow_template(template: str) -> str:
    """Convert MLflow {{var}} placeholders to Python {var}."""
    return _MLFLOW_VAR_PATTERN.sub(r"{\1}", template)


class ZorvenPromptLoader:
    """Three-tier prompt resolution: Redis cache → MLflow → fallback.

    Used by all 15 agents to load prompts with sub-ms latency
    and graceful degradation.
    """

    def __init__(
        self,
        prompt_cache: PromptCacheManager,
        mlflow_registry: Optional[MLflowPromptRegistry] = None,
        tenant_config: Optional[TenantConfigManager] = None,
        circuit_breaker: Optional[MLflowCircuitBreaker] = None,
    ) -> None:
        self.prompt_cache = prompt_cache
        self.mlflow_registry = mlflow_registry
        self.tenant_config = tenant_config
        self.circuit_breaker = (
            circuit_breaker if circuit_breaker is not None else _default_circuit_breaker
        )

    async def load(
        self,
        name: str,
        tenant_id: Optional[str] = None,
        variables: Optional[dict[str, Any]] = None,
        fallback_template: str = "",
        ttl: Optional[int] = None,
    ) -> str:
        """Load, format, and return a prompt template.

        Args:
            name: Prompt name (§3.1 convention).
            tenant_id: Optional tenant for override resolution (AC-1).
            variables: Template variables for formatting (AC-4).
            fallback_template: Hardcoded fallback if all tiers fail (AC-2).
            ttl: Cache TTL in seconds. If None, resolved from tenant config
                 (US-011: clamped to [10, 3600], default 300s).

        Returns:
            Formatted prompt string.
        """
        template = await self._resolve(name, tenant_id, ttl)

        if template is None:
            logger.warning(
                "All tiers failed for prompt '%s' — using fallback",
                name,
            )
            PROMPT_FALLBACK_USAGE.labels(name=name).inc()
            template = fallback_template

        return self._format(template, variables)

    async def _resolve(
        self,
        name: str,
        tenant_id: Optional[str],
        ttl: Optional[int],
    ) -> Optional[str]:
        """Resolve prompt template through three tiers."""
        t0 = time.monotonic()
        resolved_tier = "tier3_fallback"

        # --- Tier 1: Redis cache (AC-1: tenant override first) ---
        if tenant_id:
            cached = await self.prompt_cache.get_prompt(name, tenant_id=tenant_id)
            if cached is not None:
                logger.debug("Tier 1 HIT (tenant): %s tenant=%s", name, tenant_id)
                PROMPT_CACHE_HIT.labels(tier="tier1_tenant", result="hit").inc()
                elapsed_ms = (time.monotonic() - t0) * 1000
                PROMPT_LOAD_LATENCY.labels(
                    name=name, tier="tier1_tenant", tenant_id=tenant_id or ""
                ).observe(elapsed_ms)
                return cached
            PROMPT_CACHE_HIT.labels(tier="tier1_tenant", result="miss").inc()

        cached = await self.prompt_cache.get_prompt(name)
        if cached is not None:
            logger.debug("Tier 1 HIT (production): %s", name)
            PROMPT_CACHE_HIT.labels(tier="tier1_production", result="hit").inc()
            elapsed_ms = (time.monotonic() - t0) * 1000
            PROMPT_LOAD_LATENCY.labels(
                name=name, tier="tier1_production", tenant_id=tenant_id or ""
            ).observe(elapsed_ms)
            return cached
        PROMPT_CACHE_HIT.labels(tier="tier1_production", result="miss").inc()

        # --- Tier 2: MLflow API (lifecycle-aware, circuit-breaker protected) ---
        if self.mlflow_registry is not None:
            if not self.circuit_breaker.should_allow_request():
                logger.debug("Circuit breaker OPEN — skipping MLflow for %s", name)
                PROMPT_CACHE_HIT.labels(
                    tier="tier2_mlflow", result="circuit_open"
                ).inc()
            else:
                try:
                    template, resolved_tenant = await asyncio.to_thread(
                        self._mlflow_resolve, name, tenant_id
                    )
                    if template is not None:
                        self.circuit_breaker.record_success()
                        logger.debug("Tier 2 HIT (MLflow): %s", name)
                        PROMPT_CACHE_HIT.labels(tier="tier2_mlflow", result="hit").inc()
                        resolved_ttl = await self._resolve_ttl(ttl, tenant_id)
                        await self.prompt_cache.set_prompt(
                            name,
                            template,
                            ttl=resolved_ttl,
                            tenant_id=resolved_tenant,
                        )
                        elapsed_ms = (time.monotonic() - t0) * 1000
                        PROMPT_LOAD_LATENCY.labels(
                            name=name,
                            tier="tier2_mlflow",
                            tenant_id=tenant_id or "",
                        ).observe(elapsed_ms)
                        return template
                    # AC-3: Missing tenant override silently falls through
                    logger.debug("Tier 2 MISS (MLflow): %s", name)
                    PROMPT_CACHE_HIT.labels(tier="tier2_mlflow", result="miss").inc()
                except Exception as exc:
                    self.circuit_breaker.record_failure()
                    logger.warning(
                        "Tier 2 ERROR (MLflow) for prompt '%s': %s", name, exc
                    )

        # --- Tier 3: fallback (handled by caller) ---
        elapsed_ms = (time.monotonic() - t0) * 1000
        PROMPT_LOAD_LATENCY.labels(
            name=name, tier=resolved_tier, tenant_id=tenant_id or ""
        ).observe(elapsed_ms)
        return None

    async def _resolve_ttl(self, ttl: Optional[int], tenant_id: Optional[str]) -> int:
        """Resolve cache TTL: explicit > tenant config > default."""
        if ttl is not None:
            return ttl
        if self.tenant_config is not None:
            return await self.tenant_config.get_prompt_cache_ttl(tenant_id)
        return DEFAULT_TTL

    def _mlflow_resolve(
        self, name: str, tenant_id: Optional[str]
    ) -> tuple[Optional[str], Optional[str]]:
        """Lifecycle-aware MLflow resolution (runs in thread).

        Resolution order for tenant_id:
        1. Named tenant prompt: <name>-tenant-<tid> (AC-2)
        2. TENANT_OVERRIDE state on base prompt
        3. Global PRODUCTION

        Returns (template, resolved_tenant_id).
        Missing tenant override silently returns None (AC-3).
        """
        if tenant_id:
            # AC-2: Try tenant-specific named prompt first
            tenant_prompt_name = f"{name}-tenant-{tenant_id}"
            template = self.mlflow_registry.load_prompt_template(tenant_prompt_name)
            if template is not None:
                return template, tenant_id

            # Try TENANT_OVERRIDE state on base prompt
            info = self.mlflow_registry.get_prompt_by_state(
                name, "TENANT_OVERRIDE", tenant_id=tenant_id
            )
            if info is not None:
                return info.template, tenant_id

            # AC-3: Silent fall-through — no warning for missing override

        # Fall back to global PRODUCTION
        info = self.mlflow_registry.get_prompt_by_state(
            name, "PRODUCTION", tenant_id=None
        )
        if info is not None:
            return info.template, None

        # Last resort: load latest version (any state)
        template = self.mlflow_registry.load_prompt_template(name)
        return template, None

    def _format(self, template: str, variables: Optional[dict[str, Any]]) -> str:
        """Format a template with variables (AC-4).

        Uses single-pass regex substitution to safely replace
        {context.var} placeholders without re-processing substituted
        values.
        """
        if not template or not variables:
            return template

        # Convert MLflow {{var}} → Python {var}
        converted = _convert_mlflow_template(template)

        # Stringify all values (AC-4)
        stringified = {k: str(v) for k, v in variables.items()}

        # Single-pass regex substitution (safe against nested placeholders)
        def _replace(match: re.Match) -> str:
            key = match.group(1)
            if key in stringified:
                return stringified[key]
            return match.group(0)  # Leave unmatched placeholders as-is

        return _PLACEHOLDER_PATTERN.sub(_replace, converted)

    async def invalidate(self, name: str) -> int:
        """Invalidate all cached versions of a prompt.

        Returns the number of keys deleted.
        """
        return await self.prompt_cache.invalidate_prompt(name)
