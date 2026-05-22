"""ZorvenPromptLoader — three-tier prompt resolution (§7.3).

Resolution order:
    1. Redis cache (sub-ms) — tenant override first, then global production
    2. MLflow API (~50ms) — fetch from registry, write to cache
    3. Hardcoded fallback — return fallback_template with warning
"""

import logging
import re
from typing import Any, Optional

from app.cache.prompt_cache import PromptCacheManager
from app.services.mlflow_registry import MLflowPromptRegistry

logger = logging.getLogger(__name__)

# MLflow uses {{var}} but Python format_map needs {var}
_MLFLOW_VAR_PATTERN = re.compile(r"\{\{(\w[\w.]*)\}\}")


def _convert_mlflow_template(template: str) -> str:
    """Convert MLflow {{var}} placeholders to Python {var} for format_map."""
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
    ) -> None:
        self.prompt_cache = prompt_cache
        self.mlflow_registry = mlflow_registry

    async def load(
        self,
        name: str,
        tenant_id: Optional[str] = None,
        variables: Optional[dict[str, Any]] = None,
        fallback_template: str = "",
        ttl: int = 300,
    ) -> str:
        """Load, format, and return a prompt template.

        Args:
            name: Prompt name (§3.1 convention).
            tenant_id: Optional tenant for override resolution (AC-1).
            variables: Template variables for formatting (AC-4).
            fallback_template: Hardcoded fallback if all tiers fail (AC-2).
            ttl: Cache TTL in seconds for setex (AC-3).

        Returns:
            Formatted prompt string.
        """
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
                logger.debug("Tier 1 HIT (tenant): %s tenant=%s", name, tenant_id)
                return cached

        cached = await self.prompt_cache.get_prompt(name)
        if cached is not None:
            logger.debug("Tier 1 HIT (production): %s", name)
            return cached

        # --- Tier 2: MLflow API ---
        if self.mlflow_registry is not None:
            try:
                template = self.mlflow_registry.load_prompt_template(name)
                if template is not None:
                    logger.debug("Tier 2 HIT (MLflow): %s", name)
                    # Write to cache with configurable TTL (AC-3)
                    await self.prompt_cache.set_prompt(
                        name,
                        template,
                        ttl=ttl,
                        tenant_id=tenant_id,
                    )
                    return template
            except Exception as exc:
                # AC-2: Log warning and fall through to fallback
                logger.warning(
                    "Tier 2 FAIL (MLflow) for prompt '%s': %s", name, exc
                )

        # --- Tier 3: fallback (handled by caller) ---
        return None

    def _format(
        self, template: str, variables: Optional[dict[str, Any]]
    ) -> str:
        """Format a template with variables (AC-4).

        Converts MLflow {{var}} to Python {var}, then applies
        str.format_map with stringified values. Dotted keys like
        {context.brand_name} are replaced directly via string
        substitution since str.format_map treats dots as attribute access.
        """
        if not template or not variables:
            return template

        # Convert MLflow {{var}} → Python {var}
        converted = _convert_mlflow_template(template)

        # Stringify all values (AC-4)
        stringified = {k: str(v) for k, v in variables.items()}

        # Replace dotted keys directly (format_map can't handle dots)
        result = converted
        for key, value in stringified.items():
            result = result.replace(f"{{{key}}}", value)

        return result

    async def invalidate(self, name: str) -> int:
        """Invalidate all cached versions of a prompt.

        Returns the number of keys deleted.
        """
        return await self.prompt_cache.invalidate_prompt(name)
