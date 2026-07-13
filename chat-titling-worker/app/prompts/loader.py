"""Lightweight prompt loader client for agent services.

This module provides a self-contained async prompt loader that agents
copy into their own codebase. It connects to Redis DB 2 (prompt cache)
and MLflow tracking server independently of the prompt-optimization-svc.

Usage in an agent service:
    loader = AgentPromptClient(redis_url="redis://redis:6379/2", mlflow_uri="http://mlflow-server:5000")
    await loader.start()
    prompt = await loader.load("zorven-<wf>-<agent>-system", tenant_id="t-1", fallback="You are...")
    await loader.stop()
"""

import asyncio
import logging
import re
from typing import Any, Optional

import httpx
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_MLFLOW_VAR_PATTERN = re.compile(r"\{\{(\w[\w.]*)\}\}")
_PLACEHOLDER_PATTERN = re.compile(r"\{([\w.]+)\}")


class AgentPromptClient:
    """Async prompt loader for agent services.

    Three-tier resolution: Redis cache -> MLflow API -> fallback.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/2",
        mlflow_uri: str = "http://mlflow-server:5000",
        default_ttl: int = 300,
        critical_agent: bool = False,
        fallback_only: bool = True,
    ) -> None:
        self.redis_url = redis_url
        self.mlflow_uri = mlflow_uri
        self.default_ttl = default_ttl
        self.critical_agent = critical_agent
        self.fallback_only = fallback_only
        self._redis: Optional[aioredis.Redis] = None
        self._http: Optional[httpx.AsyncClient] = None

    async def start(self) -> None:
        """Initialize Redis and HTTP connections."""
        try:
            self._redis = aioredis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            await asyncio.wait_for(self._redis.ping(), timeout=5.0)
            logger.info("Prompt cache connected: %s", self.redis_url)
        except Exception as exc:
            logger.warning("Prompt cache unavailable: %s", exc)
            self._redis = None

        if self.mlflow_uri:
            try:
                self._http = httpx.AsyncClient(base_url=self.mlflow_uri, timeout=5.0)
                resp = await self._http.get("/health")
                if resp.status_code == 200:
                    logger.info("Prompt service connected: %s", self.mlflow_uri)
                else:
                    logger.warning("Prompt service unhealthy (%d) — disabled", resp.status_code)
                    await self._http.aclose()
                    self._http = None
            except Exception as exc:
                logger.warning("Prompt service unavailable: %s — disabled", exc)
                if self._http:
                    await self._http.aclose()
                self._http = None
        else:
            logger.info(
                "Prompt service URI not configured — prompt loader in fallback-only mode"
            )

        logger.info(
            "Prompt loader initialized (fallback_only=%s, redis=%s, mlflow=%s)",
            self.fallback_only,
            self._redis is not None,
            self._http is not None,
        )

    async def stop(self) -> None:
        """Close connections."""
        if self._redis:
            await self._redis.aclose()
            self._redis = None
        if self._http:
            await self._http.aclose()
            self._http = None

    async def load(
        self,
        name: str,
        tenant_id: Optional[str] = None,
        variables: Optional[dict[str, Any]] = None,
        fallback: str = "",
        ttl: Optional[int] = None,
    ) -> str:
        """Load a prompt with three-tier resolution.

        Args:
            name: Prompt name (§3.1 convention).
            tenant_id: Optional tenant for override.
            variables: Template variables.
            fallback: Hardcoded fallback if all tiers fail.
            ttl: Cache TTL in seconds.

        Returns:
            Formatted prompt string.
        """
        # Fallback-only mode: bypass Redis cache and MLflow entirely.
        # Guarantees behavior identical to pre-prompt-loader code.
        if self.fallback_only:
            return self._format(fallback, variables) if fallback else ""

        resolve_ttl = self.default_ttl if ttl is None else ttl
        template = None

        # Tier 1: Redis cache
        template = await self._cache_get(name, tenant_id)
        if template is not None:
            logger.info("Loaded prompt '%s' from Redis cache (tenant=%s)", name, tenant_id)

        # Tier 2: MLflow API
        if template is None:
            template = await self._mlflow_get(name, tenant_id)
            if template is not None:
                logger.info("Loaded prompt '%s' from MLflow (tenant=%s)", name, tenant_id)
                await self._cache_set(name, template, resolve_ttl, tenant_id)

        # Tier 3: Fallback
        if template is None:
            logger.info("Prompt '%s' not found in cache/MLflow, using fallback (tenant=%s)", name, tenant_id)
            if fallback:
                if self.critical_agent:
                    logger.warning(
                        "CRITICAL AGENT FALLBACK: prompt '%s' (tenant=%s) "
                        "— MLflow and Redis both unreachable, using "
                        "hardcoded fallback.",
                        name,
                        tenant_id,
                    )
                else:
                    logger.debug("Using fallback for prompt '%s'", name)
            template = fallback

        return self._format(template, variables)

    # --- Tier 1: Redis cache ---

    async def _cache_get(self, name: str, tenant_id: Optional[str]) -> Optional[str]:
        if self._redis is None:
            return None
        try:
            if tenant_id:
                key = f"prompt:{name}:tenant:{tenant_id}"
                val = await self._redis.get(key)
                if val is not None:
                    return val
            key = f"prompt:{name}:production"
            return await self._redis.get(key)
        except Exception:
            return None

    async def _cache_set(
        self,
        name: str,
        template: str,
        ttl: int,
        tenant_id: Optional[str],
    ) -> None:
        if self._redis is None:
            return
        try:
            if tenant_id:
                key = f"prompt:{name}:tenant:{tenant_id}"
            else:
                key = f"prompt:{name}:production"
            await self._redis.set(key, template, ex=ttl)
        except Exception:
            pass

    # --- Tier 2: Prompt Optimization Service API ---

    async def _mlflow_get(self, name: str, tenant_id: Optional[str]) -> Optional[str]:
        if self._http is None:
            return None
        try:
            # Try tenant-specific prompt first
            if tenant_id:
                template = await self._fetch_prompt(name, tenant_id=tenant_id)
                if template is not None:
                    return template

            # Try base prompt (no tenant override)
            return await self._fetch_prompt(name)
        except Exception as exc:
            logger.warning("Prompt service fetch failed for '%s': %s", name, exc)
            return None

    async def _fetch_prompt(self, name: str, tenant_id: Optional[str] = None) -> Optional[str]:
        """Fetch a prompt template from the prompt-optimization-svc API.

        Calls GET /v1/prompts/{name}/production which returns the
        PRODUCTION-state template directly.
        """
        try:
            headers = {}
            if tenant_id:
                headers["X-Tenant-ID"] = str(tenant_id)

            resp = await self._http.get(
                f"/v1/prompts/{name}/production",
                headers=headers,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("template")
            return None
        except Exception:
            return None

    # --- Template formatting ---

    @staticmethod
    def _format(template: str, variables: Optional[dict[str, Any]]) -> str:
        if not template or not variables:
            return template

        converted = _MLFLOW_VAR_PATTERN.sub(r"{\1}", template)
        stringified = {k: str(v) for k, v in variables.items()}

        def _replace(match: re.Match) -> str:
            key = match.group(1)
            return stringified.get(key, match.group(0))

        return _PLACEHOLDER_PATTERN.sub(_replace, converted)
