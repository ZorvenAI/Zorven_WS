"""BSA Executor — orchestrates brand story & narrative analysis flow."""

import logging
import time
import uuid
from typing import Any

from app.cache.redis_manager import RedisManager
from app.messaging.event_emitter import EventEmitter, EventType
from app.messaging.kafka_producer import AuditProducer, TraceProducer
from app.services.bsa_analyzer import BSAAnalyzer
from app.services.context_loader import BSAContextLoader
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


class BSAExecutor:
    """Thin wrapper: cache → context load → analyze → GCS → cache → audit."""

    def __init__(
        self,
        analyzer: BSAAnalyzer,
        redis_manager: RedisManager,
        trace_producer: TraceProducer,
        audit_producer: AuditProducer,
        event_emitter: EventEmitter,
        context_loader: BSAContextLoader,
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
        """Execute brand story & narrative analysis."""
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
                "node_id": "brand_story",
                "status": "started",
                "tenant_id": tenant_id,
            }
        )
        await self._events.emit(EventType.SESSION_STARTED, tenant_id, job_id)

        try:
            # Check cache (hash prompt + context for uniqueness)
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
            contexts = await self._context.load_all(tenant_id)
            wf1_context = contexts["wf1"]
            bpa_context = contexts["bpa"]
            bpv_context = contexts["bpv"]
            nta_context = contexts["nta"]
            company_context = contexts["company"]

            # Emit context events
            for label, ctx, loaded_evt, missing_evt in [
                (
                    "WF1",
                    wf1_context,
                    EventType.WF1_CONTEXT_LOADED,
                    EventType.WF1_CONTEXT_MISSING,
                ),
                (
                    "BPA",
                    bpa_context,
                    EventType.BPA_CONTEXT_LOADED,
                    EventType.BPA_CONTEXT_MISSING,
                ),
                (
                    "BPV",
                    bpv_context,
                    EventType.BPV_CONTEXT_LOADED,
                    EventType.BPV_CONTEXT_MISSING,
                ),
                (
                    "NTA",
                    nta_context,
                    EventType.NTA_CONTEXT_LOADED,
                    EventType.NTA_CONTEXT_MISSING,
                ),
            ]:
                if ctx:
                    await self._events.emit(loaded_evt, tenant_id, job_id)
                else:
                    await self._events.emit(missing_evt, tenant_id, job_id)

            # Check for BAA context in previous_outputs
            baa_context = previous_outputs.get("brand_architecture")
            if baa_context:
                await self._events.emit(EventType.BAA_CONTEXT_LOADED, tenant_id, job_id)
            else:
                await self._events.emit(
                    EventType.BAA_CONTEXT_MISSING, tenant_id, job_id
                )

            # Prerequisite check: require WF1 + BPA + BPV + NTA
            has_wf1 = bool(wf1_context) or any(k in previous_outputs for k in _WF1_KEYS)
            has_bpa = bool(bpa_context) or bool(
                previous_outputs.get("brand_positioning")
            )
            has_bpv = bool(bpv_context) or bool(
                previous_outputs.get("brand_personality")
            )
            has_nta = bool(nta_context) or bool(previous_outputs.get("brand_naming"))

            if not has_wf1 or not has_bpa or not has_bpv or not has_nta:
                missing = []
                if not has_wf1:
                    missing.append("WF1 Brand Discovery")
                if not has_bpa:
                    missing.append("BPA Brand Positioning")
                if not has_bpv:
                    missing.append("BPV Brand Personality")
                if not has_nta:
                    missing.append("NTA Brand Naming")
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

            # BAA is recommended, not required — warn if missing
            if not baa_context:
                logger.info(
                    "BAA context not available for tenant %s "
                    "(recommended, not required)",
                    tenant_id,
                )

            # Execute analysis
            result = await self._analyzer.analyze(
                prompt=prompt,
                tenant_id=tenant_id,
                user_role=user_role,
                config=config,
                previous_outputs=previous_outputs,
                wf1_context=wf1_context,
                bpa_context=bpa_context,
                bpv_context=bpv_context,
                nta_context=nta_context,
                company_context=company_context,
                baa_context=baa_context,
                job_id=job_id,
            )

            # GCS persist
            gcs_uri = await self._gcs.upload_narrative(tenant_id, job_id, result)
            if gcs_uri:
                result["gcs_uri"] = gcs_uri
                await self._events.emit(
                    EventType.GCS_UPLOAD_COMPLETED,
                    tenant_id,
                    job_id,
                    {"gcs_uri": gcs_uri},
                )
            else:
                await self._events.emit(EventType.GCS_UPLOAD_FAILED, tenant_id, job_id)

            # Cache result
            await self._redis.cache_result(tenant_id, prompt_hash, result)

            # Save to story registry
            await self._redis.save_story(tenant_id, result)

        except Exception as exc:
            logger.error("BSA analysis failed: %s", exc, exc_info=True)
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
                    "node_id": "brand_story",
                    "status": "completed",
                    "tenant_id": tenant_id,
                }
            )
            await self._events.emit(
                EventType.SESSION_COMPLETED,
                tenant_id,
                job_id,
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
        "origin_story": {},
        "mission_vision": {},
        "pitches": {},
        "channel_narratives": {},
        "story_style_guide": {},
        "subbrand_stories": [],
        "narrative_package": {},
        "wf2_strategy_summary": {},
        "confidence_score": 0.0,
        "findings": findings or [],
        "recommendations": [],
        "sources": [],
        "wf1_context_used": False,
        "bpa_context_used": False,
        "bpv_context_used": False,
        "baa_context_used": False,
        "nta_context_used": False,
        "gcs_uri": "",
        "execution_time_ms": int((time.time() - start_time) * 1000),
    }
