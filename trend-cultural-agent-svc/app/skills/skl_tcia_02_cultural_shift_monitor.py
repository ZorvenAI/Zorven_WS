"""SKL-TCIA-02: Cultural Shift Monitor.

Monitors macro-level cultural shifts across domains via Tavily search.
"""

import logging
import time
from typing import Any

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)


class CulturalShiftMonitor(BaseSkill):
    """Monitor macro-level cultural shifts relevant to the brand."""

    meta = SkillMeta(
        skill_id="SKL-TCIA-02",
        name="cultural_shift_monitor",
        description="Monitor cultural shifts across domains",
        allowed_roles=["OWNER", "ADMIN", "EDITOR", "VIEWER"],
        timeout_ms=60000,
        circuit_breaker_dependency="tavily",
    )

    def __init__(self, tavily_client: Any, cb_tavily: Any = None) -> None:
        self._tavily = tavily_client
        self._cb_tavily = cb_tavily

    async def execute(
        self, input_data: dict[str, Any], context: SkillContext
    ) -> SkillResult:
        start = time.monotonic()
        industry = input_data.get("industry", "")
        cultural_domains = input_data.get(
            "cultural_domains",
            ["values", "lifestyle", "work", "sustainability", "tech_adoption"],
        )

        cultural_shifts: list[dict[str, Any]] = []

        for domain in cultural_domains:
            query = (
                f"cultural shift {domain} {industry} "
                f"consumer behavior change 2025 2026"
            )
            try:
                if self._cb_tavily:
                    results = await self._cb_tavily.call(
                        self._tavily.search, query, max_results=5
                    )
                else:
                    results = await self._tavily.search(query, max_results=5)

                for r in results:
                    cultural_shifts.append(
                        {
                            "domain": domain,
                            "shift_description": r.get("content", "")[:500],
                            "evidence_strength": 0.6,
                            "affected_demographics": [],
                            "timeline_estimate": "",
                            "sources": [
                                {
                                    "title": r.get("title", ""),
                                    "url": r.get("url", ""),
                                }
                            ],
                        }
                    )
            except Exception as exc:
                logger.warning("Cultural shift scan failed for %s: %s", domain, exc)

        elapsed = (time.monotonic() - start) * 1000
        return SkillResult(
            skill_id=self.meta.skill_id,
            success=True,
            data={"cultural_shifts": cultural_shifts},
            duration_ms=elapsed,
        )
