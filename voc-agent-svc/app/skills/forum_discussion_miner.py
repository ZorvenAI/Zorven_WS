"""SKL-VoCA-07: Forum Discussion Miner — Unprompted opinions from forums."""

import logging
import time
import uuid
from typing import Any

from app.registry.models import ForumFeedback
from app.services.api_clients import TavilySearchClient, WebScraperClient
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)

# Forum platforms to mine
_FORUM_PLATFORMS = [
    {"name": "Reddit", "site_filter": "site:reddit.com"},
    {"name": "Quora", "site_filter": "site:quora.com"},
    {"name": "Industry Forums", "site_filter": "forum OR community"},
]

# Feature request keywords
_FEATURE_REQUEST_KEYWORDS = [
    "feature request",
    "wish list",
    "wishlist",
    "would be nice",
    "should add",
    "please add",
    "needs to have",
    "missing feature",
    "i wish",
    "it would be great",
    "suggestion",
    "proposed",
    "roadmap",
    "vote for",
    "upvote this",
]

# Complaint keywords
_COMPLAINT_KEYWORDS = [
    "frustrat",
    "annoying",
    "terrible",
    "awful",
    "broken",
    "hate",
    "worst",
    "unacceptable",
    "deal breaker",
    "dealbreaker",
    "switched from",
    "moving away",
    "cancelled",
    "canceled",
    "refund",
    "disappointed",
    "horrible",
    "useless",
]


class ForumDiscussionMiner(BaseSkill):
    """Mine Reddit, Quora, and industry forums for unprompted opinions."""

    meta = SkillMeta(
        skill_id="SKL-VoCA-07",
        name="forum_discussion_miner",
        description=(
            "Mines Reddit, Quora, and industry forums for unprompted "
            "opinions, feature requests, and complaints. Extracts "
            "thread context, upvotes, and categorizes feedback type."
        ),
        allowed_roles=["OWNER", "ADMIN", "EDITOR", "VIEWER"],
        timeout_ms=45000,
        circuit_breaker_dependency="tavily",
    )

    def __init__(
        self,
        tavily_client: TavilySearchClient,
        web_scraper: WebScraperClient,
    ) -> None:
        self.tavily_client = tavily_client
        self.web_scraper = web_scraper

    async def execute(
        self, input_data: dict[str, Any], context: SkillContext
    ) -> SkillResult:
        """
        Mine forums for unprompted opinions, feature requests, and complaints.

        input_data keys:
          - company_name (str): Brand/company name to search for
          - prompt (str): Additional search context
        """
        start = time.monotonic()
        company_name = input_data.get("company_name", "")

        if not company_name:
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error="No company_name provided",
                duration_ms=_elapsed(start),
            )

        try:
            forum_feedback: list[dict[str, Any]] = []
            sources: list[dict[str, str]] = []

            # Build search queries per forum platform
            for platform in _FORUM_PLATFORMS:
                search_queries = [
                    (
                        f"{platform['site_filter']} {company_name} "
                        f"opinions feedback experience"
                    ),
                    (
                        f"{platform['site_filter']} {company_name} "
                        f"feature request wishlist"
                    ),
                    (
                        f"{platform['site_filter']} {company_name} "
                        f"complaint issue problem"
                    ),
                ]

                for query in search_queries:
                    results = await self.tavily_client.search(query, max_results=5)

                    for r in results:
                        url = r.get("url", "")
                        content = r.get("content", "")
                        title = r.get("title", "")

                        # Attempt deeper scraping for thread context
                        scraped_content = ""
                        if url:
                            scraped_content = await self.web_scraper.scrape(
                                url, max_chars=3000
                            )

                        full_content = scraped_content or content

                        # Classify feedback type
                        is_feature_req = _is_feature_request(full_content)

                        # Extract upvotes from content
                        upvotes = _extract_upvotes(full_content)

                        feedback = ForumFeedback(
                            feedback_id=f"forum-{uuid.uuid4().hex[:12]}",
                            text=full_content[:2000],
                            platform=platform["name"],
                            thread_title=title,
                            upvotes=upvotes,
                            is_feature_request=is_feature_req,
                            metadata={
                                "source_url": url,
                                "is_complaint": _is_complaint(full_content),
                                "search_query": query,
                            },
                        )
                        forum_feedback.append(feedback.model_dump())

                        if url:
                            sources.append(
                                {
                                    "type": "forum",
                                    "title": title,
                                    "url": url,
                                    "platform": platform["name"],
                                }
                            )

            # Deduplicate by URL
            seen_urls: set[str] = set()
            deduped_feedback: list[dict[str, Any]] = []
            deduped_sources: list[dict[str, str]] = []

            for fb in forum_feedback:
                fb_url = fb.get("metadata", {}).get("source_url", "")
                if fb_url and fb_url in seen_urls:
                    continue
                if fb_url:
                    seen_urls.add(fb_url)
                deduped_feedback.append(fb)

            for src in sources:
                src_url = src.get("url", "")
                if src_url and src_url in seen_urls:
                    continue
                if src_url:
                    seen_urls.add(src_url)
                deduped_sources.append(src)

            feature_count = sum(
                1 for f in deduped_feedback if f.get("is_feature_request", False)
            )
            complaint_count = sum(
                1
                for f in deduped_feedback
                if f.get("metadata", {}).get("is_complaint", False)
            )

            logger.info(
                "Forum mining for '%s': %d threads (%d feature requests, "
                "%d complaints) from %d platforms",
                company_name,
                len(deduped_feedback),
                feature_count,
                complaint_count,
                len(_FORUM_PLATFORMS),
            )

            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={
                    "forum_feedback": deduped_feedback,
                    "sources": deduped_sources,
                },
                duration_ms=_elapsed(start),
            )

        except Exception as exc:
            logger.error(
                "Forum discussion mining failed for '%s': %s",
                company_name,
                exc,
            )
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error=str(exc),
                duration_ms=_elapsed(start),
            )


def _is_feature_request(content: str) -> bool:
    """Check if content contains a feature request."""
    lower = content.lower()
    return any(kw in lower for kw in _FEATURE_REQUEST_KEYWORDS)


def _is_complaint(content: str) -> bool:
    """Check if content contains a complaint."""
    lower = content.lower()
    return any(kw in lower for kw in _COMPLAINT_KEYWORDS)


def _extract_upvotes(content: str) -> int:
    """Attempt to extract upvote/point count from forum content."""
    import re

    lower = content.lower()
    patterns = [
        r"(\d[\d,]*)\s*(?:upvotes?|points?|votes?|likes?)",
        r"(?:upvotes?|points?|score)[:\s]+(\d[\d,]*)",
    ]
    for pattern in patterns:
        match = re.search(pattern, lower)
        if match:
            try:
                return int(match.group(1).replace(",", ""))
            except ValueError:
                continue
    return 0


def _elapsed(start: float) -> float:
    return (time.monotonic() - start) * 1000
