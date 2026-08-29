"""Redis connection pool and the single construction point for keys.

**Every key this service writes begins with ``oia:v1:``.** OIA shares DB 2 with
the prompt cache and the rest of the fleet (ERRATA-01), so the prefix — not a
dedicated database — is the isolation guarantee. ``tests/test_redis_key_
isolation.py`` enforces it structurally.

The tenant is a **constructor argument**, not a per-call one. A-03's technical
note is blunt about why: "a helper that can be called without a tenant will
eventually be called without one." With :class:`TenantKeys` the type checker
rejects a tenant-less key at build time rather than leaving it to a runtime
guard that a caller can forget (AC-4).

Eviction (AC-5). Session state must survive a full meeting, so it must not be
evictable. The shared Memorystore instance was measured at 7.2 MB of 1 GB
(0.7%) on 2026-08-01 and its ``maxmemory-policy`` was changed from
``allkeys-lru`` to ``noeviction`` — under ``allkeys-lru`` a memory spike would
have dropped live session state silently, mid-meeting. See CLAUDE.md.
"""

from __future__ import annotations

from typing import Final

import redis.asyncio as redis

from app.core.config import Settings

#: Namespace for every key this service owns. Changing it is a migration.
KEY_PREFIX: Final[str] = "oia:v1:"

#: Read-only namespace owned by prompt-optimization-svc, shared in DB 2.
#: POI writes prompt:{name}:production and prompt:{name}:tenant:{tid} keys.
PROMPT_CACHE_PREFIX: Final[str] = "prompt:"

# TTLs from Design §14. Nothing is written without one — on a shared instance
# an untrimmed key creates pressure on every other service's data.
TTL_SESSION: Final[int] = 4 * 60 * 60  # sliding
TTL_LIVE: Final[int] = 4 * 60 * 60
TTL_SUMMARY: Final[int] = 24 * 60 * 60
TTL_BRIEF: Final[int] = 60 * 60  # research brief (C-02)
TTL_IDEMPOTENCY: Final[int] = 24 * 60 * 60
TTL_OUTBOX: Final[int] = 24 * 60 * 60
TTL_CIRCUIT: Final[int] = 5 * 60
TTL_RATELIMIT: Final[int] = 60
TTL_LOCK: Final[int] = 2 * 60 * 60
#: §14 gives the tenant config key no TTL. ERRATA-01 §4 requires either a TTL
#: or a documented exemption once the database is shared; this is the TTL.
TTL_CONFIG: Final[int] = 7 * 24 * 60 * 60

#: §14 lists no chat key at all — C-01 introduces one, so it needs a TTL the
#: way TTL_CONFIG did. Four hours sliding, matching TTL_SESSION: a prep
#: conversation is the same span of work as the session it prepares, and the
#: card is explicit that "an untimed key on a shared Redis is a slow leak".
TTL_CHAT: Final[int] = 4 * 60 * 60
TTL_PROMPT_CACHE: Final[int] = 15 * 60  # write-through cache for POI API (L-01)

#: §14: the transcript list is capped so reconnect replay has a known worst
#: case. ~8 segments/minute means a 60-minute meeting stays under 500.
TRANSCRIPT_MAX_ENTRIES: Final[int] = 4000


