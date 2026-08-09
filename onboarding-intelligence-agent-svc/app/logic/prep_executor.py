"""PREP mode orchestration.

Design §9.1, §2.1 · implemented by story C-02.

Scaffolded by A-05 with a docstring naming C-01 as the implementer. C-01
delivered the envelope, the auth and the conversation store, and wired
``/v1/execute`` straight to the store because no PREP skill had a body yet —
the endpoint honestly returned ``skill_id: "NONE"``. C-02 gives SKL-OIA-01 a
body, so the route now needs something that turns a turn into a skill call.

The executor owns the registry rather than the route handler, because it also
owns two things the handler should not know about: which skill a PREP turn
maps to, and the research-brief cache. Both are decisions that will change as
C-03 and C-04 land, and neither belongs in an HTTP layer.
"""

from __future__ import annotations

import json
from typing import Any

from app.cache.redis_manager import TTL_BRIEF, RedisManager
from app.core.logging import get_logger
from app.logic.grounding import RULE_ID as OG_01
from app.logic.grounding import ground_output
from app.logic.guardrails import Layer
from app.providers.llm import LLMProvider
from app.providers.tavily import TavilyProvider
from app.skills.models import Origin, SkillContext, TenantContext
from app.skills.registry import SkillRegistry
from app.skills.research_business import normalise_company_name

logger = get_logger(__name__)

RESEARCH_SKILL = "SKL-OIA-01"

# TTL_BRIEF is one hour, declared beside the other TTLs in redis_manager. The
# card asks for "a short TTL" because "operators re-run prep several times
# while tuning question count, and each re-run is otherwise a fresh round of
# paid search". Tuning cycles are minutes; a business's public footprint does
# not move within the hour, and a stale brief is worse than a paid search once
# it does.


class PrepExecutor:
    """Runs one PREP turn.

    Constructed once at startup and held on ``app.state``: loading the
    registry parses YAML and imports sixteen modules, which is startup work,
    not per-request work.
    """

    def __init__(
        self,
        redis: RedisManager,
        *,
        tavily: TavilyProvider | None = None,
        llm: LLMProvider | None = None,
        registry: SkillRegistry | None = None,
    ) -> None:
        self._redis = redis
        self._registry = registry or self._build_registry(tavily, llm)

    @staticmethod
    def _build_registry(
        tavily: TavilyProvider | None, llm: LLMProvider | None
    ) -> SkillRegistry:
        """Load the sixteen skills and install the real OG-01.

        The grounding rule is registered here rather than inside the chain's
        defaults so A-06's "every rule starts as a recorded no-op" property
        survives: the chain is still complete and ordered on construction, and
        this replaces one body in place. That is exactly the mechanism
        ``register`` documents, and M-01 will use it for the rest.
        """
        registry = SkillRegistry(providers={"tavily": tavily, "llm": llm})
        registry.load()
        registry.chain.register(Layer.OUTPUT, OG_01, ground_output)
        return registry

    @property
    def registry(self) -> SkillRegistry:
        return self._registry

    # ── The research brief ───────────────────────────────────────────

    def _brief_key(self, tenant_id: str, company_name: str) -> str:
        """``(tenant, normalised business name)``, per the card.

        Built through ``TenantKeys`` so a tenant-less key cannot be written —
        A-03's rule, and the reason the tenant is a constructor argument
        there rather than a parameter here.
        """
        slug = normalise_company_name(company_name) or "unnamed"
        return self._redis.keys_for(tenant_id).brief(slug)

    async def cached_brief(
        self, tenant_id: str, company_name: str
    ) -> dict[str, Any] | None:
        """A previous brief for this business, if one is still warm."""
        raw = await self._redis.client.get(self._brief_key(tenant_id, company_name))
        if not raw:
            return None
        try:
            brief = json.loads(raw)
        except ValueError:
            # A corrupt entry should cost a re-run, not the turn.
            logger.warning("discarding an unparseable cached brief")
            return None
        return brief if isinstance(brief, dict) else None

    async def store_brief(
        self, tenant_id: str, company_name: str, brief: dict[str, Any]
    ) -> None:
        """Cache a brief — unless it is degraded.

        A degraded brief is the *absence* of research. Caching it would mean a
        one-minute Tavily outage silently suppresses real research for the
        next hour, and the operator would have no way to tell why their
        questions stayed thin.
        """
        if brief.get("degraded"):
            return
        await self._redis.client.set(
            self._brief_key(tenant_id, company_name),
            json.dumps(brief, separators=(",", ":")),
            ex=TTL_BRIEF,
        )

    # ── One turn ─────────────────────────────────────────────────────

    async def research(
        self,
        *,
        tenant: TenantContext,
        input_context: dict[str, Any],
        input_prompt: str,
        correlation_id: str = "",
        use_cache: bool = True,
    ) -> tuple[dict[str, Any], bool]:
        """Run SKL-OIA-01, returning ``(brief, came_from_cache)``.

        The cache is consulted before the skill, not inside it: a skill that
        silently returns cached data cannot be tested for what it does, and
        AC-2's "available without re-running research" is a property of the
        turn rather than of the research itself.
        """
        company_name = str(input_context.get("company_name") or "").strip()

        if use_cache and company_name:
            cached = await self.cached_brief(tenant.tenant_id, company_name)
            if cached is not None:
                logger.info("research_brief_cache_hit", company=company_name)
                return cached, True

        context = SkillContext(
            input_prompt=input_prompt,
            tenant_context=tenant,
            input_context=dict(input_context),
            correlation_id=correlation_id,
            origin=Origin.EXTERNAL,
        )
        result = await self._registry.execute(RESEARCH_SKILL, context)

        if company_name:
            await self.store_brief(tenant.tenant_id, company_name, result.output)

        return result.output, False
