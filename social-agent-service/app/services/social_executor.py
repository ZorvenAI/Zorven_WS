"""Core orchestration service for social media promotion."""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException

from app.api.schemas import (
    ExecuteRequest,
    ExecuteResponse,
    PublishResult,
    SocialPost,
)
from app.cache.redis_manager import RedisManager
from app.core.config import settings
from app.logic.platform_adapter import PlatformAdapter
from app.logic.action_resolver import ActionResolver, ResolvedAction
from app.messaging.kafka_producer import SocialAuditProducer, TraceProducer
from app.messaging.schemas import ContentPublishedEvent
from app.services.core_api_client import CoreApiClient
from app.services.mcp_client import McpClient

logger = logging.getLogger(__name__)


class SocialExecutor:
    """Orchestrates social media content adaptation and publishing."""

    def __init__(
        self,
        platform_adapter: PlatformAdapter,
        core_api_client: CoreApiClient,
        redis_manager: RedisManager,
        trace_producer: TraceProducer,
        audit_producer: SocialAuditProducer,
        action_resolver: ActionResolver | None = None,
        mcp_client: McpClient | None = None,
    ) -> None:
        self._adapter = platform_adapter
        self._core_api = core_api_client
        self._redis = redis_manager
        self._trace = trace_producer
        self._audit = audit_producer
        self._action_resolver = action_resolver
        self._mcp = mcp_client

    async def execute(self, request: ExecuteRequest, tenant_id: str) -> ExecuteResponse:
        """Full social promotion flow."""
        job_id = request.input_context.get("job_id", "unknown")

        # 1. Rate limit check
        within_limit = await self._redis.check_rate_limit(
            tenant_id, limit=settings.RATE_LIMIT_PER_MINUTE
        )
        if not within_limit:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

        await self._emit_trace(job_id, "Starting social promotion")

        # 2. Extract content from previous outputs
        blog_output = request.previous_outputs.get("blog_author", {})
        blog_content = blog_output.get("blog_content", "")
        seo_meta = blog_output.get("seo_meta", {})
        if isinstance(seo_meta, str):
            seo_meta = {}

        logger.info(
            "Job %s: previous_outputs keys=%s, blog_content=%d chars",
            job_id,
            list(request.previous_outputs.keys()),
            len(blog_content),
        )

        if not blog_content:
            # Try to build content from brand equity / intelligence results
            blog_content = _build_content_from_previous_outputs(
                request.previous_outputs, request.input_prompt
            )
            if blog_content != request.input_prompt:
                content_hash = hashlib.sha256(blog_content.encode("utf-8")).hexdigest()[
                    :8
                ]
                logger.info(
                    "Job %s: built social content from analysis results "
                    "(len=%d, sha256_prefix=%s)",
                    job_id,
                    len(blog_content),
                    content_hash,
                )
            else:
                logger.info(
                    "Job %s: no analysis data found — using input_prompt " "as content",
                    job_id,
                )

        # 3. Determine target platforms (intersect with connected profiles)
        user_id = request.input_context.get("user_id")
        profiles = await self._core_api.fetch_social_profiles(
            tenant_id, user_id=user_id
        )
        connected_platforms = {p["platform"] for p in profiles}

        # Priority: platforms mentioned in the user's prompt > manifest config > all connected
        prompt_platforms = _extract_platforms_from_prompt(request.input_prompt)
        config_platforms = request.config.get("platforms", [])

        if prompt_platforms:
            requested = prompt_platforms
        elif config_platforms:
            requested = config_platforms
        else:
            requested = list(connected_platforms)

        # Filter to only platforms that are actually connected
        platforms = [p for p in requested if p in connected_platforms]
        unavailable = [p for p in requested if p not in connected_platforms]

        # 4. Cache check (uses effective platforms, not request config)
        cache_key = self._build_cache_key(tenant_id, blog_content, platforms)
        cached = await self._redis.get_cached_result(cache_key)
        if cached:
            logger.info("Cache hit for job %s", job_id)
            return ExecuteResponse(**cached)

        if unavailable:
            logger.warning(
                "Job %s: requested platforms not connected: %s",
                job_id,
                ", ".join(unavailable),
            )

        if not platforms:
            findings = ["No connected social profiles found for requested platforms"]
            if unavailable:
                findings.append(
                    f"Requested but not connected: {', '.join(unavailable)}"
                )
            return ExecuteResponse(
                findings=findings,
                recommendations=[
                    "Connect social media accounts in the Automation settings"
                ],
            )

        await self._emit_trace(job_id, f"Target platforms: {', '.join(platforms)}")

        # 5. Fetch brand persona
        persona = await self._core_api.fetch_brand_persona(tenant_id)
        await self._emit_trace(job_id, "Fetched brand persona")

        # 6. Fetch user role
        user_id = request.input_context.get("user_id")
        user_role = await self._core_api.fetch_user_role(tenant_id, user_id)

        if user_role == "viewer":
            raise HTTPException(
                status_code=403,
                detail="Viewers cannot publish social content",
            )

        # 7. Adapt blog to social posts (with optional skill context from orchestrator)
        skill_context = request.config.get("skill_context", "")
        adapted_posts = await self._adapter.adapt(
            blog_content, seo_meta, persona, platforms,
            skill_context=skill_context,
        )
        await self._emit_trace(
            job_id,
            f"Adapted content for {len(adapted_posts)} platform(s)",
        )

        # Derive a meaningful title from SEO meta or blog content
        content_title = _derive_content_title(seo_meta, blog_content)

        # 7.5. Resolve action intent (publish now vs schedule)
        action = ResolvedAction(action="publish_now")
        if self._action_resolver is not None:
            action = await self._action_resolver.resolve(
                request.input_prompt, platforms
            )
            await self._emit_trace(
                job_id,
                f"Action: {action.action}"
                + (f" at {action.scheduled_date}" if action.scheduled_date else ""),
            )

        # 8. Acquire post locks
        locked_platforms: list[str] = []
        for post in adapted_posts:
            acquired = await self._redis.acquire_post_lock(tenant_id, post.platform)
            if acquired:
                locked_platforms.append(post.platform)
            else:
                logger.warning("Duplicate post lock for %s — skipping", post.platform)

        # 9. Publish or draft
        publish_results: list[PublishResult] = []
        draft_stored = False
        platforms_posted: list[str] = []
        platforms_scheduled: list[str] = []

        if user_role == "editor":
            # Store drafts for admin approval
            draft_stored = True
            for post in adapted_posts:
                if post.platform in locked_platforms:
                    await self._redis.store_draft(
                        job_id,
                        post.platform,
                        post.model_dump(),
                    )
                    publish_results.append(
                        PublishResult(
                            platform=post.platform,
                            status="draft",
                        )
                    )
                    await self._audit.send_audit(
                        tenant_id=tenant_id,
                        job_id=job_id,
                        platform=post.platform,
                        action="draft_stored",
                        content_preview=post.content[:200],
                        user_role=user_role,
                    )
        else:
            # Admin/Owner — publish via MCP or fall back to REST
            user_email = request.input_context.get("user_email")
            use_mcp = self._mcp is not None and user_email is not None

            for post in adapted_posts:
                if post.platform not in locked_platforms:
                    publish_results.append(
                        PublishResult(
                            platform=post.platform,
                            status="failed",
                            error="Duplicate post lock",
                        )
                    )
                    continue

                if use_mcp:
                    pr = await self._publish_via_mcp(
                        post=post,
                        action=action,
                        user_email=user_email,
                        tenant_id=tenant_id,
                        job_id=job_id,
                        title=content_title,
                    )
                    publish_results.append(pr)
                    if pr.status == "published":
                        platforms_posted.append(post.platform)
                    elif pr.status == "scheduled":
                        platforms_scheduled.append(post.platform)
                else:
                    result = await self._core_api.publish_to_platforms(
                        tenant_id=tenant_id,
                        platforms=[post.platform],
                        content=_build_publishable_content(post),
                        title=content_title or _derive_title(post),
                        user_role=user_role,
                        job_id=job_id,
                        user_id=user_id,
                    )

                    pub_status = result.get("status", "failed")
                    platform_results = result.get("results", {})
                    platform_errors = result.get("errors", [])

                    post_id = None
                    post_url = None
                    if post.platform in platform_results:
                        plat_r = platform_results[post.platform]
                        if isinstance(plat_r, dict):
                            post_id = plat_r.get("post_id", plat_r.get("id"))
                            post_url = plat_r.get("post_url", plat_r.get("url"))

                    publish_results.append(
                        PublishResult(
                            platform=post.platform,
                            status=pub_status,
                            post_id=str(post_id) if post_id else None,
                            post_url=str(post_url) if post_url else None,
                            error=(platform_errors[0] if platform_errors else None),
                        )
                    )

                    if pub_status == "published":
                        platforms_posted.append(post.platform)

                await self._audit.send_audit(
                    tenant_id=tenant_id,
                    job_id=job_id,
                    platform=post.platform,
                    action=(
                        publish_results[-1].status
                        if publish_results[-1].status != "failed"
                        else "failed"
                    ),
                    content_preview=post.content[:200],
                    user_role=user_role,
                )

        # 10. Release locks
        for platform in locked_platforms:
            await self._redis.release_post_lock(tenant_id, platform)

        # 11. Build response
        findings = [
            f"Adapted content for {len(adapted_posts)} platform(s)",
        ]
        if unavailable:
            findings.append(f"Not connected: {', '.join(unavailable)} — skipped")
        if draft_stored:
            findings.append("Content saved as drafts for admin approval")
        if platforms_posted:
            findings.append(f"Published to: {', '.join(platforms_posted)}")
        if platforms_scheduled:
            sched_msg = f"Scheduled on: {', '.join(platforms_scheduled)}"
            if action.scheduled_date:
                sched_msg += f" for {action.scheduled_date}"
            findings.append(sched_msg)

        recommendations = []
        if unavailable:
            recommendations.append(
                f"Connect {', '.join(unavailable)} in Automation settings to post there"
            )
        failed = [r for r in publish_results if r.status == "failed"]
        if failed:
            recommendations.append(
                "Some platforms failed — check social profile connections"
            )

        response = ExecuteResponse(
            findings=findings,
            recommendations=recommendations,
            adapted_posts=adapted_posts,
            publish_results=publish_results,
            draft_stored=draft_stored,
            platforms_posted=platforms_posted,
            action_type=action.action,
        )

        # 12. Cache result
        await self._redis.set_cached_result(cache_key, response.model_dump())

        await self._emit_trace(job_id, "Social promotion complete", status="COMPLETED")

        return response

    async def execute_from_event(
        self, event: ContentPublishedEvent, tenant_id: str
    ) -> None:
        """Handle a Kafka content-published event."""
        logger.info(
            "Auto-promoting blog %s for tenant %s",
            event.blog_id,
            tenant_id,
        )
        request = ExecuteRequest(
            input_prompt=event.title,
            input_context={
                "job_id": f"auto-{event.blog_id}",
                "blog_id": event.blog_id,
            },
            previous_outputs={
                "blog_author": {
                    "blog_content": event.title,
                    "gcs_uri": event.markdown_uri,
                    "seo_meta": event.seo_meta,
                }
            },
        )
        try:
            await self.execute(request, tenant_id)
        except HTTPException as exc:
            logger.warning(
                "Auto-promote failed for blog %s: %s",
                event.blog_id,
                exc.detail,
            )

    async def close(self) -> None:
        """Clean up all resources."""
        await self._core_api.close()
        await self._trace.close()
        await self._audit.close()
        await self._redis.close()

    async def _publish_via_mcp(
        self,
        post: SocialPost,
        action: ResolvedAction,
        user_email: str,
        tenant_id: str,
        job_id: str,
        title: str = "",
    ) -> PublishResult:
        """Publish or schedule a single post via MCP server."""
        assert self._mcp is not None
        publish_content = _build_publishable_content(post)
        publish_title = title or _derive_title(post)

        if action.action == "schedule":
            scheduled_date = action.scheduled_date
            if not scheduled_date:
                tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
                scheduled_date = tomorrow.replace(
                    hour=9, minute=0, second=0, microsecond=0
                ).isoformat()

            result = await self._mcp.create_scheduled_content(
                user_email=user_email,
                title=publish_title,
                content=publish_content,
                platforms=[post.platform],
                scheduled_date=scheduled_date,
                tenant_id=tenant_id,
            )
            if result.get("error"):
                return PublishResult(
                    platform=post.platform,
                    status="failed",
                    error=result["error"],
                )
            content_id = result.get("content_id") or result.get("id")
            return PublishResult(
                platform=post.platform,
                status="scheduled",
                post_id=str(content_id) if content_id else None,
                scheduled_date=scheduled_date,
            )

        # publish_now: create content then immediately publish
        now_iso = datetime.now(timezone.utc).isoformat()
        result = await self._mcp.create_scheduled_content(
            user_email=user_email,
            title=publish_title,
            content=publish_content,
            platforms=[post.platform],
            scheduled_date=now_iso,
            tenant_id=tenant_id,
        )
        if result.get("error"):
            return PublishResult(
                platform=post.platform,
                status="failed",
                error=result["error"],
            )
        content_id = result.get("content_id") or result.get("id")
        if not content_id:
            return PublishResult(
                platform=post.platform,
                status="failed",
                error="No content_id returned from MCP",
            )
        pub_result = await self._mcp.publish_content_now(content_id)
        if pub_result.get("error"):
            return PublishResult(
                platform=post.platform,
                status="failed",
                post_id=str(content_id),
                error=pub_result["error"],
            )
        return PublishResult(
            platform=post.platform,
            status="published",
            post_id=str(content_id),
            post_url=pub_result.get("post_url"),
        )

    def _build_cache_key(
        self, tenant_id: str, blog_content: str, platforms: list[str]
    ) -> str:
        raw = f"{tenant_id}:{blog_content[:500]}:{','.join(sorted(platforms))}"
        return hashlib.md5(raw.encode()).hexdigest()

    async def _emit_trace(
        self,
        job_id: str,
        message: str,
        status: str = "PROCESSING",
    ) -> None:
        await self._trace.send_step(job_id=job_id, message=message, status=status)


