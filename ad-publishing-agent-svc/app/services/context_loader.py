"""Context loader for the Ad Publishing Agent.

Loads all prerequisites from previous_outputs (pipeline chaining)
and/or Django backend endpoints:
- CGA creative packages (approved)
- CAA campaign blueprint
- APA persona profiles (WF1)
- Company model (website, industry)
- Meta credentials (per-tenant)

When running standalone (not chained after CAA/CGA in the same
pipeline), fetches context from Django analytics endpoints.
"""

import logging
from typing import Any

import httpx

from app.core.config import settings

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
        blueprint = self._extract_blueprint(caa_output)

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
            # Store tenant info for backend fallback
            "_tenant_id": tenant_ctx.get("tenant_id", ""),
            "_needs_caa_fetch": not caa_output,
            "_needs_cga_fetch": not cga_output,
        }

        logger.info(
            "Context loaded: blueprint=%s, packages=%d, personas=%d, "
            "sandbox=%s, needs_caa_fetch=%s, needs_cga_fetch=%s",
            blueprint.get("campaign_name", "?"),
            len(creative_packages),
            len(persona_profiles),
            sandbox_mode,
            not caa_output,
            not cga_output,
        )

        return context

    async def enrich_from_backend(self, context: dict[str, Any]) -> dict[str, Any]:
        """Fetch missing CAA/CGA context from Django backend.

        Called when previous_outputs didn't contain CAA or CGA data
        (standalone pipeline execution).
        """
        tenant_id = context.get("_tenant_id", "")
        if not tenant_id:
            logger.warning("No tenant_id — cannot fetch from backend")
            return context

        headers = {
            "X-Service-Token": settings.BACKEND_SERVICE_TOKEN,
            "X-Tenant-ID": str(tenant_id),
        }

        async with httpx.AsyncClient(timeout=30) as client:
            # Fetch CAA blueprint if missing
            if context.get("_needs_caa_fetch"):
                try:
                    resp = await client.get(
                        f"{settings.BACKEND_URL}/api/v1/analytics/caa-context/",
                        headers=headers,
                    )
                    if resp.status_code == 200:
                        caa_data = resp.json()
                        context["blueprint"] = self._extract_blueprint(caa_data)
                        logger.info(
                            "CAA blueprint fetched from backend: %s",
                            context["blueprint"].get("campaign_name", "?"),
                        )
                    else:
                        logger.warning(
                            "CAA context fetch failed: HTTP %d", resp.status_code
                        )
                except Exception as exc:
                    logger.warning("CAA context fetch error: %s", exc)

            # Fetch CGA creative packages if missing
            if context.get("_needs_cga_fetch"):
                try:
                    resp = await client.get(
                        f"{settings.BACKEND_URL}/api/v1/analytics/cga-context/",
                        headers=headers,
                    )
                    if resp.status_code == 200:
                        cga_data = resp.json()
                        context["creative_packages"] = cga_data.get(
                            "creative_packages", []
                        )
                        context["creative_approval_status"] = cga_data.get(
                            "approval_status", ""
                        )
                        logger.info(
                            "CGA packages fetched from backend: %d packages",
                            len(context["creative_packages"]),
                        )
                    else:
                        logger.warning(
                            "CGA context fetch failed: HTTP %d", resp.status_code
                        )
                except Exception as exc:
                    logger.warning("CGA context fetch error: %s", exc)

            # Fetch WF1 personas if still empty
            if not context.get("persona_profiles"):
                try:
                    resp = await client.get(
                        f"{settings.BACKEND_URL}/api/v1/analytics/wf1-context/",
                        headers=headers,
                    )
                    if resp.status_code == 200:
                        wf1_data = resp.json()
                        personas = wf1_data.get("persona_profiles", [])
                        if personas:
                            context["persona_profiles"] = personas
                            logger.info(
                                "WF1 personas fetched from backend: %d",
                                len(personas),
                            )
                except Exception as exc:
                    logger.warning("WF1 context fetch error: %s", exc)

        # Clean up internal flags
        context.pop("_needs_caa_fetch", None)
        context.pop("_needs_cga_fetch", None)

        return context

    @staticmethod
    def _extract_blueprint(caa_output: dict[str, Any]) -> dict[str, Any]:
        """Extract blueprint fields from CAA output.

        Handles both direct CAA output and the nested 'blueprint' key
        returned by the caa-context endpoint.
        """
        if not caa_output:
            return {
                "campaign_name": "",
                "objective": "OUTCOME_AWARENESS",
                "total_budget_usd": 0,
                "duration_days": 30,
                "funnel_stages": [],
                "placements": [],
                "special_ad_categories": [],
            }

        # The caa-context endpoint nests under 'blueprint'
        bp = caa_output.get("blueprint", caa_output)

        return {
            "campaign_name": (
                bp.get("campaign_name", "")
                or caa_output.get("campaign_name", "")
            ),
            "objective": (
                bp.get("objective", "")
                or caa_output.get("objective", "OUTCOME_AWARENESS")
            ),
            "total_budget_usd": (
                bp.get("total_budget_usd", 0)
                or caa_output.get("total_budget_usd", 0)
            ),
            "duration_days": (
                bp.get("duration_days", 30)
                or caa_output.get("duration_days", 30)
            ),
            "funnel_stages": (
                bp.get("funnel_stages", [])
                or caa_output.get("funnel_stages", [])
            ),
            "placements": (
                bp.get("placements", [])
                or caa_output.get("placements", [])
            ),
            "special_ad_categories": (
                bp.get("special_ad_categories", [])
                or caa_output.get("special_ad_categories", [])
            ),
        }

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
