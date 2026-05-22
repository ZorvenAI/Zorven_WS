"""ZorvenPromptLoader — three-tier prompt resolution (§7.3).

Resolution order:
    1. Redis cache (sub-ms) — tenant override first, then global production
    2. MLflow API (~50ms) — lifecycle-aware fetch, write to cache
    3. Hardcoded fallback — return fallback_template with warning
"""

import asyncio
import logging
import re
from typing import Any, Optional

from app.cache.prompt_cache import PromptCacheManager
from app.cache.tenant_config import TenantConfigManager
from app.services.mlflow_registry import MLflowPromptRegistry

logger = logging.getLogger(__name__)

# MLflow uses {{var}} but Python needs {var}
_MLFLOW_VAR_PATTERN = re.compile(r"\{\{(\w[\w.]*)\}\}")

# Single-pass placeholder pattern for safe substitution
_PLACEHOLDER_PATTERN = re.compile(r"\{([\w.]+)\}")


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
    ) -> None:
        self.prompt_cache = prompt_cache
        self.mlflow_registry = mlflow_registry
        self.tenant_config = tenant_config

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
        # Resolve TTL from tenant config if not explicitly provided
        if ttl is None:
            if self.tenant_config is not None:
                ttl = await self.tenant_config.get_prompt_cache_ttl(tenant_id)
            else:
                ttl = 300

        template = await self._resolve(name, tenant_id, ttl)

        if template is None:
            logger.warning(
                "All tiers failed for prompt '%s' — using fallback",
                name,
            )
            template = fallback_template

        return self._format(template, variables)

    async def _resolve(
        self,
        name: str,
        tenant_id: Optional[str],
        ttl: int,
    ) -> Optional[str]:
        """Resolve prompt template through three tiers."""
        # --- Tier 1: Redis cache (AC-1: tenant override first) ---
        if tenant_id:
            cached = await self.prompt_cache.get_prompt(
                name, tenant_id=tenant_id
            )
            if cached is not None:
                logger.debug(
                    "Tier 1 HIT (tenant): %s tenant=%s", name, tenant_id
                )
                return cached

        cached = await self.prompt_cache.get_prompt(name)
        if cached is not None:
            logger.debug("Tier 1 HIT (production): %s", name)
            return cached

        # --- Tier 2: MLflow API (lifecycle-aware) ---
        if self.mlflow_registry is not None:
            try:
                template, resolved_tenant = await asyncio.to_thread(
                    self._mlflow_resolve, name, tenant_id
                )
                if template is not None:
                    logger.debug("Tier 2 HIT (MLflow): %s", name)
                    # Cache under the correct key (AC-3)
                    await self.prompt_cache.set_prompt(
                        name,
                        template,
                        ttl=ttl,
                        tenant_id=resolved_tenant,
                    )
                    return template
            except Exception as exc:
                # AC-2: Log warning and fall through to fallback
                logger.warning(
                    "Tier 2 FAIL (MLflow) for prompt '%s': %s", name, exc
                )

        # --- Tier 3: fallback (handled by caller) ---
        return None

    def _mlflow_resolve(
        self, name: str, tenant_id: Optional[str]
    ) -> tuple[Optional[str], Optional[str]]:
        """Lifecycle-aware MLflow resolution (runs in thread).

        Checks TENANT_OVERRIDE first (if tenant_id), then global
        PRODUCTION. Returns (template, resolved_tenant_id).
        """
        # Try tenant override first
        if tenant_id:
            info = self.mlflow_registry.get_prompt_by_state(
                name, "TENANT_OVERRIDE", tenant_id=tenant_id
            )
            if info is not None:
                return info.template, tenant_id

        # Fall back to global PRODUCTION
        info = self.mlflow_registry.get_prompt_by_state(
            name, "PRODUCTION", tenant_id=None
        )
        if info is not None:
            return info.template, None

        # Last resort: load latest version (any state)
        template = self.mlflow_registry.load_prompt_template(name)
        return template, None

    def _format(
        self, template: str, variables: Optional[dict[str, Any]]
    ) -> str:
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