class TenantKeys:
    """Builds every tenant-scoped key for one tenant.

    Constructed with a tenant id, so there is no way to ask for a key without
    one — that is AC-4's "fails at type-check time rather than at runtime".
    """

    __slots__ = ("_scope", "tenant_id")

    def __init__(self, tenant_id: str) -> None:
        if not tenant_id or not str(tenant_id).strip():
            raise ValueError("tenant_id is required — no key is built without one")
        self.tenant_id = str(tenant_id)
        self._scope = f"{KEY_PREFIX}{self.tenant_id}:"

    # ── Session state ────────────────────────────────────────
    def session(self, session_id: str) -> str:
        """Hash · 4 h sliding · mode, status, recording_id, prompt_versions."""
        return f"{self._scope}session:{session_id}"

    def session_summary(self, session_id: str) -> str:
        """String · 24 h · compressed L3 summary."""
        return f"{self._scope}session:{session_id}:summary"

    def brief(self, company_slug: str) -> str:
        """String · 1 h · a BusinessResearchBrief (C-02).

        Keyed on the *normalised* company name rather than a session or a
        chat: the card asks for "(tenant, normalised business name)" because
        an operator re-running prep for the same business — often in a new
        chat while tuning question count — should not pay for a fresh round
        of Tavily searches each time.
        """
        return f"{self._scope}brief:{company_slug}"

    def chat(self, chat_session_id: str) -> str:
        """List · 4 h sliding · prep conversation turns (C-01).

        Keyed on the *chat* session, not the onboarding session: a prep
        conversation starts before any OnboardingSession exists, which is the
        whole point of preparing in the chat the operator already uses.
        """
        return f"{self._scope}chat:{chat_session_id}"

    # ── Live meeting ─────────────────────────────────────────
    def transcript(self, session_id: str) -> str:
        """List · 4 h · finalized redacted segments, capped, replay source."""
        return f"{self._scope}live:{session_id}:transcript"

    def questions(self, session_id: str) -> str:
        """Hash · 4 h · question_id → status/score/evidence/override."""
        return f"{self._scope}live:{session_id}:questions"

    def coverage(self, session_id: str) -> str:
        """Hash · 4 h · WF1/WF2/WF3 fractions plus updated_at."""
        return f"{self._scope}live:{session_id}:coverage"

    def live_frames(self, session_id: str) -> str:
        """List · 4 h · the replay buffer behind a reconnect (F-04 AC-3).

        Capped by count, not by bytes. AC-3 is about how far back a client can
        resume, and "the last N frames" is a resume window an operator can
        reason about where "the last N kilobytes" is not.

        In Redis because it has to be: spike A-02 finding 3 puts sockets for
        one tenant on different Cloud Run instances, so a reconnect usually
        lands somewhere that never saw the frames it is asking to replay.
        """
        return f"{self._scope}live:{session_id}:frames"

    def unmapped(self, session_id: str) -> str:
        """List · 4 h · transcript batches that mapped to no question (G-05)."""
        return f"{self._scope}live:{session_id}:unmapped"

    def live_seq(self, session_id: str) -> str:
        """String · 4 h · the monotonic counter behind AC-4.

        Separate from the buffer so the series survives the buffer being
        trimmed: seq must be "strictly increasing for the life of the session
        across all frame types", and a counter derived from the buffer's length
        would restart every time the cap evicted a frame.
        """
        return f"{self._scope}live:{session_id}:seq"

    def live_lock(self, company_id: str) -> str:
        """String · 2 h · one live meeting per company (OD-5).

        Keyed on company, not session: keying it on the session would make
        the lock trivially satisfiable by opening a second session.
        """
        return f"{self._scope}lock:live:{company_id}"

    # ── Write safety ─────────────────────────────────────────
    def idempotency(self, digest: str) -> str:
        """String · 24 h · write dedup, value is the original response."""
        return f"{self._scope}idempotency:{digest}"

    def outbox(self, session_id: str) -> str:
        """List · 24 h · Django writes buffered while the backend breaker is open."""
        return f"{self._scope}outbox:{session_id}"

    # ── Tenant control ───────────────────────────────────────
    def ratelimit(self, user_id: str) -> str:
        """Counter · 1 min · PREP 10/min per user, WS control-frame throttle."""
        return f"{self._scope}ratelimit:{user_id}"

    def retry_queue(self, queue_name: str) -> str:
        """Sorted set · OCR retry queue, scored by next-attempt timestamp."""
        return f"{self._scope}retry:{queue_name}"

    def prompt_cache(self, prompt_name: str) -> str:
        """String · 15 min · OIA's write-through cache of a POI API response."""
        return f"{self._scope}prompt_cache:{prompt_name}"

    def config(self) -> str:
        """Hash · tenant overrides.

        ERRATA-01 §4 renamed this from ``tenant:{id}:oia:config``: on a shared
        database the generic ``tenant:`` root breaks the single-prefix
        invariant and collides with other services' ``tenant:``-rooted keys.
        """
        return f"{self._scope}config"


def circuit_key(dependency: str) -> str:
    """Hash · 5 min · breaker state for one dependency.

    Deliberately **not** tenant-scoped and therefore not on :class:`TenantKeys`:
    Google STT being down is not a per-tenant condition, and a per-tenant
    breaker would require every tenant to discover the outage independently
    before protecting itself. It still carries the service prefix so another
    service's breaker state can never be read as OIA's.
    """
    if not dependency or not dependency.strip():
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
        self._client = redis.Redis.from_url(
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

    def keys_for(self, tenant_id: str) -> TenantKeys:
        """The only way to obtain tenant-scoped key builders."""
        return TenantKeys(tenant_id)

    async def ping(self) -> bool:
        """Liveness check for /health, bounded by the 2 s socket timeouts."""
        if self._client is None:
            return False
        try:
            return bool(await self._client.ping())
        except Exception:
            return False

    async def eviction_policy(self) -> str | None:
        """Report ``maxmemory-policy`` as the server actually has it (AC-5).

        Returns ``None`` when the server refuses CONFIG GET — managed Redis
        sometimes restricts it — so callers can distinguish "not noeviction"
        from "could not determine", which are different operational states.
        """
        if self._client is None:
            return None
        try:
            config = await self._client.config_get("maxmemory-policy")
            policy = config.get("maxmemory-policy")
            return str(policy) if policy is not None else None
        except Exception:
            return None

    async def scan_prefix(self, prefix: str, limit: int = 1000) -> list[str]:
        """Return keys under ``prefix``. Used by the isolation test."""
        if self._client is None:
            return []
        found: list[str] = []
        async for key in self._client.scan_iter(match=f"{prefix}*", count=100):
            found.append(key)
            if len(found) >= limit:
                break
        return found
