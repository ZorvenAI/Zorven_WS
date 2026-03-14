"""TCIA executor — thin wrapper around TrendAnalyzer with caching and tracing."""

import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)


class TCIAExecutor:
    """Thin orchestration wrapper: cache check -> analyze -> cache result."""

    def __init__(
        self,
        analyzer: Any,
        redis_manager: Any,
        trace_producer: Any,
        audit_producer: Any,
    ) -> None:
        self._analyzer = analyzer
        self._redis = redis_manager
        self._trace = trace_producer
        self._audit = audit_producer

    async def execute(
        self,
        prompt: str,
        input_context: dict[str, Any],
        tenant_context: dict[str, Any],
        config: dict[str, Any],
        previous_outputs: dict[str, Any],
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        """Execute a trend analysis with caching, tracing, and auditing."""
        job_id = input_context.get("job_id", str(uuid.uuid4()))
        user_role = tenant_context.get("user_role", "EDITOR")

        # 1. Trace: started
        await self._trace.send_step(
            job_id, f"Trend analysis: {prompt[:80]}", "PROCESSING"
        )

        # 2. Cache check
        cached = await self._redis.get_cached_result(prompt, config, tenant_id)
        if cached:
            await self._trace.send_step(
                job_id, "Cache hit, returning cached result", "COMPLETED"
            )
            return cached

        # 3. Execute analysis
        try:
            result = await self._analyzer.analyze(
                prompt,
                tenant_id=tenant_id,
                user_role=user_role,
                config=config,
                previous_outputs=previous_outputs,
            )
        except Exception as exc:
            logger.error("Analysis failed: %s", exc)
            await self._trace.send_step(
                job_id, f"Analysis failed: {exc}", "FAILED"
            )
            return {
                "error": str(exc),
                "findings": [f"Analysis failed: {exc}"],
                "sources": [],
                "scored_trends": [],
                "trend_report": {
                    "executive_summary": f"Analysis failed: {exc}",
                    "trend_scorecard": [],
                    "confidence_score": 0.0,
                },
            }

        # 4. Cache result
        await self._redis.cache_result(prompt, config, result, tenant_id)

        # 5. Audit event
        await self._audit.send_event(
            {
                "event_type": "analysis.completed",
                "job_id": job_id,
                "tenant_id": tenant_id,
                "prompt_preview": prompt[:100],
                "trend_count": len(result.get("scored_trends", [])),
                "alert_count": len(result.get("opportunity_alerts", [])),
                "confidence": result.get("confidence_score", 0.0),
            }
        )

        # 6. Trace: completed
        scored = result.get("scored_trends", [])
        await self._trace.send_step(
            job_id,
            f"Generated {len(scored)} scored trends",
            "COMPLETED",
        )

        return result
