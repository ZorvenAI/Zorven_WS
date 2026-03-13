"""APAExecutor — Thin orchestration wrapper for the Audience Persona Agent.

Flow: cache check → delegate to PersonaAnalyzer → cache result → audit event.
"""

import logging
import uuid
from typing import Any

from app.cache.redis_manager import RedisManager
from app.events.catalog import EventEmitter
from app.logic.persona_analyzer import PersonaAnalyzer
from app.messaging.kafka_producer import AuditProducer, TraceProducer
from app.messaging.schemas import AuditEvent, TraceEvent

logger = logging.getLogger(__name__)


class APAExecutor:
    """Top-level executor for persona analysis requests."""

    def __init__(
        self,
        analyzer: PersonaAnalyzer,
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
        """Execute a persona analysis request."""
        job_id = input_context.get("job_id", str(uuid.uuid4()))
        user_role = tenant_context.get("user_role", "EDITOR")
        skill_context = config.get("skill_context", "")

        # Emit trace: started
        await self._trace.send_trace(
            TraceEvent(
                job_id=job_id,
                status="started",
                message=f"Audience persona analysis: {prompt[:80]}",
            ).model_dump()
        )

        # Check cache
        cached = await self._redis.get_cached_result(prompt, config, tenant_id)
        if cached:
            logger.info("Cache hit for job %s", job_id)
            await self._trace.send_trace(
                TraceEvent(
                    job_id=job_id,
                    status="completed",
                    message="Result served from cache",
                ).model_dump()
            )
            return cached

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
        await self._redis.cache_result(prompt, config, result, tenant_id)

        # Emit audit event
        await self._audit.send_event(
            AuditEvent(
                job_id=job_id,
                tenant_id=tenant_id,
                query=prompt[:500],
                personas_count=len(result.get("personas", [])),
                journey_maps_count=len(result.get("journey_maps", [])),
                sources_count=len(result.get("sources", [])),
                findings_count=len(result.get("findings", [])),
                confidence_score=result.get("confidence_score", 0.0),
                data_sources_used=self._identify_data_sources(result),
            ).model_dump()
        )

        # Emit trace: completed
        await self._trace.send_trace(
            TraceEvent(
                job_id=job_id,
                status="completed",
                message=(
                    f"Generated {len(result.get('personas', []))} persona(s), "
                    f"{len(result.get('journey_maps', []))} journey map(s)"
                ),
                metadata={
                    "personas_count": len(result.get("personas", [])),
                    "confidence_score": result.get("confidence_score", 0.0),
                },
            ).model_dump()
        )

        return result

    async def close(self) -> None:
        """Cleanup resources."""
        await self._redis.close()
        await self._trace.stop()
        await self._audit.stop()

    @staticmethod
    def _identify_data_sources(result: dict[str, Any]) -> list[str]:
        """Identify which data sources contributed to the result."""
        sources = []
        personas = result.get("personas", [])
        for p in personas:
            if isinstance(p, dict):
                ds = p.get("data_source", "")
                if ds and ds not in sources:
                    sources.append(ds)
        if result.get("sources"):
            sources.append("web_research")
        return sources
