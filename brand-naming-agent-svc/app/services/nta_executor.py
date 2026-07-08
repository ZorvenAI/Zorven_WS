"""NTA Executor — orchestrates naming & tagline analysis flow."""

import logging
import time
import uuid
from typing import Any

from app.cache.redis_manager import RedisManager
from app.messaging.event_emitter import EventEmitter, EventType
from app.messaging.kafka_producer import AuditProducer, TraceProducer
from app.services.nta_analyzer import NTAAnalyzer
from app.services.context_loader import NTAContextLoader

logger = logging.getLogger(__name__)

# WF1 node keys that indicate upstream data
_WF1_KEYS = {
    "market_research",
    "competitor_intelligence",
    "audience_persona",
    "trend_cultural",
    "voice_of_customer",
}


class NTAExecutor:
    """Thin wrapper: cache → context load → analyze → cache → audit."""

    def __init__(
        self,
        analyzer: NTAAnalyzer,
        redis_manager: RedisManager,
        trace_producer: TraceProducer,
        audit_producer: AuditProducer,
        event_emitter: EventEmitter,
        context_loader: NTAContextLoader,
    ):
        self._analyzer = analyzer
        self._redis = redis_manager
        self._trace = trace_producer
        self._audit = audit_producer
        self._events = event_emitter
        self._context = context_loader

    async def execute(
        self,
        prompt: str,
        input_context: dict[str, Any] | None = None,
        tenant_context: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
        previous_outputs: dict[str, Any] | None = None,
        tenant_id: str = "",
    ) -> dict[str, Any]:
        """Execute brand naming & tagline analysis."""
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
                "node_id": "brand_naming",
                "status": "started",
                "tenant_id": tenant_id,
            }
        )
        await self._events.emit(EventType.SESSION_STARTED, tenant_id, job_id)

        try:
            # Check cache
            prompt_hash = RedisManager.hash_prompt(prompt)
            cached = await self._redis.get_cached_result(tenant_id, prompt_hash)
            if cached:
                cached_confidence = cached.get("confidence_score", 0)
                if cached_confidence > 0.5:
                    logger.info(
                        "Cache hit for tenant %s (confidence=%.0f%%)",
                        tenant_id,
                        cached_confidence * 100,
                    )
                    result = cached
                    return result
                else:
                    logger.warning(
                        "Ignoring stale low-confidence cache (%.0f%%) for tenant %s",
                        cached_confidence * 100,
                        tenant_id,
                    )

            # Load contexts in parallel
            contexts = await self._context.load_all(tenant_id)
            wf1_context = contexts["wf1"]
            bpa_context = contexts["bpa"]
            bpv_context = contexts["bpv"]
            company_context = contexts["company"]

            # Emit context events
            if wf1_context:
                await self._events.emit(EventType.WF1_CONTEXT_LOADED, tenant_id, job_id)
            else:
                await self._events.emit(
                    EventType.WF1_CONTEXT_MISSING, tenant_id, job_id
                )

            if bpa_context:
                await self._events.emit(EventType.BPA_CONTEXT_LOADED, tenant_id, job_id)
            else:
                await self._events.emit(
                    EventType.BPA_CONTEXT_MISSING, tenant_id, job_id
                )

            if bpv_context:
                await self._events.emit(EventType.BPV_CONTEXT_LOADED, tenant_id, job_id)
            else:
                await self._events.emit(
                    EventType.BPV_CONTEXT_MISSING, tenant_id, job_id
                )

            # Check for BAA context in previous_outputs
            baa_context = previous_outputs.get("brand_architecture")
            if baa_context:
                await self._events.emit(EventType.BAA_CONTEXT_LOADED, tenant_id, job_id)
            else:
                await self._events.emit(
                    EventType.BAA_CONTEXT_MISSING, tenant_id, job_id
                )

            # Prerequisite check: require WF1 + BPA + BPV
            has_wf1 = bool(wf1_context) or any(k in previous_outputs for k in _WF1_KEYS)
            has_bpa = bool(bpa_context) or bool(
                previous_outputs.get("brand_positioning")
            )
            has_bpv = bool(bpv_context) or bool(
                previous_outputs.get("brand_personality")
            )

            if not has_wf1 or not has_bpa or not has_bpv:
                missing = []
                if not has_wf1:
                    missing.append("WF1 Brand Discovery")
                if not has_bpa:
                    missing.append("BPA Brand Positioning")
                if not has_bpv:
                    missing.append("BPV Brand Personality")
                result = _empty_result(
                    prompt,
                    start_time,
                    findings=[
                        f"Cannot proceed: {' and '.join(missing)} "
                        f"context required. Run the missing pipeline(s) first."
                    ],
                )
                return result

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
                company_context=company_context,
                baa_context=baa_context,
                job_id=job_id,
            )

            # Cache result
            await self._redis.cache_result(tenant_id, prompt_hash, result)

            # Save to naming registry
            await self._redis.save_naming(tenant_id, result)

        except Exception as exc:
            logger.error("NTA analysis failed: %s", exc, exc_info=True)
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
                    "node_id": "brand_naming",
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
        "name_candidates": [],
        "shortlisted_names": [],
        "taglines": [],
        "naming_brief": {},
        "availability_results": {},
        "scoring_summary": {},
        "confidence_score": 0.0,
        "findings": findings or [],
        "recommendations": [],
        "sources": [],
        "wf1_context_used": False,
        "bpa_context_used": False,
        "bpv_context_used": False,
        "baa_context_used": False,
        "execution_time_ms": int((time.time() - start_time) * 1000),
    }
