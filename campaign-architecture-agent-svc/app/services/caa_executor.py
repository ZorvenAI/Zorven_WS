"""CAA Executor — orchestrates campaign architecture analysis flow."""

import logging
import time
import uuid
from typing import Any

from app.cache.redis_manager import RedisManager
from app.messaging.event_emitter import EventEmitter, EventType
from app.messaging.kafka_producer import AuditProducer, TraceProducer
from app.services.caa_analyzer import CAAAnalyzer
from app.services.context_loader import CAAContextLoader
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


class CAAExecutor:
    """Thin wrapper: cache -> context load -> analyze -> GCS -> cache -> audit."""

    def __init__(
        self,
        analyzer: CAAAnalyzer,
        redis_manager: RedisManager,
        trace_producer: TraceProducer,
        audit_producer: AuditProducer,
        event_emitter: EventEmitter,
        context_loader: CAAContextLoader,
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
        """Execute campaign architecture analysis."""
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
                "node_id": "campaign_architecture",
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
            contexts = await self._context.load_all(tenant_id)
            wf1_context = contexts["wf1"]
            bpa_context = contexts["bpa"]
            wf2_chain_context = contexts["wf2_chain"]
            company_context = contexts["company"]
            baa_context = contexts["baa"]
            odoo_context = contexts["odoo"]
            rag_context = contexts["rag"]

            # Emit context events
            for label, ctx, loaded_evt, missing_evt in [
                (
                    "WF1",
                    wf1_context,
                    EventType.WF1_CONTEXT_LOADED,
                    EventType.WF1_CONTEXT_MISSING,
                ),
                (
                    "WF2",
                    wf2_chain_context,
                    EventType.WF2_CONTEXT_LOADED,
                    EventType.WF2_CONTEXT_MISSING,
                ),
                (
                    "Company",
                    company_context,
                    EventType.COMPANY_CONTEXT_LOADED,
                    EventType.COMPANY_CONTEXT_MISSING,
                ),
            ]:
                if ctx:
                    await self._events.emit(loaded_evt, tenant_id, job_id)
                else:
                    await self._events.emit(missing_evt, tenant_id, job_id)

            # Optional context events
            if odoo_context:
                await self._events.emit(EventType.ODOO_DATA_LOADED, tenant_id, job_id)
            else:
                await self._events.emit(EventType.ODOO_DATA_SKIPPED, tenant_id, job_id)

            if rag_context:
                await self._events.emit(
                    EventType.RAG_LEARNINGS_LOADED, tenant_id, job_id
                )
            else:
                await self._events.emit(
                    EventType.RAG_LEARNINGS_SKIPPED, tenant_id, job_id
                )

            # Also check previous_outputs for WF2 agents
            if not baa_context:
                baa_context = previous_outputs.get("brand_architecture")

            # Prerequisite check: WF1 (min APA+CIA) + BPA + Company required
            has_wf1 = bool(wf1_context) or any(k in previous_outputs for k in _WF1_KEYS)
            has_bpa = bool(bpa_context) or bool(
                previous_outputs.get("brand_positioning")
            )
            has_company = bool(company_context)

            if not has_wf1 or not has_bpa or not has_company:
                missing = []
                if not has_wf1:
                    missing.append("WF1 Brand Discovery (min APA+CIA)")
                if not has_bpa:
                    missing.append("BPA Brand Positioning")
                if not has_company:
                    missing.append("Company model")
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
                        f"context required. Run the missing "
                        f"pipeline(s) first."
                    ],
                )

            # Tavily research (benchmarks + competitor ads)
            tavily_benchmarks = {}
            tavily_competitors = {}
            if hasattr(self._analyzer, "_tavily") and self._analyzer._tavily:
                industry = _extract_industry(company_context, wf1_context)
                competitors = _extract_competitors(wf1_context)
                if industry:
                    tavily_benchmarks = await self._analyzer._tavily.search_benchmarks(
                        industry
                    )
                if competitors:
                    tavily_competitors = (
                        await self._analyzer._tavily.search_competitor_ads(
                            competitors, industry or ""
                        )
                    )

            if tavily_benchmarks:
                await self._events.emit(
                    EventType.TAVILY_BENCHMARKS_LOADED,
                    tenant_id,
                    job_id,
                )
            else:
                await self._events.emit(
                    EventType.TAVILY_BENCHMARKS_SKIPPED,
                    tenant_id,
                    job_id,
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
                wf2_chain_context=wf2_chain_context,
                company_context=company_context,
                baa_context=baa_context,
                odoo_context=odoo_context,
                rag_context=rag_context,
                tavily_benchmarks=tavily_benchmarks,
                tavily_competitors=tavily_competitors,
                job_id=job_id,
            )

            # GCS persist
            gcs_uri = await self._gcs.upload_blueprint(tenant_id, job_id, result)
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

            # Save to blueprint registry
            await self._redis.save_blueprint(tenant_id, result)

        except Exception as exc:
            logger.error("CAA analysis failed: %s", exc, exc_info=True)
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
                    "node_id": "campaign_architecture",
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


def _extract_industry(
    company_context: dict[str, Any] | None,
    wf1_context: dict[str, Any] | None,
) -> str:
    """Extract industry from company or WF1 context."""
    if company_context:
        industry = company_context.get("industry", "")
        if industry:
            return industry
    if wf1_context:
        return wf1_context.get("industry", "")
    return ""


def _extract_competitors(
    wf1_context: dict[str, Any] | None,
) -> list[str]:
    """Extract competitor names from WF1 context (CIA data)."""
    if not wf1_context:
        return []
    cia = wf1_context.get("competitor_intelligence", {})
    competitors = cia.get("competitors", [])
    if isinstance(competitors, list):
        return [
            c.get("name", "") if isinstance(c, dict) else str(c)
            for c in competitors[:5]
        ]
    return []


def _empty_result(
    prompt: str,
    start_time: float,
    findings: list[str] | None = None,
) -> dict[str, Any]:
    """Build empty error/prerequisite-failure result."""
    return {
        "query": prompt,
        "blueprint": {},
        "funnel_map": {},
        "targeting_specs": [],
        "placement_budget": {},
        "test_plan": {},
        "kpi_targets": {},
        "performance_projections": {},
        "risk_assessment": {},
        "creative_briefs": [],
        "special_ad_category": "",
        "meta_api_compatible": False,
        "confidence_score": 0.0,
        "findings": findings or [],
        "recommendations": [],
        "sources": [],
        "wf1_context_used": False,
        "wf2_context_used": False,
        "bpa_context_used": False,
        "company_context_used": False,
        "tavily_benchmarks_used": False,
        "odoo_data_used": False,
        "rag_learnings_used": False,
        "gcs_uri": "",
        "execution_time_ms": int((time.time() - start_time) * 1000),
    }
