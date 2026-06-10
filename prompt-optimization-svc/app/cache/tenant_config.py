"""Tenant-configurable optimization settings (§10.2).

Each key is stored as an individual Redis string at:
    tenant:{tid}:config.<key_name>

Defaults from §10.2 and §20.1 applied when keys are missing.

US-047: Schedule choices are dual-written to Redis (hot path) and
PostgreSQL (source-of-truth). On Redis miss, falls back to PostgreSQL
and re-warms the Redis cache.
"""

import logging
from typing import Optional

from app.cache.prompt_cache import PromptCacheManager

logger = logging.getLogger(__name__)

# Prompt cache TTL
DEFAULT_TTL = 300
MIN_TTL = 10
MAX_TTL = 3600

# Golden dataset size
DEFAULT_DATASET_SIZE = 10
MIN_DATASET_SIZE = 3
MAX_DATASET_SIZE = 50

# Optimization enabled/auto-promotion
DEFAULT_OPTIMIZATION_ENABLED = True
DEFAULT_AUTO_PROMOTION = True

# Optimization model
DEFAULT_OPTIMIZATION_MODEL = "claude-sonnet-4-6"

# Optimization budget (max_metric_calls)
DEFAULT_OPTIMIZATION_BUDGET = 200
MIN_OPTIMIZATION_BUDGET = 50
MAX_OPTIMIZATION_BUDGET = 1000

# Promotion threshold
DEFAULT_PROMOTION_THRESHOLD = 0.05

# WF3 optimization schedule
VALID_SCHEDULES = ("on-demand", "biweekly", "monthly", "quarterly")
DEFAULT_SCHEDULE = "monthly"


def clamp_ttl(ttl: int) -> int:
    """Clamp TTL to [MIN_TTL, MAX_TTL] inclusive."""
    return max(MIN_TTL, min(MAX_TTL, ttl))


def clamp_dataset_size(size: int) -> int:
    """Clamp dataset size to [MIN_DATASET_SIZE, MAX_DATASET_SIZE] inclusive."""
    return max(MIN_DATASET_SIZE, min(MAX_DATASET_SIZE, size))


def clamp_optimization_budget(budget: int) -> int:
    """Clamp optimization budget to [MIN, MAX] inclusive."""
    return max(MIN_OPTIMIZATION_BUDGET, min(MAX_OPTIMIZATION_BUDGET, budget))


def validate_schedule(schedule: str) -> str:
    """Validate schedule against allowed values. Returns default if invalid."""
    if schedule in VALID_SCHEDULES:
        return schedule
    return DEFAULT_SCHEDULE


def strict_validate_schedule(schedule: str) -> str:
    """Validate schedule, raising ValueError for invalid values (AC-3).

    Unlike validate_schedule() which silently falls back to default,
    this raises so the API layer can return HTTP 400.
    """
    if schedule in VALID_SCHEDULES:
        return schedule
    raise ValueError(
        f"Invalid schedule '{schedule}'. "
        f"Must be one of: {', '.join(VALID_SCHEDULES)}"
    )


