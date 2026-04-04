"""Three-layer guardrail system for Ad Publishing Agent.

Input Guardrails:  Validate prerequisites before processing.
Plan Guardrails:   Enforce mandatory human approval + budget guards.
Output Guardrails: Validate Meta API responses and entity persistence.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class InputGuardrails:
    """Validate all prerequisites before ad publishing begins."""

    def check(
        self,
        context: dict[str, Any],
        daily_spend_cap_usd: float = 500.0,
    ) -> list[str]:
        """Return list of error messages (empty = all checks passed)."""
        errors = []

        # IG-08: Creative package validation
        packages = context.get("creative_packages", [])
        if not packages:
            errors.append(
                "IG-08: No creative packages found. "
                "Run Creative Generation (Agent 3.2) first."
            )
        for i, pkg in enumerate(packages):
            units = pkg.get("ad_units", [])
            if not units:
                errors.append(f"IG-08: Creative package [{i}] has no ad units.")
            for j, unit in enumerate(units):
                # CGA uses gcs_url; ad-publishing uses image_url
                has_image = (
                    unit.get("image_url") or unit.get("gcs_url") or unit.get("image")
                )
                if not has_image:
                    errors.append(f"IG-08: Package [{i}] unit [{j}] missing image.")

        # IG-09: Campaign blueprint validation
        bp = context.get("blueprint", {})
        if not bp.get("campaign_name"):
            errors.append(
                "IG-09: Campaign blueprint missing. "
                "Run Campaign Architecture (Agent 3.1) first."
            )
        if not bp.get("funnel_stages"):
            errors.append("IG-09: Blueprint has no funnel stages.")

        # IG-10: Meta credentials check (only in production mode)
        if not context.get("sandbox_mode", True):
            creds = context.get("meta_credentials", {})
            if not creds.get("access_token"):
                errors.append(
                    "IG-10: Meta access_token missing. "
                    "Configure Meta Business Manager credentials."
                )
            if not creds.get("ad_account_id"):
                errors.append(
                    "IG-10: Meta ad_account_id missing. "
                    "Configure Meta Business Manager credentials."
                )

        # IG-11: Daily spend cap pre-check
        total_budget = bp.get("total_budget_usd", 0)
        duration = bp.get("duration_days", 1) or 1
        proposed_daily = total_budget / duration
        if proposed_daily > daily_spend_cap_usd:
            errors.append(
                f"IG-11: Proposed daily spend ${proposed_daily:.2f} "
                f"exceeds cap ${daily_spend_cap_usd:.2f}."
            )

        # IG-12: Industry ad policy (Special Ad Categories)
        company = context.get("company", {})
        industry = (company.get("industry", "") or "").lower()
        restricted_industries = {
            "real estate": "HOUSING",
            "housing": "HOUSING",
            "mortgage": "CREDIT",
            "lending": "CREDIT",
            "credit": "CREDIT",
            "banking": "CREDIT",
            "employment": "EMPLOYMENT",
            "recruiting": "EMPLOYMENT",
            "staffing": "EMPLOYMENT",
        }
        detected_category = restricted_industries.get(industry)
        if detected_category:
            bp_categories = bp.get("special_ad_categories", [])
            if detected_category not in bp_categories:
                errors.append(
                    f"IG-12: Industry '{industry}' requires Special Ad "
                    f"Category '{detected_category}' but blueprint does "
                    f"not include it."
                )

        return errors


class PlanGuardrails:
    """Enforce mandatory human approval and budget guards."""

    def check(
        self,
        context: dict[str, Any],
        min_audience_size: int = 10000,
        max_campaign_budget_usd: float = 10000.0,
    ) -> dict[str, Any]:
        """Return guardrail check results.

        Always includes requires_approval=True (HARDCODED).
        """
        warnings = []
        errors = []

        # PG-06: MANDATORY HUMAN APPROVAL — HARDCODED
        # This is NOT configurable. It is core business logic.
        requires_approval = True

        # PG-07: Budget per ad set cap
        bp = context.get("blueprint", {})
        total_budget = bp.get("total_budget_usd", 0)
        stages = bp.get("funnel_stages", [])
        for stage in stages:
            budget_pct = stage.get("budget_pct", 0)
            stage_budget = total_budget * budget_pct
            if stage_budget > total_budget * 0.5:
                warnings.append(
                    f"PG-07: Stage '{stage.get('stage', '?')}' gets "
                    f"{budget_pct * 100:.0f}% of budget (> 50% limit)."
                )

        # PG-03: Total campaign budget
        if total_budget > max_campaign_budget_usd:
            errors.append(
                f"PG-03: Total budget ${total_budget:.2f} exceeds max "
                f"${max_campaign_budget_usd:.2f}."
            )

        # PG-11: Sandbox/Production gate
        is_production = not context.get("sandbox_mode", True)

        return {
            "requires_approval": requires_approval,
            "is_production": is_production,
            "warnings": warnings,
            "errors": errors,
        }


class OutputGuardrails:
    """Validate Meta API responses and entity persistence."""

    def check(
        self,
        published_entities: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate post-publish state.

        Returns dict with all_valid, errors, warnings.
        """
        errors = []
        warnings = []

        # OG-01: Meta API response validation
        campaign_id = published_entities.get("campaign_id")
        if not campaign_id:
            errors.append("OG-01: No campaign_id in published result.")

        ad_set_ids = published_entities.get("ad_set_ids", [])
        if not ad_set_ids:
            errors.append("OG-01: No ad_set_ids in published result.")

        ad_ids = published_entities.get("ad_ids", [])
        if not ad_ids:
            errors.append("OG-01: No ad_ids in published result.")

        # OG-02: Entity ID completeness
        creative_ids = published_entities.get("creative_ids", [])
        expected_ads = len(creative_ids)
        if expected_ads and len(ad_ids) < expected_ads:
            warnings.append(
                f"OG-02: Expected {expected_ads} ads but only "
                f"{len(ad_ids)} were created."
            )

        # OG-03: Campaign status
        campaign_status = published_entities.get("campaign_status", "")
        if campaign_status and campaign_status not in ("ACTIVE", "PAUSED"):
            errors.append(f"OG-03: Unexpected campaign status: {campaign_status}")

        return {
            "all_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }
