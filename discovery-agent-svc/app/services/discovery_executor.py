"""
Discovery executor — core orchestration service.

Wires together search engine, browser engine, data cleaner,
and Redis caching into a single execute() flow:
  1. Build search query from input_prompt + config.focus
  2. Check rate limit
  3. Search (with cache)
  4. Scrape each URL (with cache)
  5. Clean HTML to Markdown
  6. Aggregate into ExecuteResponse
"""

import logging
from typing import Optional

from fastapi import HTTPException

from app.api.schemas import ExecuteRequest, ExecuteResponse, SourceItem
from app.cache.redis_manager import RedisManager
from app.core.config import settings
from app.messaging.kafka_producer import TraceProducer
from app.scrapers.browser_engine import BrowserEngine
from app.scrapers.data_cleaner import DataCleaner
from app.scrapers.search_engine import SearchEngine

logger = logging.getLogger(__name__)


class DiscoveryExecutor:
    """Orchestrates the full discovery flow: search → scrape → clean → return."""

    def __init__(
        self,
        search_engine: SearchEngine,
        browser_engine: BrowserEngine,
        data_cleaner: DataCleaner,
        redis_manager: Optional[RedisManager] = None,
        trace_producer: Optional[TraceProducer] = None,
    ) -> None:
        self.search_engine = search_engine
        self.browser_engine = browser_engine
        self.data_cleaner = data_cleaner
        self.redis_manager = redis_manager
        self.trace_producer = trace_producer

    async def execute(
        self,
        request: ExecuteRequest,
        tenant_id: str,
    ) -> ExecuteResponse:
        """
        Execute a full discovery operation.

        1. Build query from input_prompt + config.focus
        2. Check rate limit for tenant
        3. Search via SearchEngine
        4. Scrape and clean each result URL
        5. Return structured response
        """
        # Extract skill context and job_id for trace events
        skill_context = request.config.get("skill_context", "")
        job_id = request.input_context.get("job_id", "")

        # Build the search query
        query = self._build_query(request)
        logger.info("Discovery query for tenant %s: %s", tenant_id, query[:100])

        # Check rate limit
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

        # Search
        await self._emit_trace(job_id, f"Searching for: {query[:80]}")
        search_results = await self.search_engine.search(
            query, max_results=settings.MAX_SCRAPE_URLS
        )

        # Scrape and clean each URL
        sources: list[SourceItem] = []
        findings: list[str] = []
        raw_parts: list[str] = []
        total_urls = len(search_results)

        for i, result in enumerate(search_results):
            url = result.get("url", "")
            title = result.get("title", "")
            snippet = result.get("snippet", "")

            if not url:
                continue

            logger.debug("Scraping %d/%d: %s", i + 1, total_urls, url)
            await self._emit_trace(
                job_id,
                f"Browsing ({i + 1}/{total_urls}): {title or url}",
                metadata={"action": "navigate", "url": url},
            )

            # Scrape the URL
            scrape_result = await self.browser_engine.scrape(url, tenant_id)

            # Check if it's a downloadable file
            if scrape_result.content_type and self.data_cleaner.is_downloadable(
                url, scrape_result.content_type
            ):
                sources.append(SourceItem(type="document", title=title or url, url=url))
                findings.append(f"Downloadable document found: {title or url}")
                continue

            # Clean HTML to Markdown
            if scrape_result.html:
                # If cache returned Markdown, use as-is
                if scrape_result.content_type == "text/markdown":
                    cleaned = scrape_result.html
                else:
                    cleaned = self.data_cleaner.clean(scrape_result.html)

                    # Cache the cleaned content
                    if self.redis_manager and cleaned:
                        await self.redis_manager.set_cached_page(url, cleaned)

                if cleaned:
                    raw_parts.append(cleaned)
                    sources.append(SourceItem(type="web", title=title or url, url=url))

                    # Extract key finding from snippet or cleaned content
                    if snippet:
                        findings.append(snippet)
                    elif cleaned:
                        # Use first 200 chars as finding
                        finding_text = cleaned[:200].strip()
                        if finding_text:
                            findings.append(finding_text)
            else:
                # Scraping failed — still use the search snippet as a finding
                if snippet:
                    findings.append(snippet)
                    sources.append(SourceItem(type="web", title=title or url, url=url))
                logger.debug("Scraping failed for %s, using snippet", url)
                await self._emit_trace(
                    job_id,
                    f"Could not access: {title or url}",
                    metadata={"action": "scrape_failed", "url": url},
                )

        # Build recommendations based on findings
        recommendations = self._build_recommendations(query, findings)

        await self._emit_trace(
            job_id,
            f"Discovery complete. Found {len(sources)} source(s) "
            f"with {len(findings)} finding(s).",
            status="COMPLETED",
        )

        return ExecuteResponse(
            query=query,
            sources=sources,
            findings=findings,
            recommendations=recommendations,
            raw_context="\n\n---\n\n".join(raw_parts),
        )

    async def close(self) -> None:
        """Clean up resources."""
        if self.redis_manager:
            await self.redis_manager.close()
        if self.trace_producer:
            await self.trace_producer.stop()

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
            job_id=job_id, message=message, status=status, metadata=metadata,
        )

    @staticmethod
    def _build_query(request: ExecuteRequest) -> str:
        """Build a search query from input_prompt and config.focus."""
        parts = [request.input_prompt]

        focus = request.config.get("focus", "")
        if focus:
            focus_terms = [t.strip() for t in focus.split(",") if t.strip()]
            parts.extend(focus_terms)

        return " ".join(parts)

    @staticmethod
    def _build_recommendations(query: str, findings: list[str]) -> list[str]:
        """Build simple recommendations based on the search results."""
        recommendations = []

        if not findings:
            recommendations.append("No results found. Try broadening the search query.")
        else:
            recommendations.append(
                f"Review the {len(findings)} findings for actionable insights."
            )
            recommendations.append(
                "Cross-reference web sources with internal data for validation."
            )

        return recommendations
