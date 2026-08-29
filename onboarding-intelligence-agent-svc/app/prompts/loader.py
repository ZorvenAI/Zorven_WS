"""Four-step prompt resolution chain.

Design §17.2 · implemented by story L-01.

Steps, per prompt_id (stops at first hit):
  1. Redis tenant variant:  ``prompt:{poi_name}:tenant:{tenant_id}``  (read-only)
  2. Redis platform default: ``prompt:{poi_name}:production``          (read-only)
  3. OIA cache → POI API:    ``oia:v1:{tenant}:prompt_cache:{poi_name}`` (15 min TTL)
  4. Hardcoded fallback from ``fallbacks.py``

Steps 1–2 read keys written by POI. OIA never writes under the ``prompt:``
prefix; the write-through cache in step 3 uses OIA's own ``oia:v1:`` prefix.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from app.cache.redis_manager import (
    PROMPT_CACHE_PREFIX,
    TTL_PROMPT_CACHE,
    RedisManager,
)
from app.circuit_breaker.breaker import CircuitBreaker
from app.core.logging import get_logger
from app.prompts.fallbacks import get_fallback_prompts, get_fallback_versions
from app.prompts.mapping import poi_name
from app.services.poi_client import POIClient

logger = get_logger(__name__)

ResolutionTier = Literal["redis_tenant", "redis_production", "poi_api", "fallback"]


@dataclass(frozen=True)
class ResolvedPrompt:
    """A single resolved prompt with its template, version, and origin."""

    template: str
    version: str
    tier: ResolutionTier


class PromptLoader:
    """Resolves and optionally caches prompt versions for a session."""

    def __init__(
        self,
        redis: RedisManager,
        poi_client: POIClient,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        self._redis = redis
        self._poi = poi_client
        self._breaker = breaker

    async def resolve_for_session(
        self,
        prompt_ids: Iterable[str],
        tenant_id: str,
    ) -> tuple[dict[str, ResolvedPrompt], bool]:
        """Resolve each prompt through the four-step chain.

        Returns ``(resolved_map, is_degraded)`` where ``is_degraded`` is
        True only when every prompt fell through to step 4.
        """
        ids = list(prompt_ids)
        if not ids:
            return {}, False

        poi_names = {pid: poi_name(pid) for pid in ids}

        # Steps 1–2: MGET all tenant + production keys in one round-trip
        tenant_keys = [
            f"{PROMPT_CACHE_PREFIX}{pn}:tenant:{tenant_id}" for pn in poi_names.values()
        ]
        production_keys = [
            f"{PROMPT_CACHE_PREFIX}{pn}:production" for pn in poi_names.values()
        ]

        all_keys = tenant_keys + production_keys
        raw_values = await self._redis.client.mget(all_keys)

        tenant_values = raw_values[: len(ids)]
        production_values = raw_values[len(ids) :]

        fallback_templates = get_fallback_prompts()
        fallback_versions = get_fallback_versions()

        resolved: dict[str, ResolvedPrompt] = {}
        fallback_count = 0

        for i, pid in enumerate(ids):
            pn = poi_names[pid]

            # Step 1: tenant variant
            tv = tenant_values[i]
            if tv and isinstance(tv, str):
                version = self._extract_version(tv)
                resolved[pid] = ResolvedPrompt(
                    template=tv, version=version, tier="redis_tenant"
                )
                continue

            # Step 2: platform default
            pv = production_values[i]
            if pv and isinstance(pv, str):
                version = self._extract_version(pv)
                resolved[pid] = ResolvedPrompt(
                    template=pv, version=version, tier="redis_production"
                )
                continue

            # Step 3: OIA cache, then POI API
            cached = await self._check_oia_cache(tenant_id, pn)
            if cached is not None:
                resolved[pid] = ResolvedPrompt(
                    template=cached[0], version=cached[1], tier="poi_api"
                )
                continue

            api_result = await self._poi.get_production(pn, tenant_id=tenant_id)
            if api_result is not None:
                template, version = api_result
                await self._write_oia_cache(tenant_id, pn, template, version)
                resolved[pid] = ResolvedPrompt(
                    template=template, version=version, tier="poi_api"
                )
                continue

            # Step 4: hardcoded fallback
            resolved[pid] = ResolvedPrompt(
                template=fallback_templates.get(pid, ""),
                version=fallback_versions.get(pid, "fallback-v1"),
                tier="fallback",
            )
            fallback_count += 1

        is_degraded = fallback_count == len(ids)

        tiers = {pid: r.tier for pid, r in resolved.items()}
        logger.info(
            "prompt_resolution_complete",
            tenant_id=tenant_id,
            count=len(ids),
            fallback_count=fallback_count,
            degraded=is_degraded,
            tiers=tiers,
        )

        return resolved, is_degraded

    async def _check_oia_cache(
        self, tenant_id: str, prompt_name: str
    ) -> tuple[str, str] | None:
        """Read from OIA's own write-through cache."""
        keys = self._redis.keys_for(tenant_id)
        key = keys.prompt_cache(prompt_name)
        raw = await self._redis.client.get(key)
        if raw and isinstance(raw, str):
            try:
                data = json.loads(raw)
                if isinstance(data, dict):
                    t = data.get("template")
                    v = data.get("version")
                    if t and v:
                        return str(t), str(v)
            except (json.JSONDecodeError, TypeError):
                pass
        return None

    async def _write_oia_cache(
        self, tenant_id: str, prompt_name: str, template: str, version: str
    ) -> None:
        """Write to OIA's own cache under oia:v1: prefix."""
        keys = self._redis.keys_for(tenant_id)
        key = keys.prompt_cache(prompt_name)
        payload = json.dumps({"template": template, "version": version})
        await self._redis.client.set(key, payload, ex=TTL_PROMPT_CACHE)

    @staticmethod
    def _extract_version(cached_value: str) -> str:
        """Extract version from a POI-cached value.

        POI stores the raw template string in its cache keys. The version
        is not embedded in the cached value — it comes from the MLflow
        tag. When reading from POI's Redis cache directly (steps 1–2),
        the version is unknown so we mark it as from the cache tier.
        """
        return "redis-cached"