class TenantConfigManager:
    """Read/write per-tenant configuration from Redis."""

    CONFIG_KEY_TEMPLATE = "tenant:{tenant_id}:config.prompt_cache_ttl_seconds"
    DATASET_SIZE_KEY_TEMPLATE = "tenant:{tenant_id}:config.golden_dataset_default_size"
    OPT_ENABLED_KEY = "tenant:{tenant_id}:config.prompt_optimization_enabled"
    AUTO_PROMOTION_KEY = "tenant:{tenant_id}:config.prompt_auto_promotion"
    OPT_MODEL_KEY = "tenant:{tenant_id}:config.prompt_optimization_model"
    OPT_BUDGET_KEY = "tenant:{tenant_id}:config.prompt_optimization_budget"
    PROMOTION_THRESHOLD_KEY = "tenant:{tenant_id}:config.prompt_promotion_threshold"
    SCHEDULE_KEY = "tenant:{tenant_id}:config.wf3_optimization_schedule"

    def __init__(
        self, prompt_cache: PromptCacheManager, db_session_factory=None
    ) -> None:
        self.prompt_cache = prompt_cache
        self.db_session_factory = db_session_factory

    async def get_prompt_cache_ttl(self, tenant_id: Optional[str] = None) -> int:
        """Get the prompt cache TTL for a tenant.

        Returns the tenant-specific TTL clamped to [10, 3600],
        or 300s if no tenant config exists (AC-2).
        """
        if not tenant_id:
            return DEFAULT_TTL

        try:
            r = await self.prompt_cache.connect()
            key = self.CONFIG_KEY_TEMPLATE.format(tenant_id=tenant_id)
            value = await r.get(key)
            if value is None:
                return DEFAULT_TTL
            return clamp_ttl(int(value))
        except Exception as exc:
            logger.warning(
                "Failed to read tenant TTL config for %s: %s",
                tenant_id,
                exc,
            )
            return DEFAULT_TTL

    async def set_prompt_cache_ttl(self, tenant_id: str, ttl: int) -> None:
        """Set the prompt cache TTL for a tenant.

        Value is clamped to [10, 3600] before storing (AC-1).
        """
        clamped = clamp_ttl(ttl)
        try:
            r = await self.prompt_cache.connect()
            key = self.CONFIG_KEY_TEMPLATE.format(tenant_id=tenant_id)
            await r.set(key, str(clamped))
            logger.info(
                "Tenant TTL config set: %s = %ds (requested %ds)",
                tenant_id,
                clamped,
                ttl,
            )
        except Exception as exc:
            logger.warning(
                "Failed to set tenant TTL config for %s: %s",
                tenant_id,
                exc,
            )

    async def get_golden_dataset_size(self, tenant_id: Optional[str] = None) -> int:
        """Get the golden dataset size limit for a tenant.

        Returns the tenant-specific size clamped to [3, 50],
        or 10 if no tenant config exists.
        """
        if not tenant_id:
            return DEFAULT_DATASET_SIZE

        try:
            r = await self.prompt_cache.connect()
            key = self.DATASET_SIZE_KEY_TEMPLATE.format(tenant_id=tenant_id)
            value = await r.get(key)
            if value is None:
                return DEFAULT_DATASET_SIZE
            return clamp_dataset_size(int(value))
        except Exception as exc:
            logger.warning(
                "Failed to read tenant dataset size for %s: %s",
                tenant_id,
                exc,
            )
            return DEFAULT_DATASET_SIZE

    async def set_golden_dataset_size(self, tenant_id: str, size: int) -> None:
        """Set the golden dataset size limit for a tenant.

        Value is clamped to [3, 50] before storing (AC-3).
        """
        clamped = clamp_dataset_size(size)
        try:
            r = await self.prompt_cache.connect()
            key = self.DATASET_SIZE_KEY_TEMPLATE.format(tenant_id=tenant_id)
            await r.set(key, str(clamped))
            logger.info(
                "Tenant dataset size set: %s = %d (requested %d)",
                tenant_id,
                clamped,
                size,
            )
        except Exception as exc:
            logger.warning(
                "Failed to set tenant dataset size for %s: %s",
                tenant_id,
                exc,
            )

    # --- Optimization enabled ---

    async def get_optimization_enabled(self, tenant_id: Optional[str] = None) -> bool:
        return await self._get_bool(
            self.OPT_ENABLED_KEY, tenant_id, DEFAULT_OPTIMIZATION_ENABLED
        )

    async def set_optimization_enabled(self, tenant_id: str, enabled: bool) -> None:
        await self._set_value(self.OPT_ENABLED_KEY, tenant_id, str(enabled).lower())

    # --- Auto promotion ---

    async def get_auto_promotion(self, tenant_id: Optional[str] = None) -> bool:
        return await self._get_bool(
            self.AUTO_PROMOTION_KEY, tenant_id, DEFAULT_AUTO_PROMOTION
        )

    async def set_auto_promotion(self, tenant_id: str, enabled: bool) -> None:
        await self._set_value(self.AUTO_PROMOTION_KEY, tenant_id, str(enabled).lower())

    # --- Optimization model ---

    async def get_optimization_model(self, tenant_id: Optional[str] = None) -> str:
        return await self._get_str(
            self.OPT_MODEL_KEY, tenant_id, DEFAULT_OPTIMIZATION_MODEL
        )

    async def set_optimization_model(self, tenant_id: str, model: str) -> None:
        await self._set_value(self.OPT_MODEL_KEY, tenant_id, model)

    # --- Optimization budget ---

    async def get_optimization_budget(self, tenant_id: Optional[str] = None) -> int:
        if not tenant_id:
            return DEFAULT_OPTIMIZATION_BUDGET
        try:
            r = await self.prompt_cache.connect()
            key = self.OPT_BUDGET_KEY.format(tenant_id=tenant_id)
            value = await r.get(key)
            if value is None:
                return DEFAULT_OPTIMIZATION_BUDGET
            return clamp_optimization_budget(int(value))
        except Exception as exc:
            logger.warning(
                "Failed to read optimization budget for %s: %s", tenant_id, exc
            )
            return DEFAULT_OPTIMIZATION_BUDGET

    async def set_optimization_budget(self, tenant_id: str, budget: int) -> None:
        clamped = clamp_optimization_budget(budget)
        await self._set_value(self.OPT_BUDGET_KEY, tenant_id, str(clamped))

    # --- Promotion threshold ---

    async def get_promotion_threshold(self, tenant_id: Optional[str] = None) -> float:
        if not tenant_id:
            return DEFAULT_PROMOTION_THRESHOLD
        try:
            r = await self.prompt_cache.connect()
            key = self.PROMOTION_THRESHOLD_KEY.format(tenant_id=tenant_id)
            value = await r.get(key)
            if value is None:
                return DEFAULT_PROMOTION_THRESHOLD
            return max(0.0, min(1.0, float(value)))
        except Exception as exc:
            logger.warning(
                "Failed to read promotion threshold for %s: %s", tenant_id, exc
            )
            return DEFAULT_PROMOTION_THRESHOLD

    async def set_promotion_threshold(self, tenant_id: str, threshold: float) -> None:
        clamped = max(0.0, min(1.0, threshold))
        await self._set_value(self.PROMOTION_THRESHOLD_KEY, tenant_id, str(clamped))

    # --- WF3 optimization schedule ---

    async def get_optimization_schedule(self, tenant_id: Optional[str] = None) -> str:
        """Get optimization schedule, falling back to PostgreSQL on Redis miss."""
        raw = await self._get_str(self.SCHEDULE_KEY, tenant_id, None)
        if raw is not None:
            return validate_schedule(raw)

        # Redis miss — try PostgreSQL fallback (US-047 AC-1)
        if tenant_id and self.db_session_factory:
            pg_value = await self._get_schedule_from_pg(tenant_id)
            if pg_value is not None:
                # Re-warm Redis cache
                await self._set_value(self.SCHEDULE_KEY, tenant_id, pg_value)
                return validate_schedule(pg_value)

        return DEFAULT_SCHEDULE

    async def set_optimization_schedule(self, tenant_id: str, schedule: str) -> None:
        """Persist schedule to Redis and PostgreSQL (US-047 AC-1)."""
        validated = validate_schedule(schedule)
        await self._set_value(self.SCHEDULE_KEY, tenant_id, validated)

        # Dual-write to PostgreSQL if db_session_factory is available
        if self.db_session_factory:
            await self._upsert_schedule_to_pg(tenant_id, validated)

    async def get_all_tenant_schedules(self) -> dict[str, str]:
        """Read all tenant schedules from Redis via SCAN (US-047 AC-2).

        Returns a dict mapping tenant_id to schedule value.
        Used by WF3 tasks to determine the most aggressive schedule.
        """
        result: dict[str, str] = {}
        try:
            r = await self.prompt_cache.connect()
            pattern = "tenant:*:config.wf3_optimization_schedule"
            async for key in r.scan_iter(match=pattern):
                # Extract tenant_id from key: tenant:{tid}:config.wf3_...
                parts = key.split(":")
                if len(parts) >= 2:
                    tid = parts[1]
                    value = await r.get(key)
                    if value:
                        result[tid] = validate_schedule(value)
        except Exception as exc:
            logger.warning("Failed to scan tenant schedules: %s", exc)
        return result

    # --- Private helpers ---

    async def _get_bool(
        self, key_template: str, tenant_id: Optional[str], default: bool
    ) -> bool:
        if not tenant_id:
            return default
        try:
            r = await self.prompt_cache.connect()
            key = key_template.format(tenant_id=tenant_id)
            value = await r.get(key)
            if value is None:
                return default
            return value.lower() in ("true", "1", "yes")
        except Exception:
            return default

    async def _get_str(
        self,
        key_template: str,
        tenant_id: Optional[str],
        default: Optional[str],
    ) -> Optional[str]:
        if not tenant_id:
            return default
        try:
            r = await self.prompt_cache.connect()
            key = key_template.format(tenant_id=tenant_id)
            value = await r.get(key)
            return value if value is not None else default
        except Exception:
            return default

    async def _set_value(self, key_template: str, tenant_id: str, value: str) -> None:
        try:
            r = await self.prompt_cache.connect()
            key = key_template.format(tenant_id=tenant_id)
            await r.set(key, value)
        except Exception as exc:
            logger.warning(
                "Failed to set tenant config %s for %s: %s",
                key_template.split(".")[-1],
                tenant_id,
                exc,
            )

    # --- PostgreSQL helpers (US-047) ---

    async def _upsert_schedule_to_pg(self, tenant_id: str, schedule: str) -> None:
        """Upsert tenant schedule to PostgreSQL source-of-truth."""
        try:
            from sqlalchemy.dialects.postgresql import insert

            from app.models.tenant_config import TenantConfig

            async with self.db_session_factory() as session:
                stmt = insert(TenantConfig).values(
                    tenant_id=tenant_id,
                    wf3_optimization_schedule=schedule,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["tenant_id"],
                    set_={"wf3_optimization_schedule": schedule},
                )
                await session.execute(stmt)
                await session.commit()
        except Exception as exc:
            logger.warning(
                "Failed to upsert schedule to PostgreSQL for %s: %s",
                tenant_id,
                exc,
            )

    async def _get_schedule_from_pg(self, tenant_id: str) -> Optional[str]:
        """Read tenant schedule from PostgreSQL fallback."""
        try:
            from sqlalchemy import select

            from app.models.tenant_config import TenantConfig

            async with self.db_session_factory() as session:
                stmt = select(TenantConfig.wf3_optimization_schedule).where(
                    TenantConfig.tenant_id == tenant_id
                )
                result = await session.execute(stmt)
                row = result.scalar_one_or_none()
                return row
        except Exception as exc:
            logger.warning(
                "Failed to read schedule from PostgreSQL for %s: %s",
                tenant_id,
                exc,
            )
            return None
