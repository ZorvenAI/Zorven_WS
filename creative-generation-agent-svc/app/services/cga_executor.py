"""CGA Executor — orchestrates creative generation flow."""

import logging
import time
import uuid
from typing import Any

from app.cache.redis_manager import RedisManager
from app.messaging.event_emitter import EventEmitter, EventType
from app.messaging.kafka_producer import AuditProducer, TraceProducer
from app.services.cga_analyzer import CGAAnalyzer
from app.services.context_loader import CGAContextLoader
from app.services.gcs_client import GCSClient

logger = logging.getLogger(__name__)

# WF1 node keys that indicate upstream data
_WF1_KEYS = {
    "market_research",
    "competitor_intelligence",
    "audience_persona",
    "trend_cultural",
    "voice_of_customer",
}


class CGAExecutor:
    """Thin wrapper: cache -> context load -> analyze -> cache -> audit."""

    def __init__(
        self,
        analyzer: CGAAnalyzer,
        redis_manager: RedisManager,
        trace_producer: TraceProducer,
        audit_producer: AuditProducer,
        event_emitter: EventEmitter,
        context_loader: CGAContextLoader,
        gcs_client: GCSClient,
    ):
        self._analyzer = analyzer
        self._redis = redis_manager
        self._trace = trace_producer
        self._audit = audit_producer
        self._events = event_emitter
        self._context = context_loader
        self._gcs = gcs_client

    async def execute(
        self,
        prompt: str,
        input_context: dict[str, Any] | None = None,
        tenant_context: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
        previous_outputs: dict[str, Any] | None = None,
        tenant_id: str = "",
    ) -> dict[str, Any]:
        """Execute creative generation for a campaign."""
        input_context = input_context or {}
        tenant_context = tenant_context or {}
        config = config or {}
        previous_outputs = previous_outputs or {}
        start_time = time.time()

        job_id = input_context.get("job_id", str(uuid.uuid4()))
        tenant_id = tenant_id or tenant_context.get("tenant_id", "unknown")
        user_role = tenant_context.get("user_role", "VIEWER")

        # Trace: started
        await self._trace.send_trace(
            {
                "job_id": job_id,
                "node_id": "creative_generation",
                "status": "started",
                "tenant_id": tenant_id,
            }
        )
        await self._events.emit(EventType.SESSION_STARTED, tenant_id, job_id)

        try:
            # Check cache
            prompt_hash = RedisManager.hash_inputs(
                prompt,
                input_context=input_context,
                config=config,
            )
            cached = await self._redis.get_cached_result(tenant_id, prompt_hash)
            if cached:
                logger.info("Cache hit for tenant %s", tenant_id)
                await self._events.emit(EventType.CACHE_HIT, tenant_id, job_id)
                return cached

            # Load contexts in parallel
            contexts = await self._context.load_all(
                tenant_id, previous_outputs=previous_outputs
            )
            caa_context = contexts["caa"]
            wf1_context = contexts["wf1"]
            bpa_context = contexts["bpa"]
            bpv_context = contexts["bpv"]
            nta_context = contexts["nta"]
            bsa_context = contexts["bsa"]
            company_context = contexts["company"]

            # Emit context events
            if caa_context:
                await self._events.emit(
                    EventType.CAA_CONTEXT_LOADED, tenant_id, job_id
                )
            else:
                await self._events.emit(
                    EventType.CAA_CONTEXT_MISSING, tenant_id, job_id
                )

            if wf1_context:
                await self._events.emit(
                    EventType.WF1_CONTEXT_LOADED, tenant_id, job_id
                )
            else:
                await self._events.emit(
                    EventType.WF1_CONTEXT_MISSING, tenant_id, job_id
                )

            if bpv_context:
                await self._events.emit(
                    EventType.WF2_CONTEXT_LOADED, tenant_id, job_id
                )
            elif bpa_context or nta_context:
                await self._events.emit(
                    EventType.WF2_CONTEXT_LOADED, tenant_id, job_id
                )
            else:
                await self._events.emit(
                    EventType.WF2_CONTEXT_MISSING, tenant_id, job_id
                )

            if company_context:
                await self._events.emit(
                    EventType.COMPANY_CONTEXT_LOADED, tenant_id, job_id
                )
            else:
                await self._events.emit(
                    EventType.COMPANY_CONTEXT_MISSING, tenant_id, job_id
                )

            # Prerequisite check: CAA + WF1 APA + WF2 (BPV+BPA+NTA) + Company
            has_caa = bool(caa_context) or bool(
                previous_outputs.get("campaign_architecture")
            )
            has_wf1 = bool(wf1_context) or any(
                k in previous_outputs for k in _WF1_KEYS
            )
            has_bpa = bool(bpa_context) or bool(
                previous_outputs.get("brand_positioning")
            )
            has_bpv = bool(bpv_context) or bool(
                previous_outputs.get("brand_personality")
            )
            has_nta = bool(nta_context) or bool(
                previous_outputs.get("brand_naming")
            )
            has_company = bool(company_context)

            missing = []
            if not has_caa:
                missing.append("CAA Campaign Architecture")
            if not has_wf1:
                missing.append("WF1 Brand Discovery (APA)")
            if not has_bpa:
                missing.append("BPA Brand Positioning")
            if not has_bpv:
                missing.append("BPV Brand Personality")
            if not has_nta:
                missing.append("NTA Brand Naming")
            if not has_company:
                missing.append("Company model")

            if missing:
                await self._events.emit(
                    EventType.PREREQUISITE_MISSING,
                    tenant_id,
                    job_id,
                    {"missing": missing},
                )
                return _empty_result(
                    prompt,
                    start_time,
                    findings=[
                        f"Cannot proceed: {' and '.join(missing)} "
                        f"context required. Run the missing pipeline(s) first."
                    ],
                )

            # BSA is optional — warn if missing
            if not bsa_context and not previous_outputs.get("brand_story"):
                logger.info(
                    "BSA context not available for tenant %s "
                    "(optional for creative generation)",
                    tenant_id,
                )

            # Use CAA from previous_outputs if not loaded via context
            if not caa_context and previous_outputs.get("campaign_architecture"):
                caa_context = previous_outputs["campaign_architecture"]

            # Execute analysis
            result = await self._analyzer.analyze(
                prompt=prompt,
                tenant_id=tenant_id,
                user_role=user_role,
                config=config,
                previous_outputs=previous_outputs,
                caa_context=caa_context,
                wf1_context=wf1_context,
                bpa_context=bpa_context,
                bpv_context=bpv_context,
                nta_context=nta_context,
                bsa_context=bsa_context,
                company_context=company_context,
                job_id=job_id,
            )

            # Cache result
            await self._redis.cache_result(tenant_id, prompt_hash, result)

        except Exception as exc:
            logger.error("CGA analysis failed: %s", exc, exc_info=True)
            result = _empty_result(
                prompt,
                start_time,
                findings=[f"Analysis failed: {exc}"],
            )

        finally:
            # Trace: completed
            await self._trace.send_trace(
                {
                    "job_id": job_id,
                    "node_id": "creative_generation",
                    "status": "completed",
                    "tenant_id": tenant_id,
                }
            )

        return result


def _empty_result(
    prompt: str,
    start_time: float,
    findings: list[str] | None = None,
) -> dict[str, Any]:
    """Build empty error/prerequisite-failure result."""
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
        "findings": findings or [],
        "recommendations": [],
        "sources": [],
        "caa_context_used": False,
        "wf1_context_used": False,
        "bpa_context_used": False,
        "bpv_context_used": False,
        "nta_context_used": False,
        "bsa_context_used": False,
        "company_context_used": False,
        "image_gen_failed": False,
        "gcs_uri": "",
        "execution_time_ms": int((time.time() - start_time) * 1000),
    }
