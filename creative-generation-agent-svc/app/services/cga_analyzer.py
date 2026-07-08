"""CGA Analyzer — 5-phase PAOR engine for creative generation.

Phase 1: Research + Image Generation
  - Creative context consolidation (SKL-CGA-01)
  - Creative learnings (SKL-CGA-03)
  - Input guardrails (IG-08, IG-09)
  - Claude call 1: Creative profiling + image prompt building (SKL-02, SKL-04)
  - Nano Banana 2 image generation (SKL-CGA-05)

Phase 2: Copy Generation (Claude call 2)
  - Hooks (SKL-CGA-07) + Primary copy (SKL-CGA-08) + CTAs (SKL-CGA-09)
  - Plan guardrails (PG-08, PG-10)

Phase 3: Assembly + Compliance (Claude call 3)
  - Compliance check (SKL-CGA-10)
  - Visual-copy assembly (SKL-CGA-11)
  - Package synthesis (SKL-CGA-12)

Phase 4: Validation (local)
  - Output guardrails (OG-04, OG-07)

Phase 5: Persist + Escalation
  - Redis + GCS (SKL-CGA-13)
  - Human escalation (SKL-CGA-14)
"""

import json
import logging
import time
from typing import Any

from app.cache.redis_manager import RedisManager
from app.core.config import settings
from app.logic.audience_creative_profiler import AudienceCreativeProfiler
from app.logic.copy_compliance_checker import CopyComplianceChecker
from app.logic.creative_context_loader import CreativeContextLoader
from app.logic.creative_learnings_loader import CreativeLearningsLoader
from app.logic.creative_package_synthesizer import CreativePackageSynthesizer
from app.logic.creative_persister import CreativePersister
from app.logic.cta_generator import CTAGenerator
from app.logic.guardrails import InputGuardrails, OutputGuardrails, PlanGuardrails
from app.logic.hook_generator import HookGenerator
from app.logic.human_escalation import HumanEscalation
from app.logic.image_generator import ImageGenerator
from app.logic.image_prompt_builder import ImagePromptBuilder
from app.logic.primary_copy_generator import PrimaryCopyGenerator
from app.logic.visual_copy_assembler import VisualCopyAssembler
from app.messaging.event_emitter import EventEmitter, EventType
from app.prompts.fallbacks import (
    FALLBACK_COMPLIANCE,
    FALLBACK_COPYWRITING,
    FALLBACK_CREATIVE_DIRECTOR,
)
from app.services.anthropic_client import AnthropicClient
from app.services.gcs_client import GCSClient

logger = logging.getLogger(__name__)


