"""SKL-VoCA-02: Odoo Survey Response Extractor.

Reads survey.survey, survey.user_input, survey.user_input_line, and
survey.question to extract customer survey responses.  Automatically
detects NPS questions by looking for ``numerical_box`` questions whose
constraints satisfy ``constr_min=0`` and ``constr_max=10``.

Returns a SurveyFeedbackProfile containing both NPS and non-NPS feedback,
with customer IDs SHA-256 hashed (Decision #5).
"""

import logging
import time
from typing import Any

from app.cache.redis_manager import RedisManager
from app.registry.models import (
    FeedbackChannel,
    SurveyFeedback,
    SurveyFeedbackProfile,
    hash_customer_id,
)
from app.services.odoo_rpc_client import OdooRPCClient
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)

# NPS detection: numerical_box with 0-10 scale
_NPS_QUESTION_TYPE = "numerical_box"
_NPS_MIN = 0
_NPS_MAX = 10


class OdooSurveyExtractor(BaseSkill):
    """Extract survey responses from Odoo with NPS auto-detection."""

    meta = SkillMeta(
        skill_id="SKL-VoCA-02",
        name="odoo_survey_extractor",
        description=(
            "Extract survey responses via Odoo XML-RPC. Auto-detects NPS "
            "questions (numerical_box with 0-10 scale). Returns a "
            "SurveyFeedbackProfile with NPS/non-NPS separation."
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

    # ── Execute ──

    async def execute(
        self, input_data: dict[str, Any], context: SkillContext
    ) -> SkillResult:
        """
        Extract survey data from Odoo with NPS detection.

        input_data keys:
          - prompt (str): analysis query (unused but forwarded for tracing)
          - limit (int, optional): max survey responses (default 500)
        """
        start = time.monotonic()
        tenant_id = context.tenant_id

        # ── Cache check ──
        cached = await self.redis_manager.get_odoo_cache(
            tenant_id, "survey_cache", "all"
        )
        if cached:
            logger.info("Using cached survey data for tenant %s", tenant_id)
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data=cached,
                duration_ms=_elapsed(start),
            )

        try:
            # ── Fetch surveys ──
            surveys = await self.odoo_client.search_read(
                "survey.survey",
                domain=[("state", "=", "open")],
                fields=["id", "title", "description"],
                limit=50,
            )

            if not surveys:
                empty_profile = SurveyFeedbackProfile()
                result_data = _build_result(empty_profile, "No surveys in Odoo")
                return SkillResult(
                    skill_id=self.meta.skill_id,
                    success=True,
                    data=result_data,
                    duration_ms=_elapsed(start),
                )

            survey_ids = [s["id"] for s in surveys]

            # ── Fetch questions (for NPS detection) ──
            questions = await self.odoo_client.search_read(
                "survey.question",
                domain=[("survey_id", "in", survey_ids)],
                fields=[
                    "id",
                    "title",
                    "question_type",
                    "constr_min_value",
                    "constr_max_value",
                    "survey_id",
                ],
                limit=500,
            )

            nps_question_ids = _detect_nps_questions(questions)

            # ── Fetch responses ──
            limit = input_data.get("limit", 500)
            responses = await self.odoo_client.search_read(
                "survey.user_input",
                domain=[
                    ("survey_id", "in", survey_ids),
                    ("state", "=", "done"),
                ],
                fields=[
                    "id",
                    "survey_id",
                    "partner_id",
                    "create_date",
                    "scoring_total",
                ],
                limit=limit,
            )

            # ── Fetch response lines ──
            response_ids = [r["id"] for r in responses]
            lines: list[dict[str, Any]] = []
            if response_ids:
                lines = await self.odoo_client.search_read(
                    "survey.user_input_line",
                    domain=[("user_input_id", "in", response_ids[:500])],
                    fields=[
                        "id",
                        "user_input_id",
                        "question_id",
                        "value_text",
                        "value_number",
                        "value_suggested_row",
                    ],
                    limit=5000,
                )

            # ── Build question lookup ──
            question_map = {q["id"]: q for q in questions}

            # ── Build survey title lookup ──
            survey_title_map = {s["id"]: s.get("title", "") for s in surveys}

            # ── Transform to SurveyFeedback items ──
            nps_responses: list[SurveyFeedback] = []
            non_nps_responses: list[SurveyFeedback] = []

            # Group lines by user_input_id
            lines_by_input: dict[int, list[dict[str, Any]]] = {}
            for line in lines:
                uid = line.get("user_input_id")
                if isinstance(uid, (list, tuple)):
                    uid = uid[0]
                lines_by_input.setdefault(uid, []).append(line)

            for resp in responses:
                resp_id = resp["id"]
                partner_id = _extract_partner_id(resp)
                customer_hash = (
                    hash_customer_id(partner_id, salt=tenant_id) if partner_id else ""
                )

                # Store hash lookup
                if partner_id:
                    await self.redis_manager.store_hash_lookup(
                        tenant_id, customer_hash, str(partner_id)
                    )

                survey_id = resp.get("survey_id")
                if isinstance(survey_id, (list, tuple)):
                    survey_id = survey_id[0]

                survey_title = survey_title_map.get(survey_id, "")

                resp_lines = lines_by_input.get(resp_id, [])

                for line in resp_lines:
                    question_id = line.get("question_id")
                    if isinstance(question_id, (list, tuple)):
                        question_id = question_id[0]

                    q_info = question_map.get(question_id, {})
                    q_title = q_info.get("title", "")
                    is_nps = question_id in nps_question_ids

                    # Determine answer text and score
                    answer_text = line.get("value_text", "") or ""
                    score = line.get("value_number")

                    feedback = SurveyFeedback(
                        feedback_id=f"odoo-survey-line-{line.get('id', 0)}",
                        channel=FeedbackChannel.ODOO_SURVEY,
                        customer_id_hash=customer_hash,
                        text=answer_text[:5000],
                        timestamp=resp.get("create_date", ""),
                        survey_id=survey_id or 0,
                        survey_title=survey_title,
                        question=q_title,
                        answer=answer_text[:2000],
                        score=float(score) if score is not None else None,
                        is_nps_response=is_nps,
                    )

                    if is_nps:
                        nps_responses.append(feedback)
                    else:
                        non_nps_responses.append(feedback)

            # ── Build profile ──
            nps_confidence = _compute_nps_confidence(
                nps_question_ids, questions, nps_responses
            )

            profile = SurveyFeedbackProfile(
                survey_count=len(surveys),
                response_count=len(responses),
                nps_questions_detected=len(nps_question_ids),
                nps_responses=nps_responses,
                nps_detection_confidence=nps_confidence,
                non_nps_responses=non_nps_responses,
            )

            # ── Build context summary ──
            summary_parts = [
                f"Odoo Survey Data: {len(surveys)} surveys, "
                f"{len(responses)} responses",
                f"NPS questions detected: {len(nps_question_ids)} "
                f"(confidence: {nps_confidence:.2f})",
                f"NPS responses: {len(nps_responses)}, "
                f"non-NPS responses: {len(non_nps_responses)}",
            ]
            for s in surveys:
                resp_count = sum(
                    1 for r in responses if _extract_survey_id(r) == s["id"]
                )
                summary_parts.append(
                    f"  - {s.get('title', 'Untitled')}: {resp_count} responses"
                )

            result_data = _build_result(profile, "\n".join(summary_parts))

            # ── Cache ──
            await self.redis_manager.set_odoo_cache(
                tenant_id,
                "survey_cache",
                result_data,
                cache_id="all",
                ttl=3600,  # 1h for survey data
            )

            logger.info(
                "Extracted survey data: %d surveys, %d responses, "
                "%d NPS questions (confidence=%.2f)",
                len(surveys),
                len(responses),
                len(nps_question_ids),
                nps_confidence,
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


# ── Module-level helpers ──


def _detect_nps_questions(questions: list[dict[str, Any]]) -> set[int]:
    """Identify NPS questions: numerical_box with constr_min=0, constr_max=10."""
    nps_ids: set[int] = set()
    for q in questions:
        q_type = q.get("question_type", "")
        if q_type != _NPS_QUESTION_TYPE:
            continue
        constr_min = q.get("constr_min_value", None)
        constr_max = q.get("constr_max_value", None)
        if constr_min == _NPS_MIN and constr_max == _NPS_MAX:
            nps_ids.add(q["id"])
            logger.debug(
                "NPS question detected: id=%d title=%s",
                q["id"],
                q.get("title", ""),
            )
    return nps_ids


def _compute_nps_confidence(
    nps_question_ids: set[int],
    all_questions: list[dict[str, Any]],
    nps_responses: list[SurveyFeedback],
) -> float:
    """Compute confidence in NPS detection (0.0 - 1.0)."""
    if not nps_question_ids:
        return 0.0
    # Higher confidence with more NPS questions and responses
    question_signal = min(len(nps_question_ids) / 3.0, 1.0)  # Cap at 3
    response_signal = min(len(nps_responses) / 20.0, 1.0)  # Cap at 20
    return round((question_signal * 0.6 + response_signal * 0.4), 2)


def _extract_partner_id(raw: dict[str, Any]) -> int | None:
    """Extract numeric partner_id from Odoo many2one tuple."""
    pid = raw.get("partner_id")
    if isinstance(pid, (list, tuple)) and pid:
        return pid[0]
    if isinstance(pid, int) and pid:
        return pid
    return None


def _extract_survey_id(resp: dict[str, Any]) -> int:
    """Extract survey_id from response (handles many2one tuple)."""
    sid = resp.get("survey_id")
    if isinstance(sid, (list, tuple)) and sid:
        return sid[0]
    if isinstance(sid, int):
        return sid
    return 0


def _build_result(profile: SurveyFeedbackProfile, context_text: str) -> dict[str, Any]:
    """Build the standard result dict from a SurveyFeedbackProfile."""
    return {
        "context": context_text[:5000],
        "sources": [{"type": "odoo", "title": "Odoo Surveys", "url": ""}],
        "profile": profile.model_dump(),
        "survey_count": profile.survey_count,
        "response_count": profile.response_count,
        "nps_questions_detected": profile.nps_questions_detected,
        "nps_detection_confidence": profile.nps_detection_confidence,
    }


def _elapsed(start: float) -> float:
    return (time.monotonic() - start) * 1000
