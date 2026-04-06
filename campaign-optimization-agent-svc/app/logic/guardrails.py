"""Three-layer guardrail system for Campaign Optimization Agent.

Input Guardrails (IG-01..08):    Validate prerequisites before optimization.
Decision Guardrails (PG-01..10): Enforce safety limits on proposed actions.
Output Guardrails (OG-01..06):   Validate Meta API writes and outcomes.

Each guardrail returns a GuardrailResult dataclass.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class GuardrailAction(str, Enum):
    """Action to take when a guardrail triggers."""

    SKIP = "skip"
    BLOCK = "block"
    DOWNGRADE = "downgrade"
    WARN = "warn"


@dataclass
class GuardrailResult:
    """Result from a single guardrail check."""

    passed: bool
    rule_id: str
    message: str
    action: GuardrailAction = GuardrailAction.WARN


@dataclass
class GuardrailReport:
    """Aggregated results from all guardrails in a layer."""

    results: list[GuardrailResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        """True if all guardrails passed."""
        return all(r.passed for r in self.results)

    @property
    def blocked(self) -> bool:
        """True if any guardrail returned BLOCK action."""
        return any(
            not r.passed and r.action == GuardrailAction.BLOCK
            for r in self.results
        )

    @property
    def failures(self) -> list[GuardrailResult]:
        """Return only failed guardrails."""
        return [r for r in self.results if not r.passed]


class InputGuardrails:
    """Validate all prerequisites before optimization begins."""

    def check(
        self,
        campaign: dict[str, Any],
        tenant_config: dict[str, Any],
        redis_manager: Any = None,
        settings: Any = None,
    ) -> GuardrailReport:
        """Run all input guardrails (IG-01 through IG-08).

        Returns a GuardrailReport with results for each check.
        """
        report = GuardrailReport()

        # IG-01: Campaign discovery validation
        campaign_id = campaign.get("campaign_id", "")
        if not campaign_id:
            report.results.append(
                GuardrailResult(
                    passed=False,
                    rule_id="IG-01",
                    message="Campaign ID missing from discovery data.",
                    action=GuardrailAction.SKIP,
                )
            )
        else:
            report.results.append(
                GuardrailResult(
                    passed=True, rule_id="IG-01", message="Campaign ID valid."
                )
            )

        # IG-02: Meta credentials check
        access_token = campaign.get("meta_access_token", "")
        ad_account_id = campaign.get("meta_ad_account_id", "")
        if not access_token or not ad_account_id:
            report.results.append(
                GuardrailResult(
                    passed=False,
                    rule_id="IG-02",
                    message="Meta credentials missing (access_token or ad_account_id).",
                    action=GuardrailAction.SKIP,
                )
            )
        else:
            report.results.append(
                GuardrailResult(
                    passed=True,
                    rule_id="IG-02",
                    message="Meta credentials present.",
                )
            )

        # IG-03: Minimum data threshold
        min_spend = (
            settings.MIN_SPEND_BEFORE_DECISION_USD
            if settings
            else 50.0
        )
        min_impressions = (
            settings.MIN_IMPRESSIONS_BEFORE_DECISION
            if settings
            else 1000
        )
        spend = campaign.get("total_spend_usd", 0)
        impressions = campaign.get("total_impressions", 0)
        if spend < min_spend or impressions < min_impressions:
            report.results.append(
                GuardrailResult(
                    passed=False,
                    rule_id="IG-03",
                    message=(
                        f"Insufficient data: spend=${spend:.2f} "
                        f"(min=${min_spend:.2f}), "
                        f"impressions={impressions} "
                        f"(min={min_impressions})."
                    ),
                    action=GuardrailAction.SKIP,
                )
            )
        else:
            report.results.append(
                GuardrailResult(
                    passed=True,
                    rule_id="IG-03",
                    message="Minimum data threshold met.",
                )
            )

        # IG-04: Campaign age gate (<48h = skip)
        created_at = campaign.get("created_at", "")
        if created_at:
            try:
                created = datetime.fromisoformat(created_at)
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                age_hours = (
                    datetime.now(timezone.utc) - created
                ).total_seconds() / 3600
                if age_hours < 48:
                    report.results.append(
                        GuardrailResult(
                            passed=False,
                            rule_id="IG-04",
                            message=(
                                f"Campaign too young: {age_hours:.1f}h "
                                f"(min 48h for optimization)."
                            ),
                            action=GuardrailAction.SKIP,
                        )
                    )
                else:
                    report.results.append(
                        GuardrailResult(
                            passed=True,
                            rule_id="IG-04",
                            message="Campaign age gate passed.",
                        )
                    )
            except (ValueError, TypeError):
                report.results.append(
                    GuardrailResult(
                        passed=False,
                        rule_id="IG-04",
                        message="Invalid created_at timestamp.",
                        action=GuardrailAction.SKIP,
                    )
                )
        else:
            report.results.append(
                GuardrailResult(
                    passed=False,
                    rule_id="IG-04",
                    message="No created_at timestamp.",
                    action=GuardrailAction.SKIP,
                )
            )

        # IG-05: Cooldown check (24h between optimizations)
        cooldown_hours = (
            settings.OPTIMIZATION_COOLDOWN_HOURS if settings else 24
        )
        last_optimized = campaign.get("last_optimized_at", "")
        if last_optimized:
            try:
                last_opt = datetime.fromisoformat(last_optimized)
                if last_opt.tzinfo is None:
                    last_opt = last_opt.replace(tzinfo=timezone.utc)
                hours_since = (
                    datetime.now(timezone.utc) - last_opt
                ).total_seconds() / 3600
                if hours_since < cooldown_hours:
                    report.results.append(
                        GuardrailResult(
                            passed=False,
                            rule_id="IG-05",
                            message=(
                                f"Cooldown active: {hours_since:.1f}h since "
                                f"last optimization (cooldown={cooldown_hours}h)."
                            ),
                            action=GuardrailAction.SKIP,
                        )
                    )
                else:
                    report.results.append(
                        GuardrailResult(
                            passed=True,
                            rule_id="IG-05",
                            message="Cooldown period passed.",
                        )
                    )
            except (ValueError, TypeError):
                report.results.append(
                    GuardrailResult(
                        passed=True,
                        rule_id="IG-05",
                        message="No valid last_optimized_at (first optimization).",
                    )
                )
        else:
            report.results.append(
                GuardrailResult(
                    passed=True,
                    rule_id="IG-05",
                    message="No previous optimization (first run).",
                )
            )

        # IG-06: Daily action counter
        max_actions = (
            settings.MAX_AUTO_ACTIONS_PER_DAY if settings else 10
        )
        daily_count = campaign.get("daily_action_count", 0)
        if daily_count >= max_actions:
            report.results.append(
                GuardrailResult(
                    passed=False,
                    rule_id="IG-06",
                    message=(
                        f"Daily action limit reached: {daily_count}/"
                        f"{max_actions}."
                    ),
                    action=GuardrailAction.BLOCK,
                )
            )
        else:
            report.results.append(
                GuardrailResult(
                    passed=True,
                    rule_id="IG-06",
                    message=(
                        f"Daily action count OK: {daily_count}/"
                        f"{max_actions}."
                    ),
                )
            )

        # IG-07: Sandbox mode check
        sandbox = campaign.get("sandbox_mode", True)
        report.results.append(
            GuardrailResult(
                passed=True,
                rule_id="IG-07",
                message=(
                    "Sandbox mode: ON" if sandbox else "Sandbox mode: OFF (PRODUCTION)"
                ),
            )
        )

        # IG-08: Tenant config load
        if not tenant_config:
            report.results.append(
                GuardrailResult(
                    passed=False,
                    rule_id="IG-08",
                    message="Tenant config not loaded.",
                    action=GuardrailAction.WARN,
                )
            )
        else:
            report.results.append(
                GuardrailResult(
                    passed=True,
                    rule_id="IG-08",
                    message="Tenant config loaded.",
                )
            )

        return report


class DecisionGuardrails:
    """Enforce safety limits on proposed optimization actions."""

    def check(
        self,
        recommendation: dict[str, Any],
        campaign: dict[str, Any],
        settings: Any = None,
    ) -> GuardrailReport:
        """Run all decision guardrails (PG-01 through PG-10).

        Returns a GuardrailReport with results for each check.
        """
        report = GuardrailReport()
        action_type = recommendation.get("action_type", "")
        entity_type = recommendation.get("entity_type", "")
        current = recommendation.get("current_values", {})
        proposed = recommendation.get("proposed_values", {})

        max_increase = (
            settings.MAX_DAILY_BUDGET_INCREASE_PCT if settings else 20
        )
        max_decrease = (
            settings.MAX_DAILY_BUDGET_DECREASE_PCT if settings else 50
        )

        # PG-01: Budget change limits (±20% increase, ±50% decrease)
        if action_type == "adjust_budget":
            current_budget = current.get("daily_budget", 0)
            proposed_budget = proposed.get("daily_budget", 0)
            if current_budget > 0:
                change_pct = (
                    (proposed_budget - current_budget) / current_budget * 100
                )
                if change_pct > max_increase:
                    report.results.append(
                        GuardrailResult(
                            passed=False,
                            rule_id="PG-01",
                            message=(
                                f"Budget increase {change_pct:.1f}% exceeds "
                                f"max {max_increase}%."
                            ),
                            action=GuardrailAction.DOWNGRADE,
                        )
                    )
                elif change_pct < -max_decrease:
                    report.results.append(
                        GuardrailResult(
                            passed=False,
                            rule_id="PG-01",
                            message=(
                                f"Budget decrease {abs(change_pct):.1f}% exceeds "
                                f"max {max_decrease}%."
                            ),
                            action=GuardrailAction.DOWNGRADE,
                        )
                    )
                else:
                    report.results.append(
                        GuardrailResult(
                            passed=True,
                            rule_id="PG-01",
                            message=f"Budget change {change_pct:.1f}% within limits.",
                        )
                    )
            else:
                report.results.append(
                    GuardrailResult(
                        passed=True,
                        rule_id="PG-01",
                        message="No current budget to compare.",
                    )
                )
        else:
            report.results.append(
                GuardrailResult(
                    passed=True,
                    rule_id="PG-01",
                    message="Not a budget action.",
                )
            )

        # PG-02: Spend threshold (>$500 requires approval)
        approval_threshold = (
            settings.REQUIRE_APPROVAL_ABOVE_USD if settings else 500.0
        )
        proposed_budget = proposed.get("daily_budget", 0)
        if proposed_budget > approval_threshold:
            report.results.append(
                GuardrailResult(
                    passed=False,
                    rule_id="PG-02",
                    message=(
                        f"Proposed budget ${proposed_budget:.2f} exceeds "
                        f"approval threshold ${approval_threshold:.2f}."
                    ),
                    action=GuardrailAction.BLOCK,
                )
            )
        else:
            report.results.append(
                GuardrailResult(
                    passed=True,
                    rule_id="PG-02",
                    message="Below spend approval threshold.",
                )
            )

        # PG-03: Campaign-level always manual
        campaign_always_manual = (
            settings.CAMPAIGN_LEVEL_ALWAYS_MANUAL if settings else True
        )
        if entity_type == "campaign" and campaign_always_manual:
            report.results.append(
                GuardrailResult(
                    passed=False,
                    rule_id="PG-03",
                    message="Campaign-level changes always require manual approval.",
                    action=GuardrailAction.BLOCK,
                )
            )
        else:
            report.results.append(
                GuardrailResult(
                    passed=True,
                    rule_id="PG-03",
                    message="Entity-level check passed.",
                )
            )

        # PG-04: Zero active guard (don't pause last active ad set)
        if action_type in ("pause", "kill"):
            active_count = campaign.get("active_ad_set_count", 1)
            if active_count <= 1:
                report.results.append(
                    GuardrailResult(
                        passed=False,
                        rule_id="PG-04",
                        message="Cannot pause last active ad set/ad.",
                        action=GuardrailAction.BLOCK,
                    )
                )
            else:
                report.results.append(
                    GuardrailResult(
                        passed=True,
                        rule_id="PG-04",
                        message=f"{active_count} active entities remaining.",
                    )
                )
        else:
            report.results.append(
                GuardrailResult(
                    passed=True,
                    rule_id="PG-04",
                    message="Not a pause/kill action.",
                )
            )

        # PG-05: CPA kill confirmation (need >=10 conversions)
        if action_type == "kill" and recommendation.get("reason") == "high_cpa":
            conversions = current.get("conversions", 0)
            if conversions < 10:
                report.results.append(
                    GuardrailResult(
                        passed=False,
                        rule_id="PG-05",
                        message=(
                            f"CPA kill requires >=10 conversions "
                            f"(has {conversions})."
                        ),
                        action=GuardrailAction.BLOCK,
                    )
                )
            else:
                report.results.append(
                    GuardrailResult(
                        passed=True,
                        rule_id="PG-05",
                        message=f"CPA kill confirmed ({conversions} conversions).",
                    )
                )
        else:
            report.results.append(
                GuardrailResult(
                    passed=True,
                    rule_id="PG-05",
                    message="Not a CPA kill action.",
                )
            )

        # PG-06: Reallocation balance (±5% tolerance)
        if action_type == "reallocate_budget":
            total_before = recommendation.get("total_budget_before", 0)
            total_after = recommendation.get("total_budget_after", 0)
            if total_before > 0:
                diff_pct = abs(total_after - total_before) / total_before * 100
                if diff_pct > 5:
                    report.results.append(
                        GuardrailResult(
                            passed=False,
                            rule_id="PG-06",
                            message=(
                                f"Reallocation imbalance: {diff_pct:.1f}% "
                                f"(max 5%)."
                            ),
                            action=GuardrailAction.BLOCK,
                        )
                    )
                else:
                    report.results.append(
                        GuardrailResult(
                            passed=True,
                            rule_id="PG-06",
                            message="Reallocation balanced.",
                        )
                    )
            else:
                report.results.append(
                    GuardrailResult(
                        passed=True,
                        rule_id="PG-06",
                        message="No total budget to compare.",
                    )
                )
        else:
            report.results.append(
                GuardrailResult(
                    passed=True,
                    rule_id="PG-06",
                    message="Not a reallocation action.",
                )
            )

        # PG-07: Creative refresh rate limit (7d cooldown)
        if action_type == "creative_refresh":
            last_refresh = recommendation.get("last_creative_refresh", "")
            if last_refresh:
                try:
                    last_dt = datetime.fromisoformat(last_refresh)
                    if last_dt.tzinfo is None:
                        last_dt = last_dt.replace(tzinfo=timezone.utc)
                    days_since = (
                        datetime.now(timezone.utc) - last_dt
                    ).days
                    if days_since < 7:
                        report.results.append(
                            GuardrailResult(
                                passed=False,
                                rule_id="PG-07",
                                message=(
                                    f"Creative refresh cooldown: {days_since}d "
                                    f"since last refresh (min 7d)."
                                ),
                                action=GuardrailAction.BLOCK,
                            )
                        )
                    else:
                        report.results.append(
                            GuardrailResult(
                                passed=True,
                                rule_id="PG-07",
                                message="Creative refresh cooldown passed.",
                            )
                        )
                except (ValueError, TypeError):
                    report.results.append(
                        GuardrailResult(
                            passed=True,
                            rule_id="PG-07",
                            message="Invalid last_creative_refresh timestamp.",
                        )
                    )
            else:
                report.results.append(
                    GuardrailResult(
                        passed=True,
                        rule_id="PG-07",
                        message="No previous creative refresh.",
                    )
                )
        else:
            report.results.append(
                GuardrailResult(
                    passed=True,
                    rule_id="PG-07",
                    message="Not a creative refresh action.",
                )
            )

        # PG-08: Frequency validation
        frequency = current.get("frequency", 0)
        if frequency > 0 and action_type == "scale":
            if frequency > 3.0:
                report.results.append(
                    GuardrailResult(
                        passed=False,
                        rule_id="PG-08",
                        message=(
                            f"Frequency too high ({frequency:.1f}) to scale. "
                            f"Consider creative refresh."
                        ),
                        action=GuardrailAction.WARN,
                    )
                )
            else:
                report.results.append(
                    GuardrailResult(
                        passed=True,
                        rule_id="PG-08",
                        message=f"Frequency OK ({frequency:.1f}).",
                    )
                )
        else:
            report.results.append(
                GuardrailResult(
                    passed=True,
                    rule_id="PG-08",
                    message="Frequency check not applicable.",
                )
            )

        # PG-09: Audit trail (always passes, logs the recommendation)
        logger.info(
            "PG-09 Audit: action=%s entity=%s:%s",
            action_type,
            entity_type,
            recommendation.get("entity_id", ""),
        )
        report.results.append(
            GuardrailResult(
                passed=True,
                rule_id="PG-09",
                message="Audit trail recorded.",
            )
        )

        # PG-10: First-optimization-human
        is_first = campaign.get("optimization_count", 0) == 0
        if is_first:
            report.results.append(
                GuardrailResult(
                    passed=False,
                    rule_id="PG-10",
                    message="First optimization always requires human approval.",
                    action=GuardrailAction.BLOCK,
                )
            )
        else:
            report.results.append(
                GuardrailResult(
                    passed=True,
                    rule_id="PG-10",
                    message="Not the first optimization.",
                )
            )

        return report


class OutputGuardrails:
    """Validate Meta API writes and optimization outcomes."""

    def check(
        self,
        execution_result: dict[str, Any],
        campaign: dict[str, Any],
    ) -> GuardrailReport:
        """Run all output guardrails (OG-01 through OG-06).

        Returns a GuardrailReport with results for each check.
        """
        report = GuardrailReport()

        # OG-01: Meta API write verification
        verified = execution_result.get("verified", False)
        if not verified:
            report.results.append(
                GuardrailResult(
                    passed=False,
                    rule_id="OG-01",
                    message="Meta API write not verified.",
                    action=GuardrailAction.BLOCK,
                )
            )
        else:
            report.results.append(
                GuardrailResult(
                    passed=True,
                    rule_id="OG-01",
                    message="Meta API write verified.",
                )
            )

        # OG-02: Spend impact (<30%)
        spend_impact_pct = execution_result.get("spend_impact_pct", 0)
        if spend_impact_pct > 30:
            report.results.append(
                GuardrailResult(
                    passed=False,
                    rule_id="OG-02",
                    message=(
                        f"Cumulative spend impact {spend_impact_pct:.1f}% "
                        f"exceeds 30% threshold. Pausing remaining actions."
                    ),
                    action=GuardrailAction.BLOCK,
                )
            )
        else:
            report.results.append(
                GuardrailResult(
                    passed=True,
                    rule_id="OG-02",
                    message=f"Spend impact {spend_impact_pct:.1f}% within limits.",
                )
            )

        # OG-03: Recommendation quality
        quality_score = execution_result.get("quality_score", 1.0)
        if quality_score < 0.5:
            report.results.append(
                GuardrailResult(
                    passed=False,
                    rule_id="OG-03",
                    message=(
                        f"Recommendation quality score {quality_score:.2f} "
                        f"below minimum 0.5."
                    ),
                    action=GuardrailAction.WARN,
                )
            )
        else:
            report.results.append(
                GuardrailResult(
                    passed=True,
                    rule_id="OG-03",
                    message="Recommendation quality acceptable.",
                )
            )

        # OG-04: Tenant isolation
        result_tenant = execution_result.get("tenant_id", "")
        campaign_tenant = campaign.get("tenant_id", "")
        if result_tenant and campaign_tenant and result_tenant != campaign_tenant:
            report.results.append(
                GuardrailResult(
                    passed=False,
                    rule_id="OG-04",
                    message="Tenant isolation violation detected.",
                    action=GuardrailAction.BLOCK,
                )
            )
        else:
            report.results.append(
                GuardrailResult(
                    passed=True,
                    rule_id="OG-04",
                    message="Tenant isolation verified.",
                )
            )

        # OG-05: Data freshness (<24h)
        data_age_hours = execution_result.get("data_age_hours", 0)
        if data_age_hours > 24:
            report.results.append(
                GuardrailResult(
                    passed=False,
                    rule_id="OG-05",
                    message=(
                        f"Data is {data_age_hours:.1f}h old "
                        f"(max 24h for decisions)."
                    ),
                    action=GuardrailAction.WARN,
                )
            )
        else:
            report.results.append(
                GuardrailResult(
                    passed=True,
                    rule_id="OG-05",
                    message="Data freshness OK.",
                )
            )

        # OG-06: Learnings persistence
        persisted = execution_result.get("learnings_persisted", True)
        if not persisted:
            report.results.append(
                GuardrailResult(
                    passed=False,
                    rule_id="OG-06",
                    message="Learnings not persisted to history.",
                    action=GuardrailAction.WARN,
                )
            )
        else:
            report.results.append(
                GuardrailResult(
                    passed=True,
                    rule_id="OG-06",
                    message="Learnings persisted.",
                )
            )

        return report
