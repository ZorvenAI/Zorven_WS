"""7-phase publishing engine for Meta Ads.

Phase 1: Campaign Structure Creation (Meta Campaign, PAUSED)
Phase 2: Targeting Translation (persona → Meta targeting spec)
Phase 3: Creative Upload (GCS images → Meta Ad Images + Ad Creatives)
Phase 4: Ad Assembly + Preview Generation (NOT creating ads yet)
--- MANDATORY HUMAN APPROVAL GATE (handled by ApprovalManager) ---
Phase 6: Meta API Publish (create Ads + activate Campaign)
Phase 7: Verification + Campaign Registry Write

Phases 1-4 run in the initial /v1/execute call.
Phases 6-7 run after approval via /v1/approve.
"""

import logging
import time
from typing import Any

from app.logic.circuit_breaker import BreakerAction, get_breaker
from app.logic.guardrails import OutputGuardrails
from app.logic.rollback import RollbackManager
from app.services.meta_api_client import MetaApiClient
from app.services.targeting_translator import TargetingTranslator

logger = logging.getLogger(__name__)


class AdPubAnalyzer:
    """Executes the 7-phase ad publishing pipeline."""

    def __init__(
        self,
        meta_client: MetaApiClient,
        targeting_translator: TargetingTranslator,
        event_emitter=None,
    ):
        self._meta = meta_client
        self._targeting = targeting_translator
        self._events = event_emitter
        self._rollback = RollbackManager()

    async def analyze_and_prepare(
        self,
        context: dict[str, Any],
        tenant_id: str,
        job_id: str,
    ) -> dict[str, Any]:
        """Run phases 1-4: create campaign structure + generate previews.

        Returns a dict with all created entity IDs and preview data
        ready for human review.
        """
        start = time.time()
        bp = context["blueprint"]
        packages = context["creative_packages"]
        creds = context["meta_credentials"]
        ad_account_id = creds["ad_account_id"]
        company = context.get("company", {})
        industry = company.get("industry", "")

        # Initialize Meta API with tenant credentials
        self._meta.initialize(
            access_token=creds["access_token"],
            app_id=creds.get("app_id", ""),
            app_secret=creds.get("app_secret", ""),
        )

        # Phase 1: Create Campaign (PAUSED)
        logger.info("Phase 1: Creating campaign (PAUSED)")
        campaign_id = await self._create_campaign(
            ad_account_id, bp, context.get("sandbox_mode", True)
        )

        # Phase 2: Translate targeting
        logger.info("Phase 2: Translating targeting specs")
        personas = context.get("persona_profiles", [])
        targeting_results = await self._targeting.translate_all(
            personas=personas,
            industry=industry,
            special_ad_categories=bp.get("special_ad_categories", []),
            placements=bp.get("placements", []),
        )

        # Phase 3: Create Ad Sets + Upload Creatives
        logger.info("Phase 3: Creating ad sets + uploading creatives")
        logger.info(
            "Creative packages: count=%d, ad_unit_counts=%s",
            len(packages),
            [len(p.get("ad_units", [])) for p in packages],
        )
        for pi, pkg in enumerate(packages):
            logger.info(
                "Package[%d]: ad_set_name=%r, ad_units=%d, keys=%s",
                pi,
                pkg.get("ad_set_name"),
                len(pkg.get("ad_units", [])),
                (
                    list(pkg.get("ad_units", [{}])[0].keys())
                    if pkg.get("ad_units")
                    else []
                ),
            )
        ad_sets = []
        creatives = []
        total_daily_budget_cents = 0

        for i, stage in enumerate(bp.get("funnel_stages", [])):
            budget_pct = stage.get(
                "budget_pct", 1.0 / max(len(bp.get("funnel_stages", [])), 1)
            )
            daily_budget_usd = (
                bp["total_budget_usd"]
                * budget_pct
                / max(bp.get("duration_days", 30), 1)
            )
            daily_budget_cents = int(daily_budget_usd * 100)
            total_daily_budget_cents += daily_budget_cents

            # Get targeting for this stage's audience
            targeting_spec = {}
            if i < len(targeting_results):
                targeting_spec = targeting_results[i].get("targeting_spec", {})

            ad_set_name = f"{bp['campaign_name']} - {stage.get('stage', f'Stage {i}')}"
            ad_set_id = await self._create_ad_set(
                ad_account_id,
                campaign_id,
                ad_set_name,
                targeting_spec,
                daily_budget_cents,
                bp,
            )
            ad_sets.append(
                {
                    "ad_set_id": ad_set_id,
                    "ad_set_name": ad_set_name,
                    "daily_budget_cents": daily_budget_cents,
                    "targeting_spec": targeting_spec,
                    "stage": stage.get("stage", f"Stage {i}"),
                }
            )

            # Upload creatives for this ad set
            matching_packages = [
                p
                for p in packages
                if p.get("ad_set_name", "").startswith(stage.get("stage", ""))
            ] or packages[
                :1
            ]  # Fallback to first package

            for pkg in matching_packages:
                for unit in pkg.get("ad_units", []):
                    image_result = await self._upload_image(ad_account_id, unit)
                    creative_id = await self._create_creative(
                        ad_account_id,
                        unit,
                        image_result["hash"],
                        company,
                        page_id=creds.get("page_id", ""),
                    )
                    creatives.append(
                        {
                            "creative_id": creative_id,
                            "ad_set_id": ad_set_id,
                            "ad_set_name": ad_set_name,
                            "image_hash": image_result["hash"],
                            "image_url": (
                                image_result.get("url") or unit.get("image_url", "")
                            ),
                            "headline": unit.get("headline", ""),
                            "primary_text": unit.get("primary_text", ""),
                            "cta": unit.get("cta", "LEARN_MORE"),
                            "variant_label": unit.get("variant_label", ""),
                        }
                    )

        # Phase 4: Generate previews (NOT creating ads yet)
        logger.info("Phase 4: Generating ad previews")
        previews = []
        for creative in creatives:
            preview_html = await self._meta.get_ad_preview(creative["creative_id"])
            previews.append(
                {
                    **creative,
                    "preview_html": preview_html,
                }
            )

        elapsed_ms = int((time.time() - start) * 1000)

        return {
            "campaign_id": campaign_id,
            "campaign_name": bp["campaign_name"],
            "objective": bp.get("objective", ""),
            "ad_account_id": ad_account_id,
            "page_id": creds.get("page_id", ""),
            "ad_sets": ad_sets,
            "creatives": creatives,
            "previews": previews,
            "targeting_results": targeting_results,
            "total_daily_budget_usd": total_daily_budget_cents / 100,
            "duration_days": bp.get("duration_days", 30),
            "sandbox_mode": context.get("sandbox_mode", True),
            "preparation_time_ms": elapsed_ms,
            "rollback_entities": self._rollback.entities,
        }

    async def publish_after_approval(
        self,
        preparation: dict[str, Any],
        approval_result: dict[str, Any],
        tenant_id: str,
        job_id: str,
    ) -> dict[str, Any]:
        """Run phases 6-7: create ads, activate campaign, verify.

        Only called AFTER human approval.
        """
        start = time.time()
        campaign_id = preparation["campaign_id"]
        ad_account_id = preparation.get("ad_account_id", "")
        approved_sets = approval_result.get("approved_ad_sets")

        # Phase 6: Create Ads + Activate Campaign
        logger.info("Phase 6: Creating ads and activating campaign")
        ad_ids = []
        ad_set_ids = []
        creative_ids = []

        for creative in preparation["creatives"]:
            # Skip if partial approval and this ad set not approved
            if approved_sets and creative["ad_set_name"] not in approved_sets:
                continue

            ad_id = await self._create_ad(
                creative["ad_set_id"],
                creative["creative_id"],
                creative,
                ad_account_id=ad_account_id,
            )
            ad_ids.append(ad_id)
            if creative["ad_set_id"] not in ad_set_ids:
                ad_set_ids.append(creative["ad_set_id"])
            if creative["creative_id"] not in creative_ids:
                creative_ids.append(creative["creative_id"])

        # Activate approved ad sets and campaign
        for ad_set_id in ad_set_ids:
            await self._meta.update_ad_set_status(ad_set_id, "ACTIVE")

        await self._meta.update_campaign_status(campaign_id, "ACTIVE")

        # Phase 7: Verification
        logger.info("Phase 7: Verifying published entities")
        published = {
            "campaign_id": campaign_id,
            "campaign_status": "ACTIVE",
            "ad_set_ids": ad_set_ids,
            "ad_ids": ad_ids,
            "creative_ids": creative_ids,
        }

        output_check = OutputGuardrails().check(published)
        elapsed_ms = int((time.time() - start) * 1000)

        # Clear rollback tracker on success
        if output_check["all_valid"]:
            self._rollback.clear()

        return {
            "status": "published" if output_check["all_valid"] else "partial",
            "published_campaign": {
                "campaign_id": campaign_id,
                "campaign_name": preparation.get("campaign_name", ""),
                "campaign_status": "ACTIVE",
                "ad_sets": [{"ad_set_id": sid} for sid in ad_set_ids],
                "ads": [{"ad_id": aid} for aid in ad_ids],
                "creative_ids": creative_ids,
            },
            "daily_spend_committed_usd": preparation.get("total_daily_budget_usd", 0),
            "targeting_audience_size": sum(
                t.get("estimated_reach", 0)
                for t in preparation.get("targeting_results", [])
            ),
            "sandbox_mode": preparation.get("sandbox_mode", True),
            "approval_status": approval_result.get("status", "approved"),
            "verification": output_check,
            "approval_result": approval_result,
            "publishing_time_ms": elapsed_ms,
        }

    async def rollback(self, reason: str) -> dict[str, Any]:
        """Rollback all tracked entities (on failure)."""
        return await self._rollback.rollback_all(self._meta, reason)

    # ------------------------------------------------------------------
    # Private helpers with circuit breaker integration
    # ------------------------------------------------------------------

    async def _create_campaign(
        self,
        ad_account_id: str,
        blueprint: dict[str, Any],
        sandbox: bool,
    ) -> str:
        breaker = get_breaker("meta_campaign")
        if breaker.is_open:
            raise RuntimeError(
                f"Circuit breaker '{breaker.name}' is OPEN — " "cannot create campaign"
            )
        try:
            campaign_id = await self._meta.create_campaign(
                ad_account_id=ad_account_id,
                name=blueprint["campaign_name"],
                objective=blueprint.get("objective", "OUTCOME_AWARENESS"),
                special_ad_categories=blueprint.get("special_ad_categories", []),
            )
            breaker.record_success()
            self._rollback.track("campaign", campaign_id)
            return campaign_id
        except Exception as exc:
            trip = breaker.record_failure()
            if trip and trip["action"] == BreakerAction.ESCALATE.value:
                logger.critical("Campaign creation circuit breaker tripped: %s", exc)
            raise

    async def _create_ad_set(
        self,
        ad_account_id: str,
        campaign_id: str,
        name: str,
        targeting: dict[str, Any],
        daily_budget_cents: int,
        blueprint: dict[str, Any],
    ) -> str:
        breaker = get_breaker("meta_ad_set")
        if breaker.is_open:
            raise RuntimeError(
                f"Circuit breaker '{breaker.name}' is OPEN — " "cannot create ad set"
            )
        try:
            ad_set_id = await self._meta.create_ad_set(
                ad_account_id=ad_account_id,
                campaign_id=campaign_id,
                name=name,
                targeting=targeting,
                optimization_goal="REACH",
                billing_event="IMPRESSIONS",
                daily_budget_cents=daily_budget_cents,
            )
            breaker.record_success()
            self._rollback.track("ad_set", ad_set_id)
            return ad_set_id
        except Exception as exc:
            trip = breaker.record_failure()
            if trip:
                logger.critical("Ad set circuit breaker tripped: %s", exc)
                await self.rollback(f"Ad set creation failed: {exc}")
            raise

    async def _upload_image(
        self,
        ad_account_id: str,
        ad_unit: dict[str, Any],
    ) -> dict[str, str]:
        breaker = get_breaker("meta_ad_image")
        if breaker.is_open:
            raise RuntimeError(
                f"Circuit breaker '{breaker.name}' is OPEN — " "cannot upload image"
            )
        try:
            # Download image bytes from GCS or use pre-fetched bytes
            image_bytes = ad_unit.get("image_bytes", b"")
            if not image_bytes:
                image_url = ad_unit.get("image_url", "")
                if image_url:
                    image_bytes = await self._download_image(image_url)

            result = await self._meta.upload_image(
                ad_account_id=ad_account_id,
                image_bytes=image_bytes,
                name=ad_unit.get("image_url", "image.jpg"),
            )
            breaker.record_success()
            return result
        except Exception as exc:
            trip = breaker.record_failure()
            if trip and trip["action"] == BreakerAction.RETRY.value:
                logger.warning("Image upload breaker tripped — retry allowed: %s", exc)
            raise

    @staticmethod
    async def _download_image(url: str) -> bytes:
        """Download image bytes from a GCS signed URL or HTTP URL."""
        try:
            import httpx

            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.content
        except Exception as exc:
            logger.warning("Failed to download image from %s: %s", url, exc)
            return b""

    async def _create_creative(
        self,
        ad_account_id: str,
        ad_unit: dict[str, Any],
        image_hash: str,
        company: dict[str, Any],
        page_id: str = "",
    ) -> str:
        creative_id = await self._meta.create_ad_creative(
            ad_account_id=ad_account_id,
            name=f"Creative - {ad_unit.get('variant_label', 'A')}",
            image_hash=image_hash,
            headline=ad_unit.get("headline", ""),
            body=ad_unit.get("primary_text", ""),
            cta_type=ad_unit.get("cta", "LEARN_MORE"),
            link_url=ad_unit.get("link_url", company.get("website", "")),
            page_id=page_id,
        )
        return creative_id

    async def _create_ad(
        self,
        ad_set_id: str,
        creative_id: str,
        creative_info: dict[str, Any],
        ad_account_id: str = "",
    ) -> str:
        breaker = get_breaker("meta_ad")
        if breaker.is_open:
            raise RuntimeError(
                f"Circuit breaker '{breaker.name}' is OPEN — " "cannot create ad"
            )
        try:
            ad_id = await self._meta.create_ad(
                ad_account_id=ad_account_id,
                ad_set_id=ad_set_id,
                creative_id=creative_id,
                name=(
                    f"Ad - {creative_info.get('ad_set_name', '')} "
                    f"- {creative_info.get('variant_label', 'A')}"
                ),
            )
            breaker.record_success()
            self._rollback.track("ad", ad_id)
            return ad_id
        except Exception as exc:
            trip = breaker.record_failure()
            if trip:
                logger.critical(
                    "Ad creation circuit breaker tripped (STRICTEST): %s",
                    exc,
                )
                await self.rollback(f"Ad creation failed: {exc}")
            raise
