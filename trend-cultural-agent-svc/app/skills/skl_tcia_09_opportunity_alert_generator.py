"""SKL-TCIA-09: Opportunity Alert Generator.

Generates opportunity alerts for trends scoring above the threshold.
"""

import logging
import time
import uuid
from typing import Any

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)


class OpportunityAlertGenerator(BaseSkill):
    """Generate opportunity alerts for high-scoring trends."""

    meta = SkillMeta(
        skill_id="SKL-TCIA-09",
        name="opportunity_alert_generator",
        description="Generate opportunity alerts for trends above threshold",
        allowed_roles=["OWNER", "ADMIN", "EDITOR"],
        timeout_ms=30000,
        circuit_breaker_dependency="llm",
    )

    def __init__(
        self, anthropic_client: Any = None, cb_llm: Any = None
    ) -> None:
        self._anthropic = anthropic_client
        self._cb_llm = cb_llm

    async def execute(
        self, input_data: dict[str, Any], context: SkillContext
    ) -> SkillResult:
        start = time.monotonic()

        scored_trends = input_data.get("scored_trends", [])
        trend_persona_matrix = input_data.get("trend_persona_matrix", {})
        alert_threshold = input_data.get("alert_threshold", 75)

        alerts: list[dict[str, Any]] = []
        mappings = trend_persona_matrix.get("mappings", [])

        for trend in scored_trends:
            score = trend.get("relevance_score", 0)
            if score < alert_threshold:
                continue

            trend_slug = trend.get("trend_slug", "")
            affected_personas = [
                m.get("persona_slug", "")
                for m in mappings
                if m.get("trend_slug") == trend_slug
                and m.get("affinity_score", 0) > 0.5
            ]

            urgency = "this_month"
            if score >= 90:
                urgency = "immediate"
            elif score >= 80:
                urgency = "this_week"

            alert = {
                "alert_id": str(uuid.uuid4()),
                "trend_slug": trend_slug,
                "relevance_score": score,
                "urgency": urgency,
                "recommendation": trend.get("recommendation", "monitor"),
                "affected_personas": affected_personas,
                "suggested_response": trend.get("rationale", ""),
                "expiry_estimate": "",
            }
            alerts.append(alert)

        elapsed = (time.monotonic() - start) * 1000
        return SkillResult(
            skill_id=self.meta.skill_id,
            success=True,
            data={"opportunity_alerts": alerts},
            duration_ms=elapsed,
        )
