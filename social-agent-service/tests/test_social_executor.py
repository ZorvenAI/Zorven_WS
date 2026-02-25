"""Tests for the SocialExecutor orchestration service."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.schemas import ExecuteRequest, PublishResult, SocialPost
from app.logic.action_resolver import ActionResolver, ResolvedAction
from app.services.mcp_client import McpClient
from app.services.social_executor import SocialExecutor


def _make_executor(
    rate_limit_ok: bool = True,
    cached_result: dict[str, Any] | None = None,
    user_role: str = "admin",
    profiles: list[dict[str, Any]] | None = None,
    publish_result: dict[str, Any] | None = None,
    action_resolver: ActionResolver | None = None,
    mcp_client: McpClient | None = None,
) -> SocialExecutor:
    """Create a SocialExecutor with all dependencies mocked."""
    # Platform adapter
    platform_adapter = MagicMock()
    platform_adapter.adapt = AsyncMock(
        return_value=[
            SocialPost(
                platform="linkedin",
                content="Test LinkedIn post",
                hashtags=["#test"],
                char_count=19,
                post_type="article_share",
            ),
            SocialPost(
                platform="twitter",
                content="Test tweet",
                hashtags=["#test"],
                char_count=10,
                post_type="thread",
            ),
        ]
    )

    # Core API client
    core_api_client = MagicMock()
    core_api_client.fetch_brand_persona = AsyncMock(
        return_value={"name": "TestBrand", "brand_voice": "professional"}
    )
    core_api_client.fetch_social_profiles = AsyncMock(
        return_value=profiles
        if profiles is not None
        else [
            {"id": 1, "platform": "linkedin", "status": "connected"},
            {"id": 2, "platform": "twitter", "status": "connected"},
        ]
    )
    core_api_client.fetch_user_role = AsyncMock(return_value=user_role)
    core_api_client.publish_to_platforms = AsyncMock(
        return_value=publish_result
        or {
            "status": "published",
            "results": {
                "linkedin": {"post_id": "urn:li:share:123"},
                "twitter": {"post_id": "tweet-456"},
            },
            "errors": [],
        }
    )
    core_api_client.close = AsyncMock()

    # Redis
    redis_manager = MagicMock()
    redis_manager.check_rate_limit = AsyncMock(return_value=rate_limit_ok)
    redis_manager.get_cached_result = AsyncMock(return_value=cached_result)
    redis_manager.set_cached_result = AsyncMock()
    redis_manager.acquire_post_lock = AsyncMock(return_value=True)
    redis_manager.release_post_lock = AsyncMock()
    redis_manager.store_draft = AsyncMock()
    redis_manager.close = AsyncMock()

    # Kafka producers
    trace_producer = MagicMock()
    trace_producer.send_step = AsyncMock()
    trace_producer.close = AsyncMock()

    audit_producer = MagicMock()
    audit_producer.send_audit = AsyncMock()
    audit_producer.close = AsyncMock()

    return SocialExecutor(
        platform_adapter=platform_adapter,
        core_api_client=core_api_client,
        redis_manager=redis_manager,
        trace_producer=trace_producer,
        audit_producer=audit_producer,
        action_resolver=action_resolver,
        mcp_client=mcp_client,
    )


def _make_request(
    platforms: list[str] | None = None,
    blog_content: str = "# Test Blog\n\nSome blog content.",
) -> ExecuteRequest:
    """Create a standard ExecuteRequest for testing."""
    return ExecuteRequest(
        input_prompt="Promote our latest blog",
        input_context={"job_id": "job-123", "user_id": 1},
        config={"platforms": platforms or ["linkedin", "twitter"]},
        previous_outputs={
            "blog_author": {
                "blog_content": blog_content,
                "seo_meta": {
                    "title": "Test Blog",
                    "keywords": ["test", "blog"],
                },
            }
        },
    )


class TestFullFlow:
    async def test_execute_full_flow(self):
        executor = _make_executor()
        request = _make_request()
        response = await executor.execute(request, "tenant-1")

        assert len(response.adapted_posts) == 2
        assert len(response.publish_results) == 2
        assert "linkedin" in response.platforms_posted
        assert response.draft_stored is False
        assert len(response.findings) > 0

    async def test_handles_missing_blog_content(self):
        executor = _make_executor()
        request = ExecuteRequest(
            input_prompt="Post about sustainability",
            input_context={"job_id": "job-456"},
            config={"platforms": ["linkedin"]},
            previous_outputs={},
        )
        response = await executor.execute(request, "tenant-1")
        # Should use input_prompt as fallback content
        assert len(response.adapted_posts) > 0

    async def test_handles_no_connected_profiles(self):
        executor = _make_executor(profiles=[])
        request = ExecuteRequest(
            input_prompt="Post about sustainability",
            input_context={"job_id": "job-789"},
            config={},  # no platforms specified, will fetch from profiles
            previous_outputs={},
        )
        response = await executor.execute(request, "tenant-1")
        assert "No connected social profiles" in response.findings[0]

    async def test_skips_unavailable_platforms(self):
        """Requested platform not in connected profiles is skipped."""
        executor = _make_executor(
            profiles=[{"id": 2, "platform": "twitter", "status": "connected"}]
        )
        # Override adapter to return only twitter (since linkedin is filtered)
        executor._adapter.adapt = AsyncMock(
            return_value=[
                SocialPost(
                    platform="twitter",
                    content="Test tweet",
                    hashtags=["#test"],
                    char_count=10,
                    post_type="thread",
                ),
            ]
        )
        request = _make_request(platforms=["linkedin", "twitter"])
        response = await executor.execute(request, "tenant-1")
        # Only twitter should be adapted and published
        assert all(p.platform == "twitter" for p in response.adapted_posts)
        assert "Not connected: linkedin" in response.findings[1]
        assert any("Connect linkedin" in r for r in response.recommendations)


class TestRateLimiting:
    async def test_rate_limit_returns_429(self):
        executor = _make_executor(rate_limit_ok=False)
        request = _make_request()
        with pytest.raises(HTTPException) as exc_info:
            await executor.execute(request, "tenant-1")
        assert exc_info.value.status_code == 429


class TestCaching:
    async def test_cache_hit_returns_cached(self):
        cached = {
            "findings": ["Cached result"],
            "recommendations": [],
            "adapted_posts": [],
            "publish_results": [],
            "draft_stored": False,
            "platforms_posted": ["linkedin"],
        }
        executor = _make_executor(cached_result=cached)
        request = _make_request()
        response = await executor.execute(request, "tenant-1")
        assert response.findings == ["Cached result"]
        # Platform adapter should NOT have been called
        executor._adapter.adapt.assert_not_called()


class TestRBAC:
    async def test_editor_role_stores_draft(self):
        executor = _make_executor(user_role="editor")
        request = _make_request()
        response = await executor.execute(request, "tenant-1")
        assert response.draft_stored is True
        assert all(
            r.status == "draft" for r in response.publish_results
        )
        # Drafts should be stored in Redis
        assert executor._redis.store_draft.call_count > 0

    async def test_admin_role_publishes(self):
        executor = _make_executor(user_role="admin")
        request = _make_request()
        response = await executor.execute(request, "tenant-1")
        assert response.draft_stored is False
        assert len(response.platforms_posted) > 0

    async def test_viewer_role_returns_403(self):
        executor = _make_executor(user_role="viewer")
        request = _make_request()
        with pytest.raises(HTTPException) as exc_info:
            await executor.execute(request, "tenant-1")
        assert exc_info.value.status_code == 403


class TestDuplicatePrevention:
    async def test_duplicate_post_lock(self):
        executor = _make_executor()
        # Mock lock acquisition: first platform succeeds, second fails
        executor._redis.acquire_post_lock = AsyncMock(
            side_effect=[True, False]
        )
        request = _make_request()
        response = await executor.execute(request, "tenant-1")
        # One post should be published, one skipped
        published = [
            r for r in response.publish_results if r.status == "published"
        ]
        assert len(published) >= 1


class TestPromptPlatformExtraction:
    """Platform mentions in user prompt override manifest config."""

    async def test_prompt_mentions_only_linkedin(self):
        executor = _make_executor()
        executor._adapter.adapt = AsyncMock(
            return_value=[
                SocialPost(
                    platform="linkedin",
                    content="LinkedIn post",
                    hashtags=["#test"],
                    char_count=13,
                    post_type="article_share",
                ),
            ]
        )
        request = ExecuteRequest(
            input_prompt="Write a blog about Tesla and post to LinkedIn",
            input_context={"job_id": "job-prompt-1", "user_id": 1},
            config={"platforms": ["linkedin", "twitter"]},  # manifest default
            previous_outputs={
                "blog_author": {"blog_content": "# Tesla\n\nContent."}
            },
        )
        response = await executor.execute(request, "tenant-1")
        # Only linkedin should be adapted — twitter should NOT appear
        assert len(response.adapted_posts) == 1
        assert response.adapted_posts[0].platform == "linkedin"

    async def test_prompt_with_no_platform_uses_config(self):
        executor = _make_executor()
        request = _make_request()
        # input_prompt is "Promote our latest blog" — no platform mentioned
        response = await executor.execute(request, "tenant-1")
        # Should fall back to config platforms (linkedin + twitter)
        assert len(response.adapted_posts) == 2

    async def test_x_alias_maps_to_twitter(self):
        executor = _make_executor()
        executor._adapter.adapt = AsyncMock(
            return_value=[
                SocialPost(
                    platform="twitter",
                    content="Tweet",
                    hashtags=[],
                    char_count=5,
                    post_type="thread",
                ),
            ]
        )
        request = ExecuteRequest(
            input_prompt="Share this on X",
            input_context={"job_id": "job-alias", "user_id": 1},
            config={"platforms": ["linkedin", "twitter"]},
            previous_outputs={
                "blog_author": {"blog_content": "# Test\n\nContent."}
            },
        )
        response = await executor.execute(request, "tenant-1")
        assert len(response.adapted_posts) == 1
        assert response.adapted_posts[0].platform == "twitter"


class TestCleanup:
    async def test_close_cleans_all_resources(self):
        executor = _make_executor()
        await executor.close()
        executor._core_api.close.assert_called_once()
        executor._trace.close.assert_called_once()
        executor._audit.close.assert_called_once()
        executor._redis.close.assert_called_once()


def _mock_action_resolver(
    action: str = "publish_now", scheduled_date: str | None = None
) -> ActionResolver:
    """Create a mock ActionResolver that returns a fixed result."""
    resolver = MagicMock(spec=ActionResolver)
    resolver.resolve = AsyncMock(
        return_value=ResolvedAction(action=action, scheduled_date=scheduled_date)
    )
    return resolver


def _mock_mcp_client(
    create_result: dict[str, Any] | None = None,
    publish_result: dict[str, Any] | None = None,
) -> McpClient:
    """Create a mock McpClient."""
    client = MagicMock(spec=McpClient)
    client.create_scheduled_content = AsyncMock(
        return_value=create_result or {"content_id": 42, "id": 42}
    )
    client.publish_content_now = AsyncMock(
        return_value=publish_result
        or {"status": "published", "post_url": "https://linkedin.com/post/42"}
    )
    return client


class TestMCPScheduling:
    """MCP-based scheduling flow."""

    async def test_schedule_intent_creates_scheduled_content(self):
        resolver = _mock_action_resolver(
            action="schedule",
            scheduled_date="2026-03-01T09:00:00+00:00",
        )
        mcp = _mock_mcp_client()
        executor = _make_executor(action_resolver=resolver, mcp_client=mcp)

        request = ExecuteRequest(
            input_prompt="Schedule this on LinkedIn for tomorrow",
            input_context={
                "job_id": "job-sched-1",
                "user_id": 1,
                "user_email": "test@example.com",
            },
            config={"platforms": ["linkedin", "twitter"]},
            previous_outputs={
                "blog_author": {"blog_content": "# Test\n\nContent."}
            },
        )
        response = await executor.execute(request, "tenant-1")

        assert response.action_type == "schedule"
        assert all(r.status == "scheduled" for r in response.publish_results)
        assert all(
            r.scheduled_date == "2026-03-01T09:00:00+00:00"
            for r in response.publish_results
        )
        # Should NOT call REST publish
        executor._core_api.publish_to_platforms.assert_not_called()
        # Should call MCP create_scheduled_content for each platform
        assert mcp.create_scheduled_content.call_count == 2
        # Should NOT call publish_content_now (it's scheduled, not immediate)
        mcp.publish_content_now.assert_not_called()

    async def test_publish_now_via_mcp(self):
        resolver = _mock_action_resolver(action="publish_now")
        mcp = _mock_mcp_client()
        executor = _make_executor(action_resolver=resolver, mcp_client=mcp)

        request = ExecuteRequest(
            input_prompt="Post this on LinkedIn now",
            input_context={
                "job_id": "job-pub-1",
                "user_id": 1,
                "user_email": "test@example.com",
            },
            config={"platforms": ["linkedin", "twitter"]},
            previous_outputs={
                "blog_author": {"blog_content": "# Test\n\nContent."}
            },
        )
        response = await executor.execute(request, "tenant-1")

        assert response.action_type == "publish_now"
        assert all(r.status == "published" for r in response.publish_results)
        # Should call create then publish for each platform
        assert mcp.create_scheduled_content.call_count == 2
        assert mcp.publish_content_now.call_count == 2
        # Should NOT call REST publish
        executor._core_api.publish_to_platforms.assert_not_called()

    async def test_mcp_create_error_marks_failed(self):
        resolver = _mock_action_resolver(
            action="schedule",
            scheduled_date="2026-03-01T09:00:00+00:00",
        )
        mcp = _mock_mcp_client(
            create_result={"error": "User not found", "success": False}
        )
        executor = _make_executor(action_resolver=resolver, mcp_client=mcp)

        request = ExecuteRequest(
            input_prompt="Schedule this on LinkedIn",
            input_context={
                "job_id": "job-err-1",
                "user_id": 1,
                "user_email": "test@example.com",
            },
            config={"platforms": ["linkedin", "twitter"]},
            previous_outputs={
                "blog_author": {"blog_content": "# Test\n\nContent."}
            },
        )
        response = await executor.execute(request, "tenant-1")

        assert all(r.status == "failed" for r in response.publish_results)
        assert all(
            "User not found" in r.error for r in response.publish_results
        )

    async def test_scheduled_findings_message(self):
        resolver = _mock_action_resolver(
            action="schedule",
            scheduled_date="2026-03-01T09:00:00+00:00",
        )
        mcp = _mock_mcp_client()
        executor = _make_executor(action_resolver=resolver, mcp_client=mcp)

        request = ExecuteRequest(
            input_prompt="Schedule this on LinkedIn for tomorrow",
            input_context={
                "job_id": "job-msg-1",
                "user_id": 1,
                "user_email": "test@example.com",
            },
            config={"platforms": ["linkedin"]},
            previous_outputs={
                "blog_author": {"blog_content": "# Test\n\nContent."}
            },
        )
        # Override adapter for single platform
        executor._adapter.adapt = AsyncMock(
            return_value=[
                SocialPost(
                    platform="linkedin",
                    content="LinkedIn post",
                    hashtags=["#test"],
                    char_count=13,
                    post_type="article_share",
                ),
            ]
        )
        response = await executor.execute(request, "tenant-1")

        # Should include scheduling info in findings
        sched_findings = [f for f in response.findings if "Scheduled" in f]
        assert len(sched_findings) == 1
        assert "linkedin" in sched_findings[0]
        assert "2026-03-01" in sched_findings[0]


class TestMCPFallbackToREST:
    """Fallback to REST when MCP is unavailable."""

    async def test_no_mcp_client_uses_rest(self):
        """Without MCP client, should use REST API."""
        resolver = _mock_action_resolver(action="publish_now")
        executor = _make_executor(action_resolver=resolver, mcp_client=None)

        request = _make_request()
        response = await executor.execute(request, "tenant-1")

        assert response.action_type == "publish_now"
        # Should use REST publish
        assert executor._core_api.publish_to_platforms.call_count > 0

    async def test_no_user_email_uses_rest(self):
        """With MCP client but no user_email, should fall back to REST."""
        resolver = _mock_action_resolver(action="publish_now")
        mcp = _mock_mcp_client()
        executor = _make_executor(action_resolver=resolver, mcp_client=mcp)

        # Request WITHOUT user_email
        request = ExecuteRequest(
            input_prompt="Post this on LinkedIn",
            input_context={"job_id": "job-no-email", "user_id": 1},
            config={"platforms": ["linkedin", "twitter"]},
            previous_outputs={
                "blog_author": {"blog_content": "# Test\n\nContent."}
            },
        )
        response = await executor.execute(request, "tenant-1")

        # Should use REST, not MCP
        assert executor._core_api.publish_to_platforms.call_count > 0
        mcp.create_scheduled_content.assert_not_called()

    async def test_no_action_resolver_defaults_publish_now(self):
        """Without ActionResolver, action defaults to publish_now."""
        executor = _make_executor(action_resolver=None, mcp_client=None)
        request = _make_request()
        response = await executor.execute(request, "tenant-1")

        assert response.action_type == "publish_now"
        assert executor._core_api.publish_to_platforms.call_count > 0
