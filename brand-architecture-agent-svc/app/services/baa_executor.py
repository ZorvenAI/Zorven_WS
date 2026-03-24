"""BAAExecutor — Thin orchestration wrapper for the Brand Architecture Agent.

Flow: cache check -> load WF1 + BPA + Company context -> prerequisite check ->
      delegate to BAAAnalyzer -> cache result -> update registry -> audit event.
"""

import logging
import uuid
from typing import Any

from app.cache.redis_manager import RedisManager
from app.logic.strategy_persister import StrategyPersister
from app.messaging.event_emitter import EventEmitter, EventType
from app.messaging.kafka_producer import AuditProducer, TraceProducer
from app.services.baa_analyzer import BAAAnalyzer
from app.services.context_loader import BAAContextLoader

logger = logging.getLogger(__name__)


class BAAExecutor:
    """Top-level executor for brand architecture requests."""

    def __init__(
        self,
        analyzer: BAAAnalyzer,
        redis_manager: RedisManager,
        trace_producer: TraceProducer,
        audit_producer: AuditProducer,
        event_emitter: EventEmitter,
        context_loader: BAAContextLoader,
        strategy_persister: StrategyPersister | None = None,
    ) -> None:
        self._analyzer = analyzer
        self._redis = redis_manager
        self._trace = trace_producer
        self._audit = audit_producer
        self._events = event_emitter
        self._context_loader = context_loader
        self._persister = strategy_persister or StrategyPersister()

    async def execute(
        self,
        prompt: str,
        input_context: dict[str, Any],
        tenant_context: dict[str, Any],
        config: dict[str, Any],
        previous_outputs: dict[str, Any],
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        """Execute a brand architecture request."""
        job_id = input_context.get("job_id", str(uuid.uuid4()))
        user_role = tenant_context.get("user_role", "EDITOR")
        skill_context = config.get("skill_context", "")

        # Emit trace: started
        await self._trace.send_trace(
            job_id=job_id,
            status="started",
            message=f"Brand architecture: {prompt[:80]}",
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
            # Load all contexts in parallel
            contexts = await self._context_loader.load_all(tenant_id)
            wf1_context = contexts.get("wf1")
            bpa_context = contexts.get("bpa")
            company_context = contexts.get("company")

            # Emit context load events
            if wf1_context:
                await self._events.emit(
                    EventType.WF1_CONTEXT_LOADED,
                    tenant_id=tenant_id,
                    session_id=job_id,
                    data={"snapshot_id": wf1_context.get("snapshot_id")},
                )
            else:
                await self._events.emit(
                    EventType.WF1_CONTEXT_MISSING,
                    tenant_id=tenant_id,
                    session_id=job_id,
                )

            if bpa_context:
                await self._events.emit(
                    EventType.BPA_CONTEXT_LOADED,
                    tenant_id=tenant_id,
                    session_id=job_id,
                    data={
                        "bpa_job_id": bpa_context.get("bpa_job_id"),
                        "confidence": bpa_context.get("confidence_score"),
                    },
                )
            else:
                await self._events.emit(
                    EventType.BPA_CONTEXT_MISSING,
                    tenant_id=tenant_id,
                    session_id=job_id,
                )

            if company_context:
                await self._events.emit(
                    EventType.COMPANY_CONTEXT_LOADED,
                    tenant_id=tenant_id,
                    session_id=job_id,
                )

            # Prerequisite check: BAA requires BOTH WF1 and BPA
            wf1_keys = {
                "market_research",
                "competitor_intelligence",
                "audience_persona",
                "trend_cultural",
                "voice_of_customer",
            }
            has_wf1_in_prev = any(k in previous_outputs for k in wf1_keys)
            has_wf1 = bool(wf1_context or has_wf1_in_prev)
            has_bpa = bool(bpa_context or previous_outputs.get("brand_positioning"))

            if not has_wf1 or not has_bpa:
                missing = []
                if not has_wf1:
                    missing.append("WF1 Brand Discovery")
                if not has_bpa:
                    missing.append("BPA Brand Positioning")

                await self._events.emit(
                    EventType.PREREQUISITES_MISSING,
                    tenant_id=tenant_id,
                    session_id=job_id,
                    data={"missing": missing},
                )
                await self._trace.send_trace(
                    job_id=job_id,
                    status="completed",
                    message=f"Prerequisites missing: {', '.join(missing)}",
                )

                return {
                    "query": prompt,
                    "recommendation": {},
                    "hierarchy": {},
                    "naming_hierarchy": {},
                    "growth_path": {},
                    "strategy": {},
                    "confidence_score": 0.0,
                    "wf1_context_used": False,
                    "bpa_context_used": False,
                    "execution_time_ms": 0,
                    "findings": [
                        f"Cannot proceed: missing prerequisite data "
                        f"({', '.join(missing)}). Please run the Brand "
                        f"Discovery and Brand Positioning pipelines first."
                    ],
                    "recommendations": [
                        r
                        for r in [
                            (
                                "Run WF1 Brand Discovery pipeline first"
                                if not has_wf1
                                else None
                            ),
                            (
                                "Run WF2 Brand Positioning pipeline first"
                                if not has_bpa
                                else None
                            ),
                        ]
                        if r
                    ],
                    "sources": [],
                }

            # Execute analysis
            result = await self._analyzer.analyze(
                prompt,
                tenant_id=tenant_id,
                user_role=user_role,
                config=config,
                previous_outputs=previous_outputs,
                wf1_context=wf1_context or {},
                bpa_context=bpa_context or {},
                company_context=company_context or {},
                skill_context=skill_context,
            )

            # Cache result
            await self._redis.cache_result(prompt, config, result, tenant_id)

            # Update architecture registry
            if result.get("recommendation"):
                await self._redis.save_architecture(
                    tenant_id,
                    {
                        "recommendation": result.get("recommendation", {}),
                        "hierarchy": result.get("hierarchy", {}),
                        "naming_hierarchy": result.get("naming_hierarchy", {}),
                        "confidence_score": result.get("confidence_score", 0.0),
                    },
                )

                # Sync brand context to Django Redis for Brand Context Selector
                company_name = (company_context or {}).get("name", "")
                try:
                    await self._persister.sync_brand_context(
                        tenant_id,
                        result.get("hierarchy", {}),
                        company_name,
                    )
                except Exception as exc:
                    logger.warning(
                        "Brand context sync failed for tenant %s: %s",
                        tenant_id,
                        exc,
                    )

            # Emit audit event
            await self._audit.send_event(
                event_type="BAA_ARCHITECTURE_COMPLETED",
                event_name="baa_architecture_completed",
                tenant_id=tenant_id,
                session_id=job_id,
                data={
                    "query": prompt[:500],
                    "confidence_score": result.get("confidence_score", 0.0),
                    "wf1_context_used": result.get("wf1_context_used", False),
                    "bpa_context_used": result.get("bpa_context_used", False),
                    "recommended_model": (
                        result.get("recommendation", {}).get("recommended_model", "")
                    ),
                    "hierarchy_depth": (
                        result.get("hierarchy", {}).get("total_depth", 0)
                    ),
                    "execution_time_ms": result.get("execution_time_ms", 0),
                },
            )

            # Emit trace: completed
            await self._trace.send_trace(
                job_id=job_id,
                status="completed",
                message=(
                    f"Brand architecture complete: "
                    f"model={result.get('recommendation', {}).get('recommended_model', 'N/A')}, "
                    f"confidence={result.get('confidence_score', 0):.2f}"
                ),
                metadata={
                    "confidence_score": result.get("confidence_score", 0.0),
                    "wf1_context_used": result.get("wf1_context_used", False),
                    "bpa_context_used": result.get("bpa_context_used", False),
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
            logger.error("Brand architecture analysis failed: %s", exc)
            await self._trace.send_trace(
                job_id=job_id,
                status="error",
                message=str(exc),
            )
            return {
                "query": prompt,
                "recommendation": {},
                "hierarchy": {},
                "naming_hierarchy": {},
                "growth_path": {},
                "strategy": {},
                "confidence_score": 0.0,
                "wf1_context_used": False,
                "bpa_context_used": False,
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
