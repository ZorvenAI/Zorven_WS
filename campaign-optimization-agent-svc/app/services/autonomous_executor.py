"""SKL-COA-07: Autonomous executor.

Executes optimization actions within guardrails. Validates ALL
decision guardrails before each action, increments daily action counter,
calls Meta Management API, and verifies results.
"""

import logging
from typing import Any

from app.core.config import settings
from app.logic.guardrails import DecisionGuardrails, GuardrailAction
from app.messaging.event_emitter import EventEmitter, EventType
from app.services.meta_management_client import MetaManagementClient
from app.services.optimization_verifier import OptimizationVerifier

logger = logging.getLogger(__name__)


class AutonomousExecutor:
    """Executes approved/autonomous optimization actions."""

    def __init__(
        self,
        meta_client: MetaManagementClient,
        verifier: OptimizationVerifier,
        event_emitter: EventEmitter,
        redis_manager=None,
    ):
        self._meta = meta_client
        self._verifier = verifier
        self._emitter = event_emitter
        self._redis = redis_manager
        self._decision_guardrails = DecisionGuardrails()

    async def execute_autonomous(
        self,
        campaign: Any,
        recommendations: list[dict[str, Any]],
        config: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Execute recommendations autonomously within guardrails.

        Args:
            campaign: ActiveCampaign dataclass.
            recommendations: List of recommendation dicts.
            config: Tenant optimization config.

        Returns:
            List of ExecutionResult dicts per action.
        """
        results = []
        access_token = campaign.meta_access_token

        for rec in recommendations:
            # Check decision guardrails
            guard_report = self._decision_guardrails.check(
                recommendation=rec,
                campaign={
                    "active_ad_set_count": campaign.active_ad_set_count,
                    "optimization_count": campaign.optimization_count,
                },
                settings=settings,
            )

            if guard_report.blocked:
                # Queue for human approval instead
                failures = guard_report.failures
                rec["requires_approval"] = True
                rec["guardrail_blocks"] = [
                    {"rule_id": f.rule_id, "message": f.message}
                    for f in failures
                ]
                results.append(
                    {
                        "recommendation_id": rec["recommendation_id"],
                        "status": "awaiting_approval",
                        "executed": False,
                        "reason": "Blocked by guardrails",
                        "guardrails": [f.rule_id for f in failures],
                    }
                )
                await self._emitter.emit(
                    EventType.GUARDRAIL_TRIGGERED,
                    tenant_id=campaign.tenant_id,
                    campaign_id=campaign.campaign_id,
                    data={
                        "recommendation_id": rec["recommendation_id"],
                        "guardrails": [
                            f.rule_id for f in failures
                        ],
                    },
                )
                continue

            # Check for warnings (proceed but log)
            for g in guard_report.results:
                if (
                    not g.passed
                    and g.action == GuardrailAction.DOWNGRADE
                ):
                    logger.info(
                        "Guardrail %s downgrade: %s",
                        g.rule_id,
                        g.message,
                    )

            # Execute the action
            try:
                exec_result = await self._execute_action(
                    rec, campaign, access_token
                )

                # Verify the action
                verification = await self._verifier.verify_action(
                    entity_type=rec["entity_type"],
                    entity_id=rec["entity_id"],
                    expected_state=rec["proposed_values"],
                    meta_client=self._meta,
                    access_token=access_token,
                )

                # Increment daily action counter
                if self._redis:
                    await self._redis.increment_action_counter(
                        campaign.tenant_id
                    )

                # Record last action
                if self._redis:
                    await self._redis.set_last_action(
                        tenant_id=campaign.tenant_id,
                        campaign_id=campaign.campaign_id,
                        entity_id=rec["entity_id"],
                        action_data={
                            "action_type": rec["action_type"],
                            "proposed_values": rec["proposed_values"],
                            "executed": True,
                            "verified": verification.get(
                                "verified", False
                            ),
                        },
                    )

                await self._emitter.emit(
                    EventType.ACTION_AUTO_EXECUTED,
                    tenant_id=campaign.tenant_id,
                    campaign_id=campaign.campaign_id,
                    data={
                        "recommendation_id": rec["recommendation_id"],
                        "action_type": rec["action_type"],
                        "verified": verification.get(
                            "verified", False
                        ),
                    },
                )

                results.append(
                    {
                        "recommendation_id": rec["recommendation_id"],
                        "status": "executed",
                        "executed": True,
                        "verification": verification,
                        "execution_result": exec_result,
                    }
                )

            except Exception as exc:
                logger.error(
                    "Failed to execute recommendation %s: %s",
                    rec["recommendation_id"],
                    exc,
                )
                results.append(
                    {
                        "recommendation_id": rec["recommendation_id"],
                        "status": "failed",
                        "executed": False,
                        "error": str(exc),
                    }
                )

        return results

    async def _execute_action(
        self,
        rec: dict[str, Any],
        campaign: Any,
        access_token: str,
    ) -> dict[str, Any]:
        """Execute a single optimization action via Meta Management API."""
        action_type = rec["action_type"]
        entity_id = rec["entity_id"]
        proposed = rec["proposed_values"]

        if action_type == "pause":
            success = await self._meta.update_ad_set_status(
                ad_set_id=entity_id,
                status="PAUSED",
                access_token=access_token,
            )
            return {"action": "pause", "success": success}

        elif action_type == "scale":
            increase_pct = proposed.get("budget_increase_pct", 20)
            current_budget = rec["current_values"].get(
                "daily_budget", 0
            )
            new_budget = int(
                current_budget * (1 + increase_pct / 100) * 100
            )
            success = await self._meta.update_ad_set_budget(
                ad_set_id=entity_id,
                daily_budget_cents=new_budget,
                access_token=access_token,
            )
            return {
                "action": "scale",
                "success": success,
                "new_budget_cents": new_budget,
            }

        elif action_type == "adjust_budget":
            new_budget = int(proposed.get("daily_budget", 0) * 100)
            success = await self._meta.update_ad_set_budget(
                ad_set_id=entity_id,
                daily_budget_cents=new_budget,
                access_token=access_token,
            )
            return {
                "action": "adjust_budget",
                "success": success,
                "new_budget_cents": new_budget,
            }

        elif action_type == "kill":
            success = await self._meta.update_ad_set_status(
                ad_set_id=entity_id,
                status="PAUSED",
                access_token=access_token,
            )
            return {"action": "kill", "success": success}

        elif action_type == "creative_refresh":
            # Emit event for CGA to handle
            await self._emitter.emit(
                EventType.CREATIVE_REFRESH_REQUESTED,
                tenant_id=campaign.tenant_id,
                campaign_id=campaign.campaign_id,
                data={
                    "ad_id": entity_id,
                    "reason": rec.get("reason", "fatigue"),
                },
            )
            return {
                "action": "creative_refresh",
                "success": True,
                "delegated_to": "cga",
            }

        else:
            logger.warning(
                "Unknown action type: %s", action_type
            )
            return {"action": action_type, "success": False}
