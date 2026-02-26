"""Tests for ContentExecutor — core orchestration logic."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.schemas import ExecuteRequest, ExecuteResponse
from app.services.content_executor import ContentExecutor


def _make_request(**overrides) -> ExecuteRequest:
    """Create a test ExecuteRequest."""
    defaults = {
        "input_prompt": "Write a blog about Tesla's sustainability strategy",
        "input_context": {"company_id": 42, "job_id": "job-123"},
        "tenant_context": {"tenant_id": "1"},
        "config": {"output_format": "markdown"},
        "previous_outputs": {
            "web_research": {
                "sources": [
                    {"title": "Source A", "url": "https://a.com"},
                ],
                "findings": ["Tesla reduced emissions by 20%."],
                "raw_context": "Tesla sustainability research data.",
            }
        },
    }
    defaults.update(overrides)
    return ExecuteRequest(**defaults)


def _make_executor(rate_allowed=True, cached_result=None):
    """Create an executor with mocked dependencies."""
    mock_seo = AsyncMock()
    mock_seo.optimize = AsyncMock(
        return_value={
            "keywords": ["tesla", "sustainability"],
            "meta_title": "Tesla Sustainability",
            "meta_description": "A guide to Tesla sustainability.",
            "headers": ["Introduction", "Conclusion"],
            "slug": "tesla-sustainability",
        }
    )

    mock_aeo = AsyncMock()
    mock_aeo.format = AsyncMock(
        return_value={
            "faq_items": [
                {"question": "What is Tesla?", "answer": "An EV company."}
            ],
            "structured_data": {"@context": "https://schema.org"},
        }
    )

    mock_geo = MagicMock()
    mock_geo.synthesize = MagicMock(return_value=[])

    mock_blog = AsyncMock()
    mock_blog.author = AsyncMock(
        return_value="# Tesla Sustainability\n\n## Introduction\n\nBlog content here."
    )

    mock_core_api = AsyncMock()
    mock_core_api.fetch_brand_persona = AsyncMock(
        return_value={
            "name": "Tesla",
            "industry": "EV",
            "brand_voice": "innovative",
            "target_audience": "professionals",
            "values": [],
        }
    )

    mock_gcs = AsyncMock()
    mock_gcs.upload_blog = AsyncMock(
        return_value="gs://bucket/1/content/blogs/2026/02/tesla-sustainability.md"
    )

    mock_redis = AsyncMock()
    mock_redis.check_rate_limit = AsyncMock(return_value=rate_allowed)
    mock_redis.get_cached_result = AsyncMock(return_value=cached_result)
    mock_redis.set_cached_result = AsyncMock()

    mock_trace = AsyncMock()
    mock_trace.send_step = AsyncMock()

    mock_published = AsyncMock()
    mock_published.send_published = AsyncMock()

    executor = ContentExecutor(
        seo_optimizer=mock_seo,
        aeo_formatter=mock_aeo,
        geo_synthesizer=mock_geo,
        blog_author=mock_blog,
        core_api_client=mock_core_api,
        gcs_client=mock_gcs,
        redis_manager=mock_redis,
        trace_producer=mock_trace,
        published_producer=mock_published,
    )

    return {
        "executor": executor,
        "seo": mock_seo,
        "aeo": mock_aeo,
        "geo": mock_geo,
        "blog": mock_blog,
        "core_api": mock_core_api,
        "gcs": mock_gcs,
        "redis": mock_redis,
        "trace": mock_trace,
        "published": mock_published,
    }


class TestFullFlow:
    """End-to-end execution flow tests."""

    async def test_execute_full_flow(self) -> None:
        mocks = _make_executor()
        request = _make_request()
        response = await mocks["executor"].execute(request, "tenant-1")

        assert isinstance(response, ExecuteResponse)
        assert response.blog_content.startswith("#")
        assert response.word_count > 0
        assert response.seo_meta is not None
        assert response.seo_meta.slug == "tesla-sustainability"
        assert response.aeo_schema is not None
        assert len(response.findings) > 0
        assert response.gcs_uri.startswith("gs://")

        # Verify all steps were called
        mocks["core_api"].fetch_brand_persona.assert_called_once()
        mocks["seo"].optimize.assert_called_once()
        mocks["geo"].synthesize.assert_called_once()
        mocks["blog"].author.assert_called_once()
        mocks["aeo"].format.assert_called_once()
        mocks["gcs"].upload_blog.assert_called_once()
        mocks["redis"].set_cached_result.assert_called_once()
        mocks["published"].send_published.assert_called_once()

    async def test_handles_missing_research_data(self) -> None:
        mocks = _make_executor()
        request = _make_request(previous_outputs={})
        response = await mocks["executor"].execute(request, "tenant-1")
        assert isinstance(response, ExecuteResponse)
        assert response.blog_content

    async def test_handles_core_api_failure(self) -> None:
        mocks = _make_executor()
        mocks["core_api"].fetch_brand_persona = AsyncMock(
            return_value={
                "name": "Unknown Brand",
                "industry": "General",
                "brand_voice": "professional and informative",
                "target_audience": "business professionals",
                "values": [],
            }
        )
        request = _make_request()
        response = await mocks["executor"].execute(request, "tenant-1")
        assert isinstance(response, ExecuteResponse)


class TestRateLimiting:
    """Rate limit enforcement tests."""

    async def test_rate_limit_returns_429(self) -> None:
        mocks = _make_executor(rate_allowed=False)
        request = _make_request()
        with pytest.raises(HTTPException) as exc_info:
            await mocks["executor"].execute(request, "tenant-1")
        assert exc_info.value.status_code == 429


class TestCaching:
    """Cache behavior tests."""

    async def test_cache_hit_returns_cached(self) -> None:
        cached = {
            "findings": ["Cached finding"],
            "recommendations": [],
            "blog_content": "# Cached Blog",
            "seo_meta": None,
            "aeo_schema": None,
            "citations": [],
            "gcs_uri": "gs://cached",
            "word_count": 2,
        }
        mocks = _make_executor(cached_result=cached)
        request = _make_request()
        response = await mocks["executor"].execute(request, "tenant-1")
        assert response.blog_content == "# Cached Blog"
        # Blog author should NOT have been called
        mocks["blog"].author.assert_not_called()


class TestResearchDataExtraction:
    """Test generic research input from any upstream node."""

    async def test_default_agent_used_when_web_research_empty(self) -> None:
        """When web_research is missing, default_agent data is used."""
        mocks = _make_executor()
        request = _make_request(
            previous_outputs={
                "default_agent": {
                    "summary": "Brand management analysis from RAG store.",
                    "findings": ["Key insight from document."],
                    "sources": [{"title": "Doc A", "url": "gs://bucket/doc-a"}],
                }
            }
        )
        response = await mocks["executor"].execute(request, "tenant-1")
        assert isinstance(response, ExecuteResponse)
        assert response.blog_content

        # SEO optimizer should receive the RAG summary as raw_context
        seo_call = mocks["seo"].optimize.call_args
        assert "Brand management analysis from RAG store." in seo_call.args

    async def test_web_research_takes_precedence(self) -> None:
        """When both web_research and default_agent are present, web_research wins."""
        mocks = _make_executor()
        request = _make_request(
            previous_outputs={
                "web_research": {
                    "raw_context": "Web research context.",
                    "findings": ["Web finding."],
                    "sources": [],
                },
                "default_agent": {
                    "summary": "RAG summary that should NOT be used.",
                    "findings": ["RAG finding."],
                    "sources": [],
                },
            }
        )
        response = await mocks["executor"].execute(request, "tenant-1")
        assert isinstance(response, ExecuteResponse)

        # SEO optimizer should receive web_research data, not RAG
        seo_call = mocks["seo"].optimize.call_args
        assert "Web research context." in seo_call.args

    async def test_rag_summary_maps_to_raw_context(self) -> None:
        """default_agent 'summary' field is normalized to 'raw_context'."""
        from app.services.content_executor import _extract_research_data

        data = _extract_research_data({
            "default_agent": {
                "summary": "RAG document analysis results.",
                "findings": ["Finding 1"],
                "sources": [{"title": "Source 1"}],
            }
        })
        assert data["raw_context"] == "RAG document analysis results."
        assert data["findings"] == ["Finding 1"]
        assert len(data["sources"]) == 1

    async def test_empty_outputs_returns_empty(self) -> None:
        """No research data → returns empty dict."""
        from app.services.content_executor import _extract_research_data

        data = _extract_research_data({})
        assert data == {}

    async def test_empty_data_skips_to_next_key(self) -> None:
        """Empty web_research → falls through to default_agent."""
        from app.services.content_executor import _extract_research_data

        data = _extract_research_data({
            "web_research": {},
            "default_agent": {
                "summary": "RAG data.",
                "findings": [],
                "sources": [],
            },
        })
        assert data["raw_context"] == "RAG data."


class TestCleanup:
    """Resource cleanup tests."""

    async def test_close_cleans_up(self) -> None:
        mocks = _make_executor()
        await mocks["executor"].close()
        mocks["redis"].close.assert_called_once()
        mocks["core_api"].close.assert_called_once()
        mocks["gcs"].close.assert_called_once()
        mocks["trace"].stop.assert_called_once()
        mocks["published"].stop.assert_called_once()
