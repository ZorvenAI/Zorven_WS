"""
Content executor — core orchestration service.

Wires together SEO optimizer, AEO formatter, GEO synthesizer,
blog author, core API client, GCS client, and Redis caching
into a single execute() flow.
"""

import hashlib
import logging
import uuid
from typing import Any, Optional

from fastapi import HTTPException

from app.api.schemas import (
    AEOSchema,
    Citation,
    ExecuteRequest,
    ExecuteResponse,
    FAQItem,
    SEOMeta,
)
from app.cache.redis_manager import RedisManager
from app.core.config import settings
from app.logic.aeo_formatter import AEOFormatter
from app.logic.blog_author import BlogAuthor
from app.logic.geo_synthesizer import GEOSynthesizer
from app.logic.seo_optimizer import SEOOptimizer
from app.messaging.kafka_producer import ContentPublishedProducer, TraceProducer
from app.services.core_api_client import CoreApiClient
from app.services.gcs_client import GCSClient

logger = logging.getLogger(__name__)

# Ordered preference for research input sources.
# The first one with meaningful content wins.
# "discovery" is the node ID used in auto-detect mode;
# "web_research" / "default_agent" are legacy manifest-mode keys.
_RESEARCH_KEYS = ["discovery", "web_research", "default_agent"]


def _extract_research_data(previous_outputs: dict) -> dict:
    """Extract research data from any upstream node's output.

    Checks known research node keys in priority order. Normalizes
    different output schemas to a common format:
        {raw_context: str, findings: list, sources: list}
    """
    for key in _RESEARCH_KEYS:
        data = previous_outputs.get(key, {})
        if not data or not isinstance(data, dict):
            continue

        # discovery / web_research use the expected schema
        if data.get("raw_context"):
            return data

        # default_agent (RAG): prefer raw_context (actual document chunks)
        # over summary (Gemini-synthesized answer) for richer blog content
        if key == "default_agent":
            raw = data.get("raw_context") or data.get("summary", "")
            if raw:
                return {
                    "raw_context": raw,
                    "findings": data.get("findings", []),
                    "sources": data.get("sources", []),
                }

        # Generic fallback: any node with findings/summary can provide context
        summary = data.get("summary", "")
        findings = data.get("findings", [])
        if summary or findings:
            raw = summary
            if not raw and findings:
                raw = "\n".join(str(f) for f in findings[:10])
            return {
                "raw_context": raw,
                "findings": findings,
                "sources": data.get("sources", []),
            }

    # No upstream research found — return empty (blog will use prompt only)
    return {}


