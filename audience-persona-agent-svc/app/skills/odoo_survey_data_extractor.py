"""SKL-APA-05b: Odoo Survey Data Extractor — Survey responses via XML-RPC."""

import logging
import time
from typing import Any

from app.cache.redis_manager import RedisManager
from app.services.odoo_rpc_client import OdooRPCClient
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)


class OdooSurveyDataExtractor(BaseSkill):
    """Extract survey responses from Odoo for audience profiling."""

    meta = SkillMeta(
        skill_id="SKL-APA-05b",
        name="odoo_survey_data_extractor",
        description=(
            "Extract survey responses via Odoo XML-RPC. Aggregates "
            "demographics, satisfaction scores, and NPS from survey data."
        ),
        allowed_roles=["OWNER", "ADMIN", "EDITOR"],
        timeout_ms=45000,
        circuit_breaker_dependency="odoo_survey",
    )

    def __init__(
        self,
        odoo_client: OdooRPCClient,
        redis_manager: RedisManager,
    ) -> None:
        self.odoo_client = odoo_client
        self.redis_manager = redis_manager

    async def execute(self, input_data: dict, context: SkillContext) -> SkillResult:
        """
        Extract survey data from Odoo.

        input_data keys:
          - prompt (str): Analysis query
        """
        start = time.monotonic()
        tenant_id = context.tenant_id

        # Check cache first
        cached = await self.redis_manager.get_odoo_survey_cache(tenant_id, "all")
        if cached:
            logger.info("Using cached survey data for tenant %s", tenant_id)
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data=cached,
                duration_ms=_elapsed(start),
            )

        try:
            # Fetch surveys
            surveys = await self.odoo_client.search_read(
                "survey.survey",
                domain=[("state", "=", "open")],
                fields=["id", "title", "description"],
                limit=20,
            )

            if not surveys:
                return SkillResult(
                    skill_id=self.meta.skill_id,
                    success=True,
                    data={
                        "context": "No survey data available in Odoo",
                        "sources": [
                            {"type": "odoo", "title": "Odoo Surveys", "url": ""}
                        ],
                        "survey_data": {},
                    },
                    duration_ms=_elapsed(start),
                )

            survey_ids = [s["id"] for s in surveys]

            # Fetch survey responses
            responses = await self.odoo_client.search_read(
                "survey.user_input",
                domain=[
                    ("survey_id", "in", survey_ids),
                    ("state", "=", "done"),
                ],
                fields=["id", "survey_id", "create_date", "scoring_total"],
                limit=500,
            )

            # Fetch response lines for detail
            response_ids = [r["id"] for r in responses]
            lines = []
            if response_ids:
                lines = await self.odoo_client.search_read(
                    "survey.user_input_line",
                    domain=[("user_input_id", "in", response_ids[:200])],
                    fields=[
                        "user_input_id",
                        "question_id",
                        "value_text",
                        "value_number",
                        "value_suggested_row",
                    ],
                    limit=2000,
                )

            # Aggregate survey data
            survey_data = _aggregate_survey_data(surveys, responses, lines)

            # Build context
            context_parts = [
                f"Odoo Survey Data ({len(surveys)} surveys, {len(responses)} responses):",
            ]
            for survey in surveys:
                resp_count = sum(
                    1 for r in responses if r.get("survey_id", [0])[0] == survey["id"]
                )
                context_parts.append(
                    f"- {survey.get('title', 'Untitled')}: {resp_count} responses"
                )

            raw_context = "\n".join(context_parts)

            result_data = {
                "context": raw_context[:5000],
                "sources": [{"type": "odoo", "title": "Odoo Surveys", "url": ""}],
                "survey_data": survey_data,
            }

            # Cache the result
            await self.redis_manager.set_odoo_survey_cache(
                tenant_id, "all", result_data
            )

            logger.info(
                "Extracted survey data: %d surveys, %d responses",
                len(surveys),
                len(responses),
            )

            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data=result_data,
                duration_ms=_elapsed(start),
            )

        except Exception as exc:
            logger.warning("Odoo survey extraction failed: %s", exc)
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error=str(exc),
                duration_ms=_elapsed(start),
            )


def _aggregate_survey_data(
    surveys: list[dict],
    responses: list[dict],
    lines: list[dict],
) -> dict[str, Any]:
    """Aggregate survey responses into demographic/satisfaction summaries."""
    total_responses = len(responses)
    scores = [r.get("scoring_total", 0) for r in responses if r.get("scoring_total")]

    avg_score = sum(scores) / len(scores) if scores else 0.0

    # Count text responses for keyword extraction
    text_responses = [
        line.get("value_text", "") for line in lines if line.get("value_text")
    ]

    return {
        "total_surveys": len(surveys),
        "total_responses": total_responses,
        "average_score": round(avg_score, 2),
        "text_response_count": len(text_responses),
        "survey_titles": [s.get("title", "") for s in surveys],
    }


def _elapsed(start: float) -> float:
    return (time.monotonic() - start) * 1000
