"""Redis connection pool and key builders.

**Every key this service writes begins with ``oia:v1:``.** That is not a
stylistic choice — OIA shares DB 2 with ten other services (ERRATA-01), so the
prefix is the only thing keeping its keys from colliding with theirs.
``tests/test_redis_key_isolation.py`` enforces it structurally.

Two properties matter more because the database is shared:

- **Every key carries a TTL.** Memorystore applies ``maxmemory-policy
  allkeys-lru`` instance-wide, so an untrimmed OIA key creates eviction
  pressure on another service's data.
- **The prompt cache is read-only.** It lives in the same DB under the ``poi:``
  prefix and belongs to prompt-optimization-svc. OIA reads it; it never writes
  there.
"""

from __future__ import annotations

from typing import Final

import redis.asyncio as redis

from app.core.config import Settings

#: Namespace for every key this service owns. Changing it is a migration.
KEY_PREFIX: Final[str] = "oia:v1:"

#: Read-only namespace owned by prompt-optimization-svc, shared in DB 2.
PROMPT_CACHE_PREFIX: Final[str] = "poi:"

# Default TTLs (seconds). Nothing is written without one.
TTL_SESSION: Final[int] = 24 * 60 * 60
TTL_LIVE_FRAMES: Final[int] = 6 * 60 * 60
TTL_LOCK: Final[int] = 2 * 60 * 60
TTL_IDEMPOTENCY: Final[int] = 24 * 60 * 60
TTL_CIRCUIT: Final[int] = 5 * 60
#: The tenant config key is long-lived but still bounded — see ERRATA-01 §4.
TTL_CONFIG: Final[int] = 7 * 24 * 60 * 60


def _tenant_scope(tenant_id: str) -> str:
    if not tenant_id:
        raise ValueError("tenant_id is required — no key is built without one")
    return f"{KEY_PREFIX}{tenant_id}:"


def session_key(tenant_id: str, session_id: str) -> str:
    """Onboarding session state hash."""
    return f"{_tenant_scope(tenant_id)}session:{session_id}"


def live_frames_key(tenant_id: str, session_id: str) -> str:
    """Capped list of server → client frames backing reconnect replay."""
    return f"{_tenant_scope(tenant_id)}live:{session_id}:frames"


def live_lock_key(tenant_id: str, company_id: str) -> str:
    """Single-live-session lock (OD-5), held with a TTL so a crashed process
    cannot lock a company out permanently."""
    return f"{_tenant_scope(tenant_id)}live:lock:{company_id}"


def idempotency_key(tenant_id: str, digest: str) -> str:
    """Write-dedup marker (§18.1)."""
    return f"{_tenant_scope(tenant_id)}idem:{digest}"


def tenant_config_key(tenant_id: str) -> str:
    """Per-tenant overrides.

    ERRATA-01 §4 renamed this from ``tenant:{id}:oia:config``. On a dedicated
    database the generic ``tenant:`` root was harmless; on shared DB 2 it
    breaks the single-prefix invariant and collides with other services'
    ``tenant:``-rooted keys.
    """
    return f"{_tenant_scope(tenant_id)}config"


def circuit_key(dependency: str) -> str:
    """Circuit-breaker state for one dependency.

    Deliberately **not** tenant-scoped: a breaker tracks the health of an
    external engine, which is a property of the service, not of a tenant. It
    still carries the service prefix so another service's breaker state can
    never be read as OIA's.
    """
    if not dependency:
        raise ValueError("dependency is required")
    return f"{KEY_PREFIX}circuit:{dependency}"


class RedisManager:
    """Owns the connection pool and answers the health probe.

    Deliberately does **not** fail open. ERRATA-01 records that the fleet's
    other RedisManagers log a warning and continue with no cache when their
    database index is invalid, which is how eleven services ran cacheless and
    silently for days. A connection problem here surfaces as an unhealthy
    service instead.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: redis.Redis | None = None

    async def connect(self) -> None:
        self._client = redis.from_url(  # type: ignore[no-untyped-call]
            self._settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            raise RuntimeError("RedisManager.connect() has not been called")
        return self._client

    async def ping(self) -> bool:
        """Liveness check for /health.

        Bounded by the 2 s socket timeouts above so the probe answers within
        the 2 s budget rather than hanging (A-05 AC-3).
        """
        if self._client is None:
            return False
        try:
            return bool(await self._client.ping())
        except Exception:
            return False
