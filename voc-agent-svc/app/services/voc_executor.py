"""VoCAExecutor — Thin orchestration wrapper for the Voice of Customer Agent.

Flow: cache check → delegate to VoCAAnalyzer → cache result → audit event.
"""

import logging
import uuid
from typing import Any

from app.cache.redis_manager import RedisManager
from app.events.catalog import EventEmitter, EventType
from app.logic.voc_analyzer import VoCAAnalyzer
from app.messaging.kafka_producer import AuditProducer, TraceProducer

logger = logging.getLogger(__name__)


class VoCAExecutor:
    """Top-level executor for VoC analysis requests."""

    def __init__(
        self,
        analyzer: VoCAAnalyzer,
        redis_manager: RedisManager,
        trace_producer: TraceProducer,
        audit_producer: AuditProducer,
        event_emitter: EventEmitter,
    ) -> None:
        self._analyzer = analyzer
        self._redis = redis_manager
        self._trace = trace_producer
        self._audit = audit_producer
        self._events = event_emitter

    async def execute(
        self,
        prompt: str,
        input_context: dict[str, Any],
        tenant_context: dict[str, Any],
        config: dict[str, Any],
        previous_outputs: dict[str, Any],
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        """Execute a VoC analysis request."""
        job_id = input_context.get("job_id", str(uuid.uuid4()))
        user_role = tenant_context.get("user_role", "EDITOR")
        skill_context = config.get("skill_context", "")

        # Emit trace: started
        await self._trace.send_trace(
            job_id=job_id,
            status="started",
            message=f"VoC analysis: {prompt[:80]}",
        )

        # Emit session started event
        await self._events.emit(
            EventType.SESSION_STARTED,
            tenant_id=tenant_id,
            session_id=job_id,
            data={"prompt_preview": prompt[:200]},
        )

        # Check cache
        cached = await self._redis.get_cached_result(
            prompt, config, tenant_id
        )
        if cached:
            cached_confidence = cached.get("confidence_score", 0)
            if cached_confidence > 0.5:
                logger.info(
                    "Cache hit for job %s (confidence=%.0f%%)",
                    job_id,
                    cached_confidence * 100,
                )
                await self._trace.send_trace(
                    job_id=job_id,
                    status="completed",
                    message="Result served from cache",
                )
                return cached
            else:
                logger.warning(
                    "Ignoring stale low-confidence cache (%.0f%%) for job %s",
                    cached_confidence * 100,
                    job_id,
                )

        try:
            # Execute analysis
            result = await self._analyzer.analyze(
                prompt,
                tenant_id=tenant_id,
                user_role=user_role,
                config=config,
                previous_outputs=previous_outputs,
                skill_context=skill_context,
            )

            # Cache result
            await self._redis.cache_result(
                prompt, config, result, tenant_id
            )

            # Emit audit event
            await self._audit.send_event(
                event_type="VOC_ANALYSIS_COMPLETED",
                event_name="voc_analysis_completed",
                tenant_id=tenant_id,
                session_id=job_id,
                data={
                    "query": prompt[:500],
                    "operating_mode": result.get("operating_mode", ""),
                    "voc_health_score": result.get("voc_health_score", 0.0),
                    "themes_count": len(
                        result.get("themes", {}).get("themes", [])
                    ),
                    "sources_count": len(result.get("sources", [])),
                    "findings_count": len(result.get("findings", [])),
                    "confidence_score": result.get("confidence_score", 0.0),
                    "data_coverage_score": result.get(
                        "data_coverage_score", 0.0
                    ),
                },
            )

            # Emit trace: completed
            await self._trace.send_trace(
                job_id=job_id,
                status="completed",
                message=(
                    f"VoC analysis complete: "
                    f"health={result.get('voc_health_score', 0):.0f}, "
                    f"mode={result.get('operating_mode', 'unknown')}"
                ),
                metadata={
                    "voc_health_score": result.get("voc_health_score", 0.0),
                    "confidence_score": result.get("confidence_score", 0.0),
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
            logger.error("VoC analysis failed: %s", exc)
            await self._trace.send_trace(
                job_id=job_id,
                status="error",
                message=str(exc),
            )
            return {
                "query": prompt,
                "operating_mode": "",
                "data_coverage_score": 0.0,
                "sentiment": {},
                "themes": {},
                "nps_analysis": {},
                "pain_point_priority_matrix": {},
                "strategy_bridge": {},
                "voc_health_score": 0.0,
                "findings": [f"Analysis failed: {str(exc)[:200]}"],
                "recommendations": [],
                "sources": [],
                "confidence_score": 0.0,
                "raw_context": "",
            }

    async def close(self) -> None:
        """Cleanup resources."""
        await self._redis.close()
        await self._trace.stop()
        await self._audit.stop()
