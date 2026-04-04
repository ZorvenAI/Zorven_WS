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
        creative_packages = self._extract_creative_packages(cga_output)
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
                tenant_ctx.get("meta_page_id", "") or cfg.get("meta_page_id", "")
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

        Stores diagnostic messages in context["_backend_diagnostics"]
        so validation errors can surface them to the user.
        """
        diagnostics: list[str] = []
        tenant_id = context.get("_tenant_id", "")

        if not tenant_id:
            msg = (
                "Backend enrichment skipped: no tenant_id in tenant_context. "
                "Ensure the pipeline dispatch includes tenant_context.tenant_id."
            )
            logger.warning(msg)
            diagnostics.append(msg)
            context["_backend_diagnostics"] = diagnostics
            return context

        logger.info(
            "Enriching from backend: tenant_id=%s, backend_url=%s, "
            "needs_caa=%s, needs_cga=%s",
            tenant_id,
            settings.backend_url,
            context.get("_needs_caa_fetch"),
            context.get("_needs_cga_fetch"),
        )

        headers = {
            "X-Service-Token": settings.BACKEND_SERVICE_TOKEN,
            "X-Tenant-ID": str(tenant_id),
        }

        async with httpx.AsyncClient(timeout=30) as client:
            # Fetch CAA blueprint if missing
            if context.get("_needs_caa_fetch"):
                caa_url = (
                    f"{settings.backend_url}/api/v1/analytics/caa-context/"
                )
                try:
                    logger.info("Fetching CAA context from: %s", caa_url)
                    resp = await client.get(caa_url, headers=headers)
                    if resp.status_code == 200:
                        caa_data = resp.json()
                        context["blueprint"] = self._extract_blueprint(caa_data)
                        bp_name = context["blueprint"].get("campaign_name", "?")
                        logger.info(
                            "CAA blueprint fetched from backend: %s", bp_name
                        )
                        diagnostics.append(
                            f"CAA fetch OK: campaign={bp_name}"
                        )
                    else:
                        body = resp.text[:300]
                        msg = (
                            f"CAA fetch failed: HTTP {resp.status_code} "
                            f"from {caa_url} (tenant={tenant_id}) — {body}"
                        )
                        logger.warning(msg)
                        diagnostics.append(msg)
                except Exception as exc:
                    msg = (
                        f"CAA fetch error: {exc} "
                        f"(url={caa_url}, tenant={tenant_id})"
                    )
                    logger.error(msg)
                    diagnostics.append(msg)

            # Fetch CGA creative packages if missing
            if context.get("_needs_cga_fetch"):
                cga_url = (
                    f"{settings.backend_url}/api/v1/analytics/cga-context/"
                )
                try:
                    logger.info("Fetching CGA context from: %s", cga_url)
                    resp = await client.get(cga_url, headers=headers)
                    if resp.status_code == 200:
                        cga_data = resp.json()
                        context["creative_packages"] = (
                            self._extract_creative_packages(cga_data)
                        )
                        pkg_count = len(context["creative_packages"])
                        logger.info(
                            "CGA packages fetched from backend: %d packages",
                            pkg_count,
                        )
                        diagnostics.append(
                            f"CGA fetch OK: {pkg_count} packages"
                        )
                    else:
                        body = resp.text[:300]
                        msg = (
                            f"CGA fetch failed: HTTP {resp.status_code} "
                            f"from {cga_url} (tenant={tenant_id}) — {body}"
                        )
                        logger.warning(msg)
                        diagnostics.append(msg)
                except Exception as exc:
                    msg = (
                        f"CGA fetch error: {exc} "
                        f"(url={cga_url}, tenant={tenant_id})"
                    )
                    logger.error(msg)
                    diagnostics.append(msg)

            # Fetch WF1 personas if still empty
            if not context.get("persona_profiles"):
                try:
                    resp = await client.get(
                        f"{settings.backend_url}/api/v1/analytics/wf1-context/",
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
        context["_backend_diagnostics"] = diagnostics

        return context

    @staticmethod
    def _extract_blueprint(caa_output: dict[str, Any]) -> dict[str, Any]:
        """Extract blueprint fields from CAA output.

        Handles both:
        - Direct CAA node output (pipeline chaining via previous_outputs)
        - The caa-context Django endpoint response

        CAA output structure:
          blueprint:
            campaign_name, campaign_objective, daily_budget,
            buying_type, bid_strategy, cbo_enabled,
            ad_sets: [{name, funnel_stage, targeting, placements, ...}]
          funnel_map:
            stages: [{stage, meta_objective, budget_pct}]
          targeting_specs: [...]
          placement_budget: {per_ad_set: [...]}
          special_ad_category: str
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
                "ad_sets": [],
                "funnel_map": {},
                "targeting_specs": [],
                "placement_budget": {},
                "raw_blueprint": {},
            }

        # The caa-context endpoint nests campaign data under 'blueprint'
        bp = caa_output.get("blueprint", caa_output)

        def _first(*keys: str, default: Any = None) -> Any:
            """Return first non-None value found across bp and caa_output."""
            for src in (bp, caa_output):
                for key in keys:
                    if key in src and src[key] is not None:
                        return src[key]
            return default

        # Campaign name
        campaign_name = _first("campaign_name", default="")

        # Objective: CAA uses "campaign_objective", normalize
        objective = _first(
            "campaign_objective", "objective", default="OUTCOME_AWARENESS"
        )

        # Budget: CAA uses "daily_budget"; also accept "total_budget_usd"
        daily_budget = _first("daily_budget", "total_budget_usd", default=0)

        # Duration
        duration_days = _first("duration_days", default=30)

        # Funnel stages: derive from blueprint.ad_sets or funnel_map.stages
        ad_sets = _first("ad_sets", default=[])
        funnel_map = caa_output.get("funnel_map", {})
        funnel_stages_raw = funnel_map.get("stages", [])

        # Build unified funnel_stages list from ad_sets (preferred) or
        # funnel_map stages
        funnel_stages = []
        if ad_sets:
            for ad_set in ad_sets:
                funnel_stages.append(ad_set)
        elif funnel_stages_raw:
            funnel_stages = funnel_stages_raw
        else:
            # Fallback: check for literal "funnel_stages" key
            funnel_stages = _first("funnel_stages", default=[])

        # Placements: collect from ad_sets or top-level
        placements = _first("placements", default=[])
        if not placements and ad_sets:
            seen = set()
            for ad_set in ad_sets:
                for p in ad_set.get("placements", []):
                    if p not in seen:
                        seen.add(p)
                        placements.append(p)

        # Special ad categories: CAA uses singular "special_ad_category"
        special_ad_categories = _first("special_ad_categories", default=[])
        if not special_ad_categories:
            cat = _first("special_ad_category", default="")
            if cat:
                special_ad_categories = [cat]

        # Targeting specs (top-level in caa-context response)
        targeting_specs = caa_output.get("targeting_specs", [])

        # Placement budget (top-level in caa-context response)
        placement_budget = caa_output.get("placement_budget", {})

        return {
            "campaign_name": campaign_name,
            "objective": objective,
            "total_budget_usd": daily_budget * duration_days,
            "daily_budget": daily_budget,
            "duration_days": duration_days,
            "funnel_stages": funnel_stages,
            "placements": placements,
            "special_ad_categories": special_ad_categories,
            "ad_sets": ad_sets,
            "funnel_map": funnel_map,
            "targeting_specs": targeting_specs,
            "placement_budget": placement_budget,
            "raw_blueprint": bp,
        }

    @staticmethod
    def _extract_creative_packages(cga_output: dict[str, Any]) -> list[dict]:
        """Extract creative packages from CGA output.

        CGA stores per-ad-set packages in "ad_set_packages", each with
        "creative_units" (assembled image+copy+CTA). This method maps
        them to the ad-publishing expected format: a list of dicts with
        "ad_set_name" and "ad_units".

        Also handles the already-mapped "creative_packages" key returned
        by the cga-context Django endpoint.
        """
        if not cga_output:
            return []

        # Already mapped (from cga-context endpoint)
        creative_packages = cga_output.get("creative_packages", [])
        if creative_packages:
            return creative_packages

        # Map from raw CGA output (pipeline chaining)
        ad_set_packages = cga_output.get("ad_set_packages", [])
        if ad_set_packages:
            packages = []
            for pkg in ad_set_packages:
                units = pkg.get("creative_units", [])
                packages.append(
                    {
                        "ad_set_name": pkg.get("ad_set_name", ""),
                        "persona": pkg.get("persona", ""),
                        "funnel_stage": pkg.get("funnel_stage", ""),
                        "ad_units": units,
                    }
                )
            return packages

        # Fallback: top-level ad_units
        ad_units = cga_output.get("ad_units", [])
        if ad_units:
            return [{"ad_set_name": "Default", "ad_units": ad_units}]

        return []

    def validate(self, context: dict[str, Any]) -> list[str]:
        """Validate that all required prerequisites are present.

        Returns a list of error messages (empty = valid).
        Includes backend fetch diagnostics if enrichment was attempted.
        """
        errors = []

        # Surface backend fetch diagnostics so failures are visible
        diagnostics = context.pop("_backend_diagnostics", [])
        if diagnostics:
            errors.append(
                "Backend enrichment diagnostics: " + " | ".join(diagnostics)
            )

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
                errors.append(f"Creative package [{i}] has no ad units")
            for j, unit in enumerate(ad_units):
                # CGA uses gcs_url; ad-publishing uses image_url
                has_image = (
                    unit.get("image_url") or unit.get("gcs_url") or unit.get("image")
                )
                if not has_image:
                    errors.append(
                        f"Creative package [{i}] ad unit [{j}] has no image"
                    )

        # Meta credentials (only required in production mode)
        if not context.get("sandbox_mode", True):
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
