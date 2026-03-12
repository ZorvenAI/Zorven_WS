"""
MRA Executor — thin wrapper that delegates to MarketResearcher.

The researcher handles guardrails, skills, RBAC, and circuit breakers.
The executor handles caching and audit/trace event emission.
"""

import hashlib
import json
import logging
from typing import Optional

from app.api.schemas import ExecuteRequest, MarketResearchResponse
from app.cache.redis_manager import RedisManager
from app.core.config import settings
from app.logic.guardrails import InputGuardrail, OutputGuardrail
from app.logic.market_researcher import MarketResearcher
from app.messaging.kafka_producer import AuditProducer, TraceProducer

logger = logging.getLogger(__name__)


class MRAExecutor:
    """Orchestrates caching, research delegation, and audit."""

    def __init__(
        self,
        researcher: MarketResearcher,
        redis_manager: Optional[RedisManager] = None,
        trace_producer: Optional[TraceProducer] = None,
        audit_producer: Optional[AuditProducer] = None,
        input_guard: Optional[InputGuardrail] = None,
        output_guard: Optional[OutputGuardrail] = None,
    ) -> None:
        self.researcher = researcher
        self.redis_manager = redis_manager
        self.trace_producer = trace_producer
        self.audit_producer = audit_producer
        self.input_guard = input_guard or InputGuardrail()
        self.output_guard = output_guard or OutputGuardrail()

    async def execute(
        self,
        request: ExecuteRequest,
        tenant_id: str,
    ) -> MarketResearchResponse:
        """
        Execute market research with caching and audit.

        1. Legacy input guardrail (basic validation)
        2. Cache check
        3. Delegate to MarketResearcher (handles skills, RBAC, guardrails)
        4. Legacy output guardrail
        5. Cache result
        6. Audit event
        """
        job_id = request.input_context.get("job_id", "")

        # 1. Legacy input guardrail (basic sync validation)
        sanitized_prompt = self.input_guard.validate(request.input_prompt)

        # 2. Cache check
        cache_key = self._build_cache_key(sanitized_prompt, request.config)
        if self.redis_manager:
            cached = await self.redis_manager.get_cached_result(cache_key)
            if cached:
                logger.info("Cache HIT for tenant %s", tenant_id)
                await self._emit_trace(job_id, "Returning cached research results")
                return MarketResearchResponse(**cached)

        # 3. Delegate to researcher
        logger.info(
            "Starting market research for tenant %s: %s",
            tenant_id,
            sanitized_prompt[:100],
        )
        await self._emit_trace(job_id, f"Researching: {sanitized_prompt[:80]}")

        # Extract user_role from tenant_context
        tenant_ctx = request.tenant_context
        if isinstance(tenant_ctx, dict):
            user_role = tenant_ctx.get("user_role", "EDITOR")
        else:
            user_role = getattr(tenant_ctx, "user_role", "EDITOR")

        result = await self.researcher.research(
            prompt=sanitized_prompt,
            config=request.config,
            tenant_id=tenant_id,
            user_role=user_role,
            previous_outputs=request.previous_outputs,
        )

        # 4. Legacy output guardrail
        result = self.output_guard.validate(result)

        # 5. Cache result
        if self.redis_manager:
            await self.redis_manager.set_cached_result(
                cache_key,
                result.model_dump(),
                ttl=settings.RESEARCH_CACHE_TTL,
            )

        # 6. Audit event
        await self._emit_audit(
            job_id=job_id,
            tenant_id=tenant_id,
            query=sanitized_prompt,
            result=result,
        )

        await self._emit_trace(
            job_id,
            f"Research complete. {len(result.sources)} sources, "
            f"{len(result.findings)} findings. "
            f"Confidence: {result.confidence_score:.0%}",
            status="COMPLETED",
        )

        return result

    async def close(self) -> None:
        """Clean up resources."""
        if self.redis_manager:
            await self.redis_manager.close()
        if self.trace_producer:
            await self.trace_producer.stop()
        if self.audit_producer:
            await self.audit_producer.stop()
        await self.researcher.close()

    @staticmethod
    def _build_cache_key(prompt: str, config: dict) -> str:
        """Build a deterministic cache key from prompt + config."""
        key_data = json.dumps({"prompt": prompt, "config": config}, sort_keys=True)
        return hashlib.md5(key_data.encode()).hexdigest()

    async def _emit_trace(
        self,
        job_id: str,
        message: str,
        status: str = "PROCESSING",
        metadata: Optional[dict] = None,
    ) -> None:
        """Emit a trace event for ThoughtTrace UI (non-fatal)."""
        if not self.trace_producer or not job_id:
            return
        await self.trace_producer.send_step(
            job_id=job_id,
            message=message,
            status=status,
            metadata=metadata,
        )

    async def _emit_audit(
        self,
        job_id: str,
        tenant_id: str,
        query: str,
        result: MarketResearchResponse,
    ) -> None:
        """Emit an audit event (non-fatal)."""
        if not self.audit_producer or not job_id:
            return

        data_sources = []
        source_types = {s.type for s in result.sources}
        if "web" in source_types:
            data_sources.append("tavily")
        if "economic_data" in source_types:
            data_sources.append("world_bank")
        if "news" in source_types:
            data_sources.append("newsapi")

        await self.audit_producer.send_audit(
            job_id=job_id,
            tenant_id=tenant_id,
            query=query,
            sources_count=len(result.sources),
            findings_count=len(result.findings),
            confidence_score=result.confidence_score,
            data_sources_used=data_sources,
        )