def _build_content_from_previous_outputs(
    previous_outputs: dict[str, Any],
    fallback: str,
) -> str:
    """Build rich social-media-ready content from upstream node results.

    Scans ``previous_outputs`` for brand equity / intelligence data
    (valuation, BSI, findings) and composes a concise summary that
    Gemini can adapt into a platform-specific post.  Falls back to
    *fallback* (usually the raw user prompt) when nothing useful is found.
    """
    # Look through all upstream outputs for intelligence/valuation data
    valuation_data: dict[str, Any] = {}
    bsi_data: dict[str, Any] = {}
    findings: list[str] = []
    recommendations: list[str] = []

    for _node_id, output in previous_outputs.items():
        if not isinstance(output, dict):
            continue
        # Intelligence agent returns valuation + bsi at the top level
        if "valuation" in output and isinstance(output["valuation"], dict):
            valuation_data = output["valuation"]
        if "bsi" in output and isinstance(output["bsi"], dict):
            bsi_data = output["bsi"]
        if "findings" in output and isinstance(output["findings"], list):
            findings.extend(output["findings"])
        if "recommendations" in output and isinstance(output["recommendations"], list):
            recommendations.extend(output["recommendations"])

    if not valuation_data and not bsi_data and not findings and not recommendations:
        return fallback

    # Compose a structured summary for Gemini to adapt
    parts: list[str] = []

    if valuation_data:
        npv = valuation_data.get("brand_value_npv")
        rate = valuation_data.get("royalty_rate")
        horizon = valuation_data.get("horizon_years")
        method = valuation_data.get("methodology", "royalty relief")
        if npv is not None:
            formatted_npv = f"${npv:,.0f}" if npv >= 1 else str(npv)
            parts.append(f"Brand Valuation: {formatted_npv} (ISO 10668 {method})")
        if rate is not None:
            parts.append(f"Royalty Rate: {rate * 100:.1f}%")
        if horizon is not None:
            parts.append(f"Forecast Horizon: {horizon} years")

    if bsi_data:
        score = bsi_data.get("score")
        if score is not None:
            parts.append(f"Brand Strength Index (BSI): {score}/100")
        pillars = bsi_data.get("pillars", [])
        for pillar in pillars:
            name = pillar.get("name", "")
            pscore = pillar.get("score")
            if name and pscore is not None:
                parts.append(f"  - {name}: {pscore}/100")

    if findings:
        parts.append("")
        parts.append("Key Findings:")
        for f in findings[:5]:
            parts.append(f"- {f}")

    if recommendations:
        parts.append("")
        parts.append("Recommendations:")
        for r in recommendations[:3]:
            parts.append(f"- {r}")

    return "\n".join(parts) if parts else fallback


