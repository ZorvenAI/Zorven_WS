"""Ad Publishing Agent executor.

Thin orchestration wrapper with two entry points:

1. execute()               — Called by /v1/execute, runs phases 1-4
2. resume_after_approval() — Called by /v1/approve, runs phases 6-7

The gap between these (phase 5) is the mandatory human approval gate,
handled by the ApprovalManager.
"""

import logging
import time
from typing import Any

from app.logic.guardrails import InputGuardrails, PlanGuardrails
from app.services.adpub_analyzer import AdPubAnalyzer
from app.services.approval_manager import ApprovalManager
from app.services.context_loader import AdPubContextLoader

logger = logging.getLogger(__name__)


class AdPubExecutor:
    """Orchestrates the two-phase ad publishing flow."""

    def __init__(
        self,
        analyzer: AdPubAnalyzer,
        approval_manager: ApprovalManager,
        context_loader: AdPubContextLoader,
        redis_manager=None,
        trace_producer=None,
        audit_producer=None,
        event_emitter=None,
        daily_spend_cap_usd: float = 500.0,
        min_audience_size: int = 10000,
        max_campaign_budget_usd: float = 10000.0,
    ):
        self._analyzer = analyzer
        self._approval = approval_manager
        self._context_loader = context_loader
        self._redis = redis_manager
        self._trace = trace_producer
        self._audit = audit_producer
        self._events = event_emitter
        self._spend_cap = daily_spend_cap_usd
        self._min_audience = min_audience_size
        self._max_budget = max_campaign_budget_usd

    async def execute(
        self,
        prompt: str,
        input_context: dict[str, Any],
        tenant_context: dict[str, Any],
        config: dict[str, Any],
        previous_outputs: dict[str, Any],
        tenant_id: str,
        job_id: str = "",
        callback_url: str = "",
    ) -> dict[str, Any]:
        """Phase A: Run phases 1-4 and create approval request.

        Returns result with status="awaiting_approval" and preview data.
        """
        start = time.time()

        logger.info(
            "Execute called: tenant_id=%s, job_id=%s, "
            "previous_outputs_keys=%s, config_keys=%s",
            tenant_id,
            job_id,
            list(previous_outputs.keys()) if previous_outputs else [],
            list(config.keys()) if config else [],
        )

        # 1. Load context from previous_outputs (pipeline chaining)
        context = self._context_loader.load(
            previous_outputs=previous_outputs,
            input_context=input_context,
            tenant_context=tenant_context,
            config=config,
        )

        # 1b. If CAA/CGA data missing, fetch from Django backend
        #     (standalone execution — agents ran as separate pipelines)
        if context.get("_needs_caa_fetch") or context.get("_needs_cga_fetch"):
            context = await self._context_loader.enrich_from_backend(context)

        # 2. Input guardrails
        validation_errors = self._context_loader.validate(context)
        diagnostics_info = context.pop("_diagnostics_info", [])
        if validation_errors:
            # Prepend diagnostics so user sees fetch context alongside errors
            all_errors = []
            if diagnostics_info:
                all_errors.append(
                    "Backend enrichment diagnostics: "
                    + " | ".join(diagnostics_info)
                )
            all_errors.extend(validation_errors)
            return self._error_result(
                "prerequisite_missing",
                all_errors,
                start,
            )

        input_errors = InputGuardrails().check(
            context, daily_spend_cap_usd=self._spend_cap
        )
        if input_errors:
            return self._error_result("input_guardrail", input_errors, start)

        # 3. Plan guardrails
        plan_check = PlanGuardrails().check(
            context,
            min_audience_size=self._min_audience,
            max_campaign_budget_usd=self._max_budget,
        )
        if plan_check["errors"]:
            return self._error_result(
                "plan_guardrail", plan_check["errors"], start
            )

        # 4. Run phases 1-4 (campaign + targeting + creatives + previews)
        try:
            preparation = await self._analyzer.analyze_and_prepare(
                context=context,
                tenant_id=tenant_id,
                job_id=job_id,
            )
        except Exception as exc:
            logger.error("Preparation failed: %s", exc, exc_info=True)
            return self._error_result(
                "preparation_failed", [str(exc)], start
            )

        # 5. Create approval request (MANDATORY — HARDCODED)
        preview_data = {
            "campaign_name": preparation["campaign_name"],
            "objective": preparation["objective"],
            "total_daily_budget_usd": preparation["total_daily_budget_usd"],
            "duration_days": preparation["duration_days"],
            "ad_sets": preparation["ad_sets"],
            "previews": preparation["previews"],
            "sandbox_mode": preparation["sandbox_mode"],
        }

        approval_request = await self._approval.create_approval_request(
            job_id=job_id,
            tenant_id=tenant_id,
            preview_data=preview_data,
            is_production=plan_check["is_production"],
            callback_url=callback_url,
        )

        elapsed_ms = int((time.time() - start) * 1000)

        # Store preparation for resume_after_approval
        if self._redis:
            await self._redis.store_preparation(
                approval_request["request_id"],
                tenant_id,
                preparation,
            )

        return {
            "status": "awaiting_approval",
            "approval_request_id": approval_request["request_id"],
            "preview_data": preview_data,
            "is_production": plan_check["is_production"],
            "sandbox_mode": preparation["sandbox_mode"],
            "plan_warnings": plan_check["warnings"],
            "preparation_time_ms": preparation["preparation_time_ms"],
            "execution_time_ms": elapsed_ms,
            "query": prompt,
            "findings": [
                f"Campaign '{preparation['campaign_name']}' prepared "
                f"with {len(preparation['ad_sets'])} ad sets and "
                f"{len(preparation['creatives'])} creatives.",
                f"Daily budget: ${preparation['total_daily_budget_usd']:.2f}",
                f"Mode: {'Sandbox' if preparation['sandbox_mode'] else 'PRODUCTION'}",
            ],
            "recommendations": [
                "Review the ad previews and approve or reject.",
            ],
        }

    async def resume_after_approval(
        self,
        approval_request_id: str,
        approval_result: dict[str, Any],
        tenant_id: str,
        job_id: str = "",
    ) -> dict[str, Any]:
        """Phase B: Run phases 6-7 after human approval.

        Returns final published result.
        """
        start = time.time()

        # Retrieve stored preparation data
        preparation = None
        if self._redis:
            preparation = await self._redis.get_preparation(
                approval_request_id, tenant_id
            )
        if not preparation:
            return self._error_result(
                "preparation_not_found",
                ["Preparation data expired or not found. Re-run execute."],
                start,
            )

        try:
            result = await self._analyzer.publish_after_approval(
                preparation=preparation,
                approval_result=approval_result,
                tenant_id=tenant_id,
                job_id=job_id,
            )
        except Exception as exc:
            logger.error("Publishing failed: %s", exc, exc_info=True)
            # Attempt rollback
            rollback_result = await self._analyzer.rollback(str(exc))
            return {
                "status": "failed",
                "error": str(exc),
                "rollback": rollback_result,
                "execution_time_ms": int((time.time() - start) * 1000),
            }

        elapsed_ms = int((time.time() - start) * 1000)
        result["execution_time_ms"] = elapsed_ms

        return result

    @staticmethod
    def _error_result(
        error_type: str,
        errors: list[str],
        start_time: float,
    ) -> dict[str, Any]:
        return {
            "status": "failed",
            "error_type": error_type,
            "errors": errors,
            "findings": errors,
            "recommendations": [],
            "execution_time_ms": int((time.time() - start_time) * 1000),
        }