class CGAAnalyzer:
    """Five-phase engine: Research+ImageGen -> CopyGen -> Assembly -> Validate -> Persist."""

    def __init__(
        self,
        anthropic_client: AnthropicClient | None,
        image_gen_client: Any,
        event_emitter: EventEmitter,
        gcs_client: GCSClient | None = None,
        redis_manager: RedisManager | None = None,
        prompt_loader: Any = None,
    ):
        self._llm = anthropic_client
        self._image_gen = image_gen_client
        self._events = event_emitter
        self._gcs = gcs_client
        self._redis = redis_manager
        self._prompt_loader = prompt_loader

        # Skills
        self._context_loader = CreativeContextLoader()
        self._learnings_loader = CreativeLearningsLoader()
        self._audience_profiler = AudienceCreativeProfiler()
        self._image_prompt_builder = ImagePromptBuilder()
        self._image_generator = ImageGenerator()
        self._hook_generator = HookGenerator()
        self._primary_copy_generator = PrimaryCopyGenerator()
        self._cta_generator = CTAGenerator()
        self._compliance_checker = CopyComplianceChecker()
        self._visual_copy_assembler = VisualCopyAssembler()
        self._package_synthesizer = CreativePackageSynthesizer()
        self._persister = CreativePersister()
        self._escalation = HumanEscalation()
        self._input_guardrails = InputGuardrails()
        self._plan_guardrails = PlanGuardrails()
        self._output_guardrails = OutputGuardrails()

    async def analyze(
        self,
        prompt: str,
        tenant_id: str,
        user_role: str,
        config: dict[str, Any],
        previous_outputs: dict[str, Any],
        caa_context: dict[str, Any] | None,
        wf1_context: dict[str, Any] | None,
        bpa_context: dict[str, Any] | None,
        bpv_context: dict[str, Any] | None,
        nta_context: dict[str, Any] | None,
        bsa_context: dict[str, Any] | None,
        company_context: dict[str, Any] | None,
        job_id: str = "",
    ) -> dict[str, Any]:
        """Run full creative generation analysis."""
        start_time = time.time()
        findings: list[str] = []
        recommendations: list[str] = []
        sources: list[dict[str, Any]] = []

        # Track context usage
        caa_used = caa_context is not None
        wf1_used = wf1_context is not None
        bpa_used = bpa_context is not None
        bpv_used = bpv_context is not None
        nta_used = nta_context is not None
        bsa_used = bsa_context is not None
        company_used = company_context is not None

        if not self._llm:
            return self._stub_result(
                prompt,
                start_time,
                caa_used=caa_used,
                wf1_used=wf1_used,
                bpa_used=bpa_used,
                bpv_used=bpv_used,
                nta_used=nta_used,
                bsa_used=bsa_used,
                company_used=company_used,
            )

        # ── Phase 1: Research + Image Generation ──
        await self._events.emit(
            EventType.CREATIVE_PROFILING_STARTED, tenant_id, job_id,
            {"phase": "research_and_image_gen"},
        )

        # SKL-CGA-01: Build unified creative context
        creative_context = self._context_loader.build_context(
            caa_context=caa_context,
            wf1_context=wf1_context,
            bpa_context=bpa_context,
            bpv_context=bpv_context,
            nta_context=nta_context,
            bsa_context=bsa_context,
            company_context=company_context,
        )

        # SKL-CGA-03: Creative learnings
        learnings = self._learnings_loader.load(previous_outputs or {})

        # Input guardrails (IG-08, IG-09)
        input_issues = self._input_guardrails.check(caa_context, company_context)
        if input_issues:
            findings.extend(input_issues)

        # Claude call 1: Creative profiling + image prompt building
        profiler_section = self._audience_profiler.build_prompt_section(
            creative_context
        )
        image_prompt_section = self._image_prompt_builder.build_prompt_section(
            creative_context
        )

        # Build brand summary for system prompt
        brand_name = creative_context.get("name_tagline", {}).get(
            "brand_name", ""
        ) or creative_context.get("company", {}).get("name", "")
        brand_desc = creative_context.get("company", {}).get("description", "")
        brand_industry = creative_context.get("company", {}).get("industry", "")

        if self._prompt_loader is not None:
            call1_system = await self._prompt_loader.load(
                "zorven-wf3-cga-creative-director",
                tenant_id=tenant_id,
                fallback=FALLBACK_CREATIVE_DIRECTOR,
            )
        else:
            # Brand-specific construction when no catalog is available
            call1_system = (
                "You are a creative director for Meta Ads campaigns"
            )
            if brand_name:
                call1_system += f" for {brand_name}"
                if brand_industry:
                    call1_system += f", a {brand_industry} brand"
            call1_system += (
                ". Given brand context, audience personas, and campaign "
                "architecture, generate creative profiles for each audience x "
                "funnel combination and detailed AI image generation prompts.\n\n"
                "CRITICAL: Every image prompt MUST be specific to this brand and "
                "its products/services. The images will be used as actual brand "
                "assets for social media and ad campaigns. Generic stock imagery "
                "is unacceptable.\n\n"
                "Respond with a JSON object containing: creative_profiles, "
                "image_prompts, findings, recommendations, sources."
            )
        call1_user = (
            f"## Campaign Brief\n{prompt}\n\n"
            f"{profiler_section}\n\n"
            f"{image_prompt_section}"
        )
        if learnings.get("available"):
            call1_user += (
                f"\n\n## Creative Learnings from Prior Campaigns\n"
                f"{json.dumps(learnings, default=str)[:2000]}\n"
            )

        call1_result = await self._llm.generate_json(call1_system, call1_user)

        creative_profiles = call1_result.get("creative_profiles", [])
        image_prompts = call1_result.get("image_prompts", [])
        findings.extend(call1_result.get("findings", []))
        recommendations.extend(call1_result.get("recommendations", []))
        sources.extend(call1_result.get("sources", []))

        await self._events.emit(
            EventType.CREATIVE_PROFILING_COMPLETED, tenant_id, job_id,
            {
                "profiles_count": len(creative_profiles),
                "image_prompts_count": len(image_prompts),
            },
        )

        # SKL-CGA-05: Image generation via Nano Banana 2
        image_gen_failed = False
        generated_images: list[dict[str, Any]] = []
        total_images = 0
        image_gen_cost = 0.0

        if image_prompts and self._image_gen:
            await self._events.emit(
                EventType.IMAGE_GENERATION_STARTED, tenant_id, job_id,
                {"prompts_count": len(image_prompts)},
            )

            try:
                gen_result = await self._image_generator.generate_all(
                    image_prompts=image_prompts,
                    image_gen_client=self._image_gen,
                    gcs_client=self._gcs,
                    tenant_id=tenant_id,
                    job_id=job_id,
                )
                generated_images = gen_result.get("generated_images", [])
                total_images = gen_result.get("total_images", 0)
                image_gen_cost = gen_result.get("total_cost_usd", 0.0)
                failed_count = gen_result.get("failed_count", 0)

                if failed_count > 0:
                    failure_reasons = gen_result.get("failure_reasons", [])
                    reasons_str = (
                        "; ".join(failure_reasons)
                        if failure_reasons
                        else "see logs"
                    )
                    findings.append(
                        f"Image generation: {failed_count} images failed "
                        f"out of {total_images + failed_count} attempted. "
                        f"Reasons: {reasons_str}"
                    )
                if total_images == 0 and failed_count > 0:
                    image_gen_failed = True
                    first_reason = (
                        gen_result.get("failure_reasons", ["unknown"])[0]
                        if gen_result.get("failure_reasons")
                        else "unknown"
                    )
                    findings.append(
                        f"CRITICAL: Image generation produced 0 images "
                        f"({failed_count} attempts failed). "
                        f"First reason: {first_reason}. "
                        "Creative package will contain copy only."
                    )

                await self._events.emit(
                    EventType.IMAGE_GENERATION_COMPLETED, tenant_id, job_id,
                    {
                        "total_images": total_images,
                        "failed_count": failed_count,
                        "cost_usd": image_gen_cost,
                    },
                )
            except Exception as exc:
                image_gen_failed = True
                logger.error(
                    "Image generation failed entirely: %s: %s",
                    type(exc).__name__,
                    exc,
                    exc_info=True,
                )
                findings.append(
                    f"CRITICAL: Image generation failed entirely. "
                    f"{type(exc).__name__}: {exc}. "
                    "Creative package will contain copy only."
                )
                await self._events.emit(
                    EventType.IMAGE_GENERATION_FAILED, tenant_id, job_id,
                    {"error": str(exc)},
                )
        elif not image_prompts:
            findings.append(
                "No image prompts generated by Claude — "
                "check CAA blueprint for ad_sets"
            )
            image_gen_failed = True

        # ── Phase 2: Copy Generation (Claude call 2) ──
        await self._events.emit(
            EventType.COPY_GENERATION_STARTED, tenant_id, job_id,
            {"phase": "copy_generation"},
        )

        hook_section = self._hook_generator.build_prompt_section(
            creative_context
        )
        copy_section = self._primary_copy_generator.build_prompt_section(
            creative_context
        )
        cta_section = self._cta_generator.build_prompt_section(
            creative_context
        )

        if self._prompt_loader is not None:
            call2_system = await self._prompt_loader.load(
                "zorven-wf3-cga-copywriting",
                tenant_id=tenant_id,
                fallback=FALLBACK_COPYWRITING,
            )
        else:
            call2_system = FALLBACK_COPYWRITING
        call2_user = (
            f"## Campaign Brief\n{prompt}\n\n"
            f"{hook_section}\n\n"
            f"{copy_section}\n\n"
            f"{cta_section}"
        )

        call2_result = await self._llm.generate_json(call2_system, call2_user)

        hooks = call2_result.get("hooks", [])
        primary_copy = call2_result.get("primary_copy", [])
        ctas = call2_result.get("ctas", [])
        findings.extend(call2_result.get("findings", []))
        recommendations.extend(call2_result.get("recommendations", []))

        # Plan guardrails (PG-08, PG-10)
        plan_issues = self._plan_guardrails.check(
            call2_result, caa_context or {}
        )
        if plan_issues:
            findings.extend(plan_issues)

        await self._events.emit(
            EventType.COPY_GENERATION_COMPLETED, tenant_id, job_id,
            {
                "hooks_count": len(hooks),
                "copy_sets_count": len(primary_copy),
                "ctas_count": len(ctas),
            },
        )

        # ── Phase 3: Assembly + Compliance (Claude call 3) ──
        compliance_section = self._compliance_checker.build_prompt_section(
            creative_context
        )
        assembly_section = self._visual_copy_assembler.build_prompt_section(
            creative_context, generated_images
        )
        package_section = self._package_synthesizer.build_prompt_section(
            creative_context
        )

        if self._prompt_loader is not None:
            call3_system = await self._prompt_loader.load(
                "zorven-wf3-cga-compliance",
                tenant_id=tenant_id,
                fallback=FALLBACK_COMPLIANCE,
            )
        else:
            call3_system = FALLBACK_COMPLIANCE

        # Build context with all generated assets
        # Strip data/thumbnail URIs from images for LLM — only metadata needed
        _STRIP_KEYS = {"gcs_url", "thumbnail_url", "image_generated"}
        images_for_llm = [
            {k: v for k, v in img.items() if k not in _STRIP_KEYS}
            for img in generated_images
        ]
        call3_user = (
            f"## Generated Hooks\n{_fmt(hooks)}\n\n"
            f"## Generated Primary Copy\n{_fmt(primary_copy)}\n\n"
            f"## Generated CTAs\n{_fmt(ctas)}\n\n"
            f"## Generated Images\n{_fmt(images_for_llm)}\n\n"
            f"## Image Generation Stats\n"
            f"- Total images: {total_images}\n"
            f"- Image gen cost: ${image_gen_cost:.4f}\n"
            f"- Image gen failed: {image_gen_failed}\n\n"
            f"{compliance_section}\n\n"
            f"{assembly_section}\n\n"
            f"{package_section}"
        )

        # Call 3 emits the largest payload (compliance_results + creative_units
        # + ad_set_packages for every audience × funnel). The default 8192
        # token cap truncates mid-JSON on multi-ad-set campaigns, which used
        # to surface as empty ad_set_packages downstream. Give it headroom.
        call3_result = await self._llm.generate_json(
            call3_system, call3_user, max_tokens=16384
        )

        compliance_results = call3_result.get("compliance_results", [])
        creative_units = call3_result.get("creative_units", []) or call3_result.get("ad_units", [])
        ad_set_packages = call3_result.get("ad_set_packages", [])
        creative_quality_score = call3_result.get(
            "creative_quality_score", 0.0
        )
        confidence = call3_result.get("confidence_score", 0.0)
        findings.extend(call3_result.get("findings", []))
        recommendations.extend(call3_result.get("recommendations", []))
        sources.extend(call3_result.get("sources", []))

        await self._events.emit(
            EventType.COMPLIANCE_CHECK_COMPLETED, tenant_id, job_id,
            {"compliance_results_count": len(compliance_results)},
        )
        await self._events.emit(
            EventType.ASSEMBLY_COMPLETED, tenant_id, job_id,
            {
                "creative_units_count": len(creative_units),
                "ad_set_packages_count": len(ad_set_packages),
            },
        )

        # Calculate compliance pass rate
        total_checks = len(compliance_results)
        passed_checks = sum(
            1
            for c in compliance_results
            if isinstance(c, dict) and c.get("status") in ("pass", "warning")
        )
        compliance_pass_rate = (
            passed_checks / total_checks if total_checks > 0 else 1.0
        )

        # ── Phase 4: Validation ──
        # Replace full-size data URIs with thumbnails for callback (1MB limit).
        # Full images are ~1.2MB base64 each; thumbnails are ~10-20KB.
        response_images = []
        for img in generated_images:
            url = img.get("gcs_url", "")
            thumb = img.get("thumbnail_url", "")
            if url.startswith("data:"):
                # Swap full image for thumbnail in gcs_url so frontend renders it
                response_images.append(
                    {**img, "gcs_url": thumb or "", "image_generated": True}
                )
            else:
                response_images.append(img)

        result = {
            "query": prompt,
            "creative_package": {
                "campaign_id": (caa_context or {}).get("campaign_id", ""),
                "brand_name": creative_context.get("name_tagline", {}).get(
                    "brand_name", ""
                ),
                "total_images_generated": total_images,
                "total_images_refined": 0,
                "image_gen_cost_usd": round(image_gen_cost, 4),
                "compliance_pass_rate": round(compliance_pass_rate, 4),
                "creative_quality_score": creative_quality_score,
                "confidence_score": confidence,
            },
            "ad_set_packages": ad_set_packages,
            "ad_units": creative_units,
            "generated_images": response_images,
            "hooks": hooks,
            "copy_variants": primary_copy,
            "ctas": ctas,
            "compliance_results": compliance_results,
            "creative_profiles": creative_profiles,
            "total_images_generated": total_images,
            "total_images_refined": 0,
            "image_gen_cost_usd": round(image_gen_cost, 4),
            "compliance_pass_rate": round(compliance_pass_rate, 4),
            "creative_quality_score": creative_quality_score,
            "confidence_score": confidence,
            "findings": findings,
            "recommendations": recommendations,
            "sources": sources,
            "caa_context_used": caa_used,
            "wf1_context_used": wf1_used,
            "bpa_context_used": bpa_used,
            "bpv_context_used": bpv_used,
            "nta_context_used": nta_used,
            "bsa_context_used": bsa_used,
            "company_context_used": company_used,
            "image_gen_failed": image_gen_failed,
        }

        # Output guardrails (OG-04, OG-07)
        output_issues = self._output_guardrails.check(result)
        if output_issues:
            result["findings"].extend(output_issues)

        # ── Phase 5: Persist + Escalation ──
        gcs_uri = await self._persister.persist(
            result=result,
            redis_manager=self._redis,
            gcs_client=self._gcs,
            tenant_id=tenant_id,
            job_id=job_id,
        )
        result["gcs_uri"] = gcs_uri

        if gcs_uri:
            await self._events.emit(
                EventType.GCS_UPLOAD_COMPLETED, tenant_id, job_id,
                {"gcs_uri": gcs_uri},
            )

        # Human escalation check
        escalation = self._escalation.check(
            result, threshold=settings.CONFIDENCE_THRESHOLD
        )
        if escalation.get("escalate"):
            result["findings"].append(
                f"Human review recommended: "
                f"{'; '.join(escalation.get('reasons', []))}"
            )
            await self._events.emit(
                EventType.ESCALATION_TRIGGERED, tenant_id, job_id,
                escalation,
            )

        elapsed_ms = int((time.time() - start_time) * 1000)
        result["execution_time_ms"] = elapsed_ms

        await self._events.emit(
            EventType.SESSION_COMPLETED, tenant_id, job_id,
            {
                "execution_time_ms": elapsed_ms,
                "total_images": total_images,
                "image_gen_cost_usd": image_gen_cost,
                "confidence_score": confidence,
            },
        )

        logger.info(
            "CGA analysis complete: %d images, %d units, "
            "cost $%.4f, confidence %.2f, %dms",
            total_images,
            len(creative_units),
            image_gen_cost,
            confidence,
            elapsed_ms,
        )

        return result

    def _stub_result(
        self,
        prompt: str,
        start_time: float,
        caa_used: bool = False,
        wf1_used: bool = False,
        bpa_used: bool = False,
        bpv_used: bool = False,
        nta_used: bool = False,
        bsa_used: bool = False,
        company_used: bool = False,
    ) -> dict[str, Any]:
        """Return stub when LLM is unavailable."""
        return {
            "query": prompt,
            "creative_package": {},
            "ad_set_packages": [],
            "ad_units": [],
            "generated_images": [],
            "hooks": [],
            "copy_variants": [],
            "ctas": [],
            "compliance_results": [],
            "creative_profiles": [],
            "total_images_generated": 0,
            "total_images_refined": 0,
            "image_gen_cost_usd": 0.0,
            "compliance_pass_rate": 0.0,
            "creative_quality_score": 0.0,
            "confidence_score": 0.0,
            "findings": [
                "LLM unavailable — creative generation requires Claude"
            ],
            "recommendations": [],
            "sources": [],
            "caa_context_used": caa_used,
            "wf1_context_used": wf1_used,
            "bpa_context_used": bpa_used,
            "bpv_context_used": bpv_used,
            "nta_context_used": nta_used,
            "bsa_context_used": bsa_used,
            "company_context_used": company_used,
            "image_gen_failed": True,
            "gcs_uri": "",
            "execution_time_ms": int((time.time() - start_time) * 1000),
        }


def _fmt(data: Any) -> str:
    """Format data as compact JSON for prompt injection."""
    return json.dumps(data, indent=None, default=str)[:4000]