def _derive_content_title(
    seo_meta: dict[str, Any],
    blog_content: str,
) -> str:
    """Derive a meaningful title from SEO metadata or blog content.

    Tries in order: SEO title, first markdown heading, first non-empty line.
    """
    # 1. SEO title from upstream content agent
    title = seo_meta.get("title", "")
    if isinstance(title, str) and title.strip():
        return title.strip()[:200]

    # 2. First markdown heading in blog content
    for line in blog_content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped.lstrip("# ").strip()[:200]

    # 3. First non-empty line
    for line in blog_content.split("\n"):
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped[:120]

    return ""


def _derive_title(post: SocialPost) -> str:
    """Derive a title from the post content itself (last resort)."""
    first_line = post.content.split("\n", 1)[0].strip()
    if first_line:
        clean = first_line.rstrip("!?.…")
        return clean[:120] if len(clean) > 120 else clean
    return f"{post.platform.capitalize()} post"


def _build_publishable_content(post: SocialPost) -> str:
    """Build the final text to publish, including hashtags if missing.

    Platform-specific behaviour:
    - Twitter/X: cap total hashtags to 2 and enforce 280-char limit.
    - Other platforms: append all missing hashtags.
    """
    content = post.content
    if not post.hashtags:
        return content

    platform = (post.platform or "").lower()

    # Check if hashtags are already present in the content
    existing_tags = {tag.lower() for tag in re.findall(r"#\w+", content)}
    missing = [tag for tag in post.hashtags if tag.lower() not in existing_tags]
    if not missing:
        return content

    # Twitter: stricter hashtag count and character limit
    if platform in ("twitter", "x"):
        max_hashtags_total = 2
        allowed = max(max_hashtags_total - len(existing_tags), 0)
        if allowed <= 0:
            return content
        missing = missing[:allowed]
        candidate = content.rstrip() + "\n\n" + " ".join(missing)
        if len(candidate) > 280:
            return content
        return candidate

    content = content.rstrip() + "\n\n" + " ".join(missing)

    return content


# Platform aliases → canonical platform name
_PLATFORM_ALIASES: dict[str, str] = {
    "linkedin": "linkedin",
    "twitter": "twitter",
    "x": "twitter",
    "facebook": "facebook",
    "fb": "facebook",
    "instagram": "instagram",
    "insta": "instagram",
}

# Short aliases that need word-boundary matching to avoid false positives
# (e.g. "x" matching "next", "example"; "fb" matching "cfb").
_SHORT_ALIASES = {"x", "fb"}


def _extract_platforms_from_prompt(prompt: str) -> list[str]:
    """Parse the user's prompt for explicit platform mentions.

    Returns a deduplicated list of canonical platform names, or an empty
    list if no platforms are mentioned (so the caller falls back to
    manifest config or connected profiles).

    Short aliases ('x', 'fb') use word-boundary regex to avoid false
    positives on words like 'next' or 'example'.
    """
    lower = prompt.lower()
    found: dict[str, None] = {}  # ordered set
    for alias, canonical in _PLATFORM_ALIASES.items():
        if alias in _SHORT_ALIASES:
            if re.search(rf"\b{alias}\b", lower) and canonical not in found:
                found[canonical] = None
        else:
            if alias in lower and canonical not in found:
                found[canonical] = None
    return list(found)
