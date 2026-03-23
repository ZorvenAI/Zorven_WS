"""BPAExecutor — Thin orchestration wrapper for the Brand Positioning Agent.

Flow: cache check → load WF1 context → delegate to BPAAnalyzer →
      cache result → audit event.
"""

import logging
import uuid
from typing import Any

from app.cache.redis_manager import RedisManager
from app.messaging.event_emitter import EventEmitter, EventType
from app.messaging.kafka_producer import AuditProducer, TraceProducer
from app.services.bpa_analyzer import BPAAnalyzer
from app.services.wf1_loader import WF1ContextLoader

logger = logging.getLogger(__name__)


class BPAExecutor:
    """Top-level executor for brand positioning requests."""

    def __init__(
        self,
        analyzer: BPAAnalyzer,
        redis_manager: RedisManager,
        trace_producer: TraceProducer,
        audit_producer: AuditProducer,
        event_emitter: EventEmitter,
        wf1_loader: WF1ContextLoader,
    ) -> None:
        self._analyzer = analyzer
        self._redis = redis_manager
        self._trace = trace_producer
        self._audit = audit_producer
        self._events = event_emitter
        self._wf1_loader = wf1_loader

    async def execute(
        self,
        prompt: str,
        input_context: dict[str, Any],
        tenant_context: dict[str, Any],
        config: dict[str, Any],
        previous_outputs: dict[str, Any],
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        """Execute a brand positioning request."""
        job_id = input_context.get("job_id", str(uuid.uuid4()))
        user_role = tenant_context.get("user_role", "EDITOR")
        skill_context = config.get("skill_context", "")

        # Emit trace: started
        await self._trace.send_trace(
            job_id=job_id,
            status="started",
            message=f"Brand positioning: {prompt[:80]}",
        )

        # Emit session started event
        await self._events.emit(
            EventType.SESSION_STARTED,
            tenant_id=tenant_id,
            session_id=job_id,
            data={"prompt_preview": prompt[:200]},
        )

        # Check cache
        cached = await self._redis.get_cached_result(prompt, config, tenant_id)
        if cached:
            logger.info("Cache hit for job %s", job_id)
            await self._trace.send_trace(
                job_id=job_id,
                status="completed",
                message="Result served from cache",
            )
            return cached

        try:
            # Load WF1 context from Django backend
            wf1_context = await self._wf1_loader.load(tenant_id)
            if wf1_context:
                await self._events.emit(
                    EventType.WF1_CONTEXT_LOADED,
                    tenant_id=tenant_id,
                    session_id=job_id,
                    data={
                        "snapshot_id": wf1_context.get("snapshot_id"),
                        "wf1_job_id": wf1_context.get("wf1_job_id"),
                    },
                )
            else:
                await self._events.emit(
                    EventType.WF1_CONTEXT_MISSING,
                    tenant_id=tenant_id,
                    session_id=job_id,
                )
                # Not a hard failure — BPA can work with previous_outputs
                # from the orchestrator pipeline
                if not previous_outputs:
                    logger.warning(
                        "No WF1 data and no previous_outputs for tenant %s",
                        tenant_id,
                    )

            # Execute analysis
            result = await self._analyzer.analyze(
                prompt,
                tenant_id=tenant_id,
                user_role=user_role,
                config=config,
                previous_outputs=previous_outputs,
                wf1_context=wf1_context or {},
                skill_context=skill_context,
            )

            # Cache result
            await self._redis.cache_result(prompt, config, result, tenant_id)

            # Emit audit event
            await self._audit.send_event(
                event_type="BPA_POSITIONING_COMPLETED",
                event_name="bpa_positioning_completed",
                tenant_id=tenant_id,
                session_id=job_id,
                data={
                    "query": prompt[:500],
                    "confidence_score": result.get("confidence_score", 0.0),
                    "wf1_context_used": result.get("wf1_context_used", False),
                    "candidates_count": len(result.get("positioning_candidates", [])),
                    "maps_count": len(result.get("perceptual_maps", [])),
                    "execution_time_ms": result.get("execution_time_ms", 0),
                },
            )

            # Emit trace: completed
            await self._trace.send_trace(
                job_id=job_id,
                status="completed",
                message=(
                    f"Brand positioning complete: "
                    f"confidence={result.get('confidence_score', 0):.2f}, "
                    f"candidates={len(result.get('positioning_candidates', []))}"
                ),
                metadata={
                    "confidence_score": result.get("confidence_score", 0.0),
                    "wf1_context_used": result.get("wf1_context_used", False),
                },
            )

            # Emit session completed event
            await self._events.emit(
                EventType.SESSION_COMPLETED,
                tenant_id=tenant_id,
                session_id=job_id,
            )

            return result

        except Exception as exc:
            logger.error("Brand positioning analysis failed: %s", exc)
            await self._trace.send_trace(
                job_id=job_id,
                status="error",
                message=str(exc),
            )
            return {
                "query": prompt,
                "recommended_positioning": {},
                "alternative_positions": [],
                "positioning_candidates": [],
                "canvas": {},
                "perceptual_maps": [],
                "differentiation": {},
                "strategy": {},
                "confidence_score": 0.0,
                "wf1_context_used": False,
                "execution_time_ms": 0,
                "findings": [f"Analysis failed: {str(exc)[:200]}"],
                "recommendations": [],
                "sources": [],
            }

    async def close(self) -> None:
        """Cleanup resources."""
        await self._redis.close()
        await self._trace.stop()
        await self._audit.stop()
