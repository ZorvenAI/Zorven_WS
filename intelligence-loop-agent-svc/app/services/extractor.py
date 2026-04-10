"""IntelligenceExtractor — Phase 3 implementation.

Flow:
1. Fetch campaign context from Django (recommendations + brand snippet).
2. Build a prompt and call Claude (or fall back to a deterministic mock).
3. Parse + validate learnings.
4. Adjust confidence and detect contradictions.
5. Return an IntelligenceReport.

Fail-open at every external boundary so the orchestrator always gets a
valid report (possibly empty) instead of a 500.
"""

import logging
import uuid
from typing import Any

from app.api.schemas import IntelligenceReport, LearningOut
from app.core.config import settings
from app.logic.parser import parse_claude_response
from app.logic.prompts import SYSTEM_PROMPT, build_user_prompt
from app.logic.scoring import adjust_confidence, detect_contradictions
from app.services.anthropic_client import AnthropicClient
from app.services.django_client import DjangoClient

logger = logging.getLogger(__name__)


class IntelligenceExtractor:
    def __init__(
        self,
        django_client: DjangoClient | None = None,
        anthropic_client: AnthropicClient | None = None,
    ) -> None:
        self._django = django_client or DjangoClient()
        self._claude = anthropic_client or AnthropicClient(
            api_key=settings.ANTHROPIC_API_KEY,
            model=settings.ANTHROPIC_MODEL,
            temperature=settings.ANTHROPIC_TEMPERATURE,
        )

    async def extract(
        self,
        *,
        job_id: str,
        tenant_id: str | None,
        state: dict[str, Any],
        context: dict[str, Any],
        config: dict[str, Any],
    ) -> IntelligenceReport:
        mode = (config or {}).get("default_mode") or settings.DEFAULT_MODE
        trigger_source = (context or {}).get("trigger_source", "manual")
        campaign_id = (state or {}).get("campaign_id") or (context or {}).get(
            "campaign_id"
        )
        brand_context_id = str((context or {}).get("brand_context_id", ""))

        # 1. Load campaign context from Django (fail-open).
        campaign_ctx: dict[str, Any] = {}
        if campaign_id:
            fetched = await self._django.get_campaign_context(
                tenant_id, str(campaign_id)
            )
            if fetched:
                campaign_ctx = fetched

        # 2. Call Claude (or fall back).
        summary, learnings = await self._call_claude(campaign_ctx)
        if not learnings:
            summary, learnings = _mock_report(campaign_id)

        # 3. Adjust confidence + detect contradictions.
        scored = [adjust_confidence(le, campaign_ctx) for le in learnings]
        contradictions = detect_contradictions(scored, campaign_ctx)

        report = IntelligenceReport(
            intelligence_id=str(uuid.uuid4()),
            campaign_id=str(campaign_id) if campaign_id else None,
            brand_context_id=brand_context_id,
            mode=mode,
            trigger_source=trigger_source,
            summary=summary,
            learnings=scored,
            contradictions=contradictions,
            auto_reruns_triggered=0,
            rag_writes=0,
        )

        # Persist + dispatch follow-ups (fail-open).
        await self._persist_and_dispatch(
            tenant_id=tenant_id, job_id=job_id, report=report
        )
        return report

    async def _persist_and_dispatch(
        self,
        *,
        tenant_id: str | None,
        job_id: str,
        report: IntelligenceReport,
    ) -> None:
        """Ingest into Django, then auto-trigger eligible follow-ups."""
        ingest_payload = {
            "job_id": job_id,
            "tenant_id": tenant_id or "",
            "campaign_id": report.campaign_id,
            "brand_context_id": report.brand_context_id,
            "mode": report.mode,
            "trigger_source": report.trigger_source,
            "intelligence_report": report.model_dump(),
            "contradictions": report.contradictions,
            "rag_writes": report.rag_writes,
            "learnings": [le.model_dump() for le in report.learnings],
        }
        await self._django.ingest_intelligence_report(tenant_id, ingest_payload)

        # Post each learning to Django as a RAG document. This is what
        # `rag_writes` actually counts; we only increment on success so the
        # field reflects what made it into the per-tenant Vertex AI store.
        rag_writes = 0
        for learning in report.learnings:
            rag_payload = {
                "tenant_id": tenant_id or "",
                "learning_id": learning.learning_id,
                "content": (
                    f"{learning.headline}\n\n"
                    f"Category: {learning.category}\n"
                    f"Impact: {learning.impact}\n"
                    f"Confidence: {learning.confidence}\n"
                    f"Target: {learning.target_workflow}/{learning.target_agent}\n"
                ),
                "metadata": {
                    "category": learning.category,
                    "impact": learning.impact,
                    "confidence": learning.confidence,
                    "target_workflow": learning.target_workflow,
                    "target_agent": learning.target_agent,
                    "intelligence_id": report.intelligence_id,
                    "campaign_id": report.campaign_id,
                    **(learning.detail or {}),
                },
            }
            ok = await self._django.ingest_rag_learning(tenant_id, rag_payload)
            if ok:
                rag_writes += 1
        report.rag_writes = rag_writes

        # Auto-trigger only when explicitly enabled.
        logger.info(
            "Dispatch check: mode=%s, learnings=%d, targets=%s, confidences=%s",
            report.mode,
            len(report.learnings),
            [le.target_workflow for le in report.learnings],
            [le.confidence for le in report.learnings],
        )
        if report.mode != "auto_trigger":
            return

        contradiction_ids = {
            c.get("learning_id") for c in (report.contradictions or [])
        }
        triggered = 0
        for learning in report.learnings:
            if learning.confidence < settings.MIN_CONFIDENCE_AUTO_TRIGGER:
                logger.info(
                    "Skipping learning %s: confidence %d < threshold %d",
                    learning.learning_id, learning.confidence,
                    settings.MIN_CONFIDENCE_AUTO_TRIGGER,
                )
                continue
            if learning.target_workflow == "WF2":
                # WF2 is always behind human approval.
                await self._django.create_wf2_request(
                    tenant_id,
                    {
                        "tenant_id": tenant_id or "",
                        "learning_id": learning.learning_id,
                        "requested_agent": learning.target_agent,
                        "rationale": learning.headline,
                        "expires_in_hours": settings.WF2_APPROVAL_TIMEOUT_HOURS,
                    },
                )
                continue
            if learning.learning_id in contradiction_ids:
                continue  # contradicts established strategy
            ok = await self._django.auto_trigger_rerun(
                tenant_id,
                {
                    "learning_id": learning.learning_id,
                    "note": "ILA auto-trigger (Phase 4)",
                },
            )
            if ok:
                triggered += 1
        if triggered:
            report.auto_reruns_triggered = triggered

    async def _call_claude(
        self, campaign_ctx: dict[str, Any]
    ) -> tuple[str, list[LearningOut]]:
        if not self._claude.enabled or not campaign_ctx:
            return "", []
        user = build_user_prompt(campaign_ctx)
        raw = await self._claude.complete_json(system=SYSTEM_PROMPT, user=user)
        if not raw:
            return "", []
        return parse_claude_response(raw)


