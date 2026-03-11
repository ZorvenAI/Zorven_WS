"""
MRA Executor — orchestrates the full market research flow.

Flow: guardrail → rate limit → cache check → research → cache store → audit
"""

import hashlib
import json
import logging
from typing import Optional

from fastapi import HTTPException

from app.api.schemas import ExecuteRequest, MarketResearchResponse
from app.cache.redis_manager import RedisManager
from app.core.config import settings
from app.logic.guardrails import InputGuardrail, OutputGuardrail
from app.logic.market_researcher import MarketResearcher
from app.messaging.kafka_producer import AuditProducer, TraceProducer

logger = logging.getLogger(__name__)


class MRAExecutor:
    """Orchestrates guardrails, caching, research, and audit."""

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
        Execute market research with full guardrail and caching pipeline.

        1. Input guardrail (validate/sanitize)
        2. Rate limit check
        3. Cache check
        4. PAOR research loop
        5. Output guardrail
        6. Cache result
        7. Audit event
        """
        job_id = request.input_context.get("job_id", "")

        # 1. Input guardrail
        sanitized_prompt = self.input_guard.validate(request.input_prompt)

        # 2. Rate limit check
        if self.redis_manager:
            allowed = await self.redis_manager.check_rate_limit(
                tenant_id, limit=settings.RATE_LIMIT_PER_MINUTE
            )
            if not allowed:
                logger.warning("Rate limit exceeded for tenant %s", tenant_id)
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded for tenant {tenant_id}. "
                    f"Max {settings.RATE_LIMIT_PER_MINUTE} requests per minute.",
                )

        # 3. Cache check
        cache_key = self._build_cache_key(sanitized_prompt, request.config)
        if self.redis_manager:
            cached = await self.redis_manager.get_cached_result(cache_key)
            if cached:
                logger.info("Cache HIT for tenant %s", tenant_id)
                await self._emit_trace(job_id, "Returning cached research results")
                return MarketResearchResponse(**cached)

        # 4. Execute research (PAOR loop)
        logger.info(
            "Starting market research for tenant %s: %s",
            tenant_id,
            sanitized_prompt[:100],
        )
        await self._emit_trace(job_id, f"Researching: {sanitized_prompt[:80]}")

        result = await self.researcher.research(
            prompt=sanitized_prompt,
            config=request.config,
            previous_outputs=request.previous_outputs,
        )

        # 5. Output guardrail
        result = self.output_guard.validate(result)

        # 6. Cache result
        if self.redis_manager:
            await self.redis_manager.set_cached_result(
                cache_key,
                result.model_dump(),
                ttl=settings.RESEARCH_CACHE_TTL,
            )

        # 7. Audit event
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

        # Determine which data sources were used
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
