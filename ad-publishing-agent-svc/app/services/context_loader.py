"""Context loader for the Ad Publishing Agent.

Loads all prerequisites from previous_outputs (pipeline chaining)
and/or Django backend endpoints:
- CGA creative packages (approved)
- CAA campaign blueprint
- APA persona profiles (WF1)
- Company model (website, industry)
- Meta credentials (per-tenant)
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AdPubContextLoader:
    """Loads and validates prerequisites for ad publishing."""

    def load(
        self,
        previous_outputs: dict[str, Any],
        input_context: dict[str, Any],
        tenant_context: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Extract and structure context from pipeline outputs.

        Returns a dict with keys: blueprint, creative_packages,
        persona_profiles, company, meta_credentials, sandbox_mode.
        """
        tenant_ctx = tenant_context or {}
        cfg = config or {}

        # 1. Campaign blueprint from CAA (Agent 3.1)
        caa_output = previous_outputs.get("campaign_architecture", {})
        blueprint = {
            "campaign_name": caa_output.get("campaign_name", ""),
            "objective": caa_output.get("objective", "OUTCOME_AWARENESS"),
            "total_budget_usd": caa_output.get("total_budget_usd", 0),
            "duration_days": caa_output.get("duration_days", 30),
            "funnel_stages": caa_output.get("funnel_stages", []),
            "placements": caa_output.get("placements", []),
            "special_ad_categories": caa_output.get(
                "special_ad_categories", []
            ),
        }

        # 2. Creative packages from CGA (Agent 3.2) — MUST be approved
        cga_output = previous_outputs.get("creative_generation", {})
        creative_packages = cga_output.get("creative_packages", [])
        approval_status = cga_output.get("approval_status", "")

        # 3. Persona profiles from WF1 APA
        persona_output = previous_outputs.get("audience_persona", {})
        persona_profiles = persona_output.get("persona_profiles", [])
        # Fallback: extract from blueprint funnel_stages audiences
        if not persona_profiles:
            for stage in blueprint.get("funnel_stages", []):
                for audience in stage.get("audiences", []):
                    persona_profiles.append(audience)

        # 4. Company model
        company = input_context.get("company", {})
        if not company:
            company = tenant_ctx.get("company", {})

        # 5. Meta credentials (per-tenant from tenant_context or config)
        meta_credentials = {
            "access_token": (
                tenant_ctx.get("meta_access_token", "")
                or cfg.get("meta_access_token", "")
            ),
            "ad_account_id": (
                tenant_ctx.get("meta_ad_account_id", "")
                or cfg.get("meta_ad_account_id", "")
            ),
            "page_id": (
                tenant_ctx.get("meta_page_id", "")
                or cfg.get("meta_page_id", "")
            ),
            "business_id": (
                tenant_ctx.get("meta_business_id", "")
                or cfg.get("meta_business_id", "")
            ),
        }

        # 6. Sandbox mode
        sandbox_mode = cfg.get(
            "meta_ads_sandbox_mode",
            tenant_ctx.get("meta_ads_sandbox_mode", True),
        )

        context = {
            "blueprint": blueprint,
            "creative_packages": creative_packages,
            "creative_approval_status": approval_status,
            "persona_profiles": persona_profiles,
            "company": company,
            "meta_credentials": meta_credentials,
            "sandbox_mode": sandbox_mode,
        }

        logger.info(
            "Context loaded: blueprint=%s, packages=%d, personas=%d, "
            "sandbox=%s",
            blueprint.get("campaign_name", "?"),
            len(creative_packages),
            len(persona_profiles),
            sandbox_mode,
        )

        return context

    def validate(self, context: dict[str, Any]) -> list[str]:
        """Validate that all required prerequisites are present.

        Returns a list of error messages (empty = valid).
        """
        errors = []

        # Campaign blueprint
        bp = context.get("blueprint", {})
        if not bp.get("campaign_name"):
            errors.append(
                "Campaign blueprint missing: run Campaign Architecture "
                "(Agent 3.1) first"
            )
        if not bp.get("funnel_stages"):
            errors.append(
                "Campaign blueprint has no funnel stages: run Campaign "
                "Architecture first"
            )

        # Creative packages
        packages = context.get("creative_packages", [])
        if not packages:
            errors.append(
                "No creative packages found: run Creative Generation "
                "(Agent 3.2) first"
            )

        # Validate each package has ad_units with images
        for i, pkg in enumerate(packages):
            ad_units = pkg.get("ad_units", [])
            if not ad_units:
                errors.append(
                    f"Creative package [{i}] has no ad units"
                )
            for j, unit in enumerate(ad_units):
                if not unit.get("image_url"):
                    errors.append(
                        f"Creative package [{i}] ad unit [{j}] "
                        "has no image_url"
                    )

        # Meta credentials
        creds = context.get("meta_credentials", {})
        if not creds.get("access_token"):
            errors.append(
                "Meta access_token missing: configure Meta Business "
                "Manager credentials"
            )
        if not creds.get("ad_account_id"):
            errors.append(
                "Meta ad_account_id missing: configure Meta Business "
                "Manager credentials"
            )

        return errors