def _mock_report(campaign_id: str | None) -> tuple[str, list[LearningOut]]:
    """Deterministic fallback used when Claude is unavailable.

    Produces representative learnings across WF1/WF2/WF3 so the full
    dispatch + WF2 approval flow can be exercised even without a live LLM.
    Confidence is set above MIN_CONFIDENCE_AUTO_TRIGGER (75) so
    auto_trigger mode actually creates WF2 requests and fires reruns.
    """
    return (
        "Mock intelligence report — Anthropic unavailable or no campaign context.",
        [
            LearningOut(
                learning_id=str(uuid.uuid4()),
                category="creative",
                headline="Mock: ad creative fatigue detected — refresh imagery",
                detail={"source": "mock-extractor", "campaign_id": campaign_id},
                confidence=80,
                impact="MEDIUM",
                target_workflow="WF3",
                target_agent="CGA",
            ),
            LearningOut(
                learning_id=str(uuid.uuid4()),
                category="audience",
                headline="Mock: audience segments shifting — re-evaluate personas",
                detail={"source": "mock-extractor", "campaign_id": campaign_id},
                confidence=82,
                impact="HIGH",
                target_workflow="WF1",
                target_agent="APA",
            ),
            LearningOut(
                learning_id=str(uuid.uuid4()),
                category="messaging",
                headline="Mock: brand positioning underperforming — review strategy",
                detail={"source": "mock-extractor", "campaign_id": campaign_id},
                confidence=85,
                impact="HIGH",
                target_workflow="WF2",
                target_agent="BPA",
            ),
        ],
    )
