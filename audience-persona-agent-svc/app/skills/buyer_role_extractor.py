"""SKL-APA-04: Buyer Role Extractor — B2B buying committee roles."""

import logging
import time
from typing import Any

from app.services.api_clients import TavilySearchClient
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)


class BuyerRoleExtractor(BaseSkill):
    """Identify B2B buying committee roles and decision-making patterns."""

    meta = SkillMeta(
        skill_id="SKL-APA-04",
        name="buyer_role_extractor",
        description=(
            "Identify decision makers, influencers, champions, blockers, "
            "and end users in B2B buying committees."
        ),
        allowed_roles=["OWNER", "ADMIN", "EDITOR", "VIEWER"],
        timeout_ms=45000,
        circuit_breaker_dependency="tavily",
    )

    def __init__(self, tavily_client: TavilySearchClient) -> None:
        self.tavily_client = tavily_client

    async def execute(self, input_data: dict, context: SkillContext) -> SkillResult:
        """
        Extract buyer roles from web research.

        input_data keys:
          - prompt (str): User's analysis query
        """
        start = time.monotonic()
        prompt = input_data.get("prompt", "")

        if not prompt:
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error="No query provided",
                duration_ms=_elapsed(start),
            )

        # Buyer role queries
        search_queries = [
            f"{prompt} buying committee decision makers",
            f"{prompt} B2B purchase decision process stakeholders",
            f"{prompt} buyer roles influencers champions end users",
        ]

        all_results: list[dict[str, Any]] = []
        sources: list[dict[str, str]] = []

        for query in search_queries:
            results = await self.tavily_client.search(query, max_results=5)
            for r in results:
                all_results.append(r)
                url = r.get("url", "")
                if url:
                    sources.append(
                        {
                            "type": "web",
                            "title": r.get("title", ""),
                            "url": url,
                        }
                    )

        # Extract buyer roles
        buyer_roles = _extract_buyer_roles(all_results)

        # Build context
        context_parts = []
        for r in all_results:
            content = r.get("content", "")
            if content:
                context_parts.append(content[:400])

        raw_context = "\n\n".join(context_parts)

        logger.info(
            "Buyer role extraction: %d results, %d roles identified",
            len(all_results),
            len(buyer_roles),
        )

        return SkillResult(
            skill_id=self.meta.skill_id,
            success=True,
            data={
                "context": raw_context[:15000],
                "sources": sources,
                "buyer_roles": buyer_roles,
            },
            duration_ms=_elapsed(start),
        )


def _extract_buyer_roles(results: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Extract buyer committee roles from search results."""
    role_keywords = {
        "decision_maker": [
            "decision maker",
            "executive",
            "c-suite",
            "ceo",
            "cto",
            "cfo",
            "vp",
            "vice president",
            "director",
            "head of",
        ],
        "influencer": [
            "influencer",
            "consultant",
            "advisor",
            "analyst",
            "thought leader",
            "subject matter expert",
        ],
        "champion": [
            "champion",
            "advocate",
            "internal sponsor",
            "project lead",
            "initiative owner",
        ],
        "blocker": [
            "blocker",
            "gatekeeper",
            "procurement",
            "legal",
            "compliance",
            "risk",
            "security",
        ],
        "end_user": [
            "end user",
            "user",
            "operator",
            "practitioner",
            "team member",
            "individual contributor",
        ],
    }

    roles: list[dict[str, str]] = []
    seen_roles: set[str] = set()

    for result in results:
        content = (result.get("content", "") + " " + result.get("title", "")).lower()
        for role_type, keywords in role_keywords.items():
            if role_type in seen_roles:
                continue
            for kw in keywords:
                if kw in content:
                    idx = content.find(kw)
                    snippet_start = max(0, idx - 30)
                    snippet_end = min(len(content), idx + 120)
                    snippet = content[snippet_start:snippet_end].strip()
                    seen_roles.add(role_type)
                    roles.append(
                        {
                            "role": role_type,
                            "evidence": snippet[:200],
                        }
                    )
                    break

    return roles


def _elapsed(start: float) -> float:
    return (time.monotonic() - start) * 1000