class ContentExecutor:
    """Orchestrates the full content authoring flow."""

    def __init__(
        self,
        seo_optimizer: SEOOptimizer,
        aeo_formatter: AEOFormatter,
        geo_synthesizer: GEOSynthesizer,
        blog_author: BlogAuthor,
        core_api_client: CoreApiClient,
        gcs_client: GCSClient,
        redis_manager: Optional[RedisManager] = None,
        trace_producer: Optional[TraceProducer] = None,
        published_producer: Optional[ContentPublishedProducer] = None,
    ) -> None:
        self.seo_optimizer = seo_optimizer
        self.aeo_formatter = aeo_formatter
        self.geo_synthesizer = geo_synthesizer
        self.blog_author = blog_author
        self.core_api_client = core_api_client
        self.gcs_client = gcs_client
        self.redis_manager = redis_manager
        self.trace_producer = trace_producer
        self.published_producer = published_producer

    async def execute(
        self,
        request: ExecuteRequest,
        tenant_id: str,
    ) -> ExecuteResponse:
        """
        Execute the full blog authoring pipeline.

        1. Rate limit check
        2. Cache check
        3. Fetch brand persona
        4. Extract research data from previous outputs
        5. SEO optimization
        6. GEO citation synthesis
        7. Blog authoring
        8. AEO formatting
        9. GCS upload
        10. Cache result
        11. Emit published event
        12. Return response
        """
        topic = request.input_prompt
        job_id = request.input_context.get("job_id", "")
        company_id = request.input_context.get("company_id")

        logger.info("Content authoring for tenant %s: %s", tenant_id, topic[:100])

        # 1. Rate limit check
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

        # 2. Extract research data early (needed for cache key)
        research_data = _extract_research_data(request.previous_outputs)
        raw_context = research_data.get("raw_context", "")
        research_findings = research_data.get("findings", [])

        # 3. Cache check (includes research context hash)
        cache_key = self._build_cache_key(tenant_id, topic, request.config, raw_context)
        if self.redis_manager:
            cached = await self.redis_manager.get_cached_result(cache_key)
            if cached:
                logger.info("Cache hit for tenant %s, returning cached blog", tenant_id)
                return ExecuteResponse(**cached)

        await self._trace(job_id, "Fetching brand persona...")

        # 4. Fetch brand persona
        brand_persona = await self.core_api_client.fetch_brand_persona(
            tenant_id, str(company_id) if company_id else None
        )

        await self._trace(job_id, "Optimizing for SEO...")

        # 5. SEO optimization
        seo_data = await self.seo_optimizer.optimize(topic, raw_context, brand_persona)

        await self._trace(job_id, "Synthesizing citations...")

        # 6. GEO citation synthesis
        citations = self.geo_synthesizer.synthesize(research_data, research_findings)

        await self._trace(job_id, "Writing blog post...")

        # 7. Blog authoring (with optional skill context from orchestrator)
        skill_context = request.config.get("skill_context", "")
        blog_content = await self.blog_author.author(
            topic,
            raw_context,
            brand_persona,
            seo_data,
            citations,
            skill_context=skill_context,
        )

        await self._trace(job_id, "Generating FAQ schema...")

        # 8. AEO formatting
        aeo_data = await self.aeo_formatter.format(
            topic, blog_content, seo_data.get("keywords", [])
        )

        await self._trace(job_id, "Uploading to storage...")

        # 9. GCS upload
        slug = seo_data.get("slug", "untitled")
        upload_metadata = {
            "topic": topic,
            "tenant_id": tenant_id,
            "seo_meta": {
                "title": seo_data.get("meta_title", ""),
                "description": seo_data.get("meta_description", ""),
                "keywords": seo_data.get("keywords", []),
                "slug": slug,
            },
            "word_count": len(blog_content.split()),
        }
        gcs_uri = await self.gcs_client.upload_blog(
            tenant_id, slug, blog_content, upload_metadata
        )

        # Build response
        seo_meta = SEOMeta(
            title=seo_data.get("meta_title", ""),
            description=seo_data.get("meta_description", ""),
            keywords=seo_data.get("keywords", []),
            slug=slug,
        )

        aeo_schema = AEOSchema(
            faq_items=[
                FAQItem(
                    question=item.get("question", ""),
                    answer=item.get("answer", ""),
                )
                for item in aeo_data.get("faq_items", [])
            ],
            structured_data=aeo_data.get("structured_data", {}),
        )

        word_count = len(blog_content.split())

        findings = [
            f"Blog authored: {seo_data.get('meta_title', topic)}",
            f"Word count: {word_count}",
            f"SEO keywords: {', '.join(seo_data.get('keywords', [])[:5])}",
            f"FAQ items generated: {len(aeo_data.get('faq_items', []))}",
            f"Citations included: {len(citations)}",
        ]

        recommendations = [
            "Review the generated blog for accuracy and brand alignment.",
            "Verify all cited sources are accessible and current.",
            "Consider adding internal links to related content.",
        ]

        response = ExecuteResponse(
            findings=findings,
            recommendations=recommendations,
            blog_content=blog_content,
            seo_meta=seo_meta,
            aeo_schema=aeo_schema,
            citations=citations,
            gcs_uri=gcs_uri,
            word_count=word_count,
        )

        # 10. Cache result
        if self.redis_manager:
            await self.redis_manager.set_cached_result(cache_key, response.model_dump())

        # 11. Emit published event
        if self.published_producer:
            blog_id = str(uuid.uuid4())
            await self.published_producer.send_published(
                blog_id=blog_id,
                tenant_id=tenant_id,
                gcs_uri=gcs_uri,
                seo_meta=seo_meta.model_dump(),
                title=seo_data.get("meta_title", topic),
            )

        await self._trace(job_id, "Blog authoring complete", status="COMPLETED")

        return response

    async def close(self) -> None:
        """Clean up resources."""
        if self.redis_manager:
            await self.redis_manager.close()
        await self.core_api_client.close()
        await self.gcs_client.close()
        if self.trace_producer:
            await self.trace_producer.stop()
        if self.published_producer:
            await self.published_producer.stop()

    async def _trace(
        self, job_id: str, message: str, status: str = "PROCESSING"
    ) -> None:
        """Emit a trace event if producer is available."""
        if self.trace_producer and job_id:
            await self.trace_producer.send_step(job_id, message, status=status)

    @staticmethod
    def _build_cache_key(
        tenant_id: str,
        topic: str,
        config: dict[str, Any],
        research_context: str = "",
    ) -> str:
        """Build a cache key from tenant, topic, config, and research context.

        Includes a hash of the research context so different research inputs
        (e.g., RAG vs web search, or updated documents) produce different blogs.
        """
        ctx_hash = hashlib.md5(research_context.encode()).hexdigest()[:8]
        raw = f"{tenant_id}:{topic}:{sorted(config.items())}:{ctx_hash}"
        return hashlib.md5(raw.encode()).hexdigest()
