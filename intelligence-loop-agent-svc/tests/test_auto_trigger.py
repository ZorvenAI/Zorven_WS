"""Phase 4 — auto-trigger flow tests."""

from unittest.mock import AsyncMock

import pytest

from app.services.anthropic_client import AnthropicClient
from app.services.django_client import DjangoClient
from app.services.extractor import IntelligenceExtractor


def _make_claude(learnings):
    claude = AnthropicClient(api_key=None)
    claude._client = object()  # type: ignore[attr-defined]
    claude.complete_json = AsyncMock(  # type: ignore[method-assign]
        return_value={"summary": "ok", "learnings": learnings}
    )
    return claude


def _make_django(ctx):
    django = DjangoClient()
    django.get_campaign_context = AsyncMock(return_value=ctx)
    django.ingest_intelligence_report = AsyncMock(return_value={"ok": True})
    django.auto_trigger_rerun = AsyncMock(return_value={"job_id": "j1"})
    django.create_wf2_request = AsyncMock(return_value={"id": 1})
    return django


@pytest.mark.asyncio
async def test_auto_trigger_dispatches_high_confidence_wf3():
    ctx = {
        "campaign": {"campaign_id": "c1", "status": "active"},
        "company": {},  # no strategy → no contradictions
        "recommendations": [{"a": i} for i in range(6)],
    }
    django = _make_django(ctx)
    claude = _make_claude(
        [
            {
                "category": "creative",
                "headline": "Refresh top ad",
                "confidence": 80,  # +10 evidence boost → 90
                "impact": "HIGH",
                "target_workflow": "WF3",
                "target_agent": "CGA",
            },
            {
                "category": "audience",
                "headline": "Low signal",
                "confidence": 40,
                "impact": "LOW",
                "target_workflow": "WF1",
                "target_agent": "APA",
            },
        ]
    )
    extractor = IntelligenceExtractor(django_client=django, anthropic_client=claude)
    report = await extractor.extract(
        job_id="j1",
        tenant_id="t1",
        state={"campaign_id": "c1"},
        context={},
        config={"default_mode": "auto_trigger"},
    )

    django.ingest_intelligence_report.assert_awaited_once()
    # High-confidence WF3 dispatched, low-confidence WF1 skipped.
    assert django.auto_trigger_rerun.await_count == 1
    assert django.create_wf2_request.await_count == 0
    assert report.auto_reruns_triggered == 1


@pytest.mark.asyncio
async def test_wf2_always_routes_to_approval_request_even_in_auto_mode():
    ctx = {
        "campaign": {"campaign_id": "c1", "status": "active"},
        "company": {},
        "recommendations": [{"a": i} for i in range(6)],
    }
    django = _make_django(ctx)
    claude = _make_claude(
        [
            {
                "category": "messaging",
                "headline": "Reframe positioning",
                "confidence": 90,
                "impact": "HIGH",
                "target_workflow": "WF2",
                "target_agent": "BPA",
            }
        ]
    )
    extractor = IntelligenceExtractor(django_client=django, anthropic_client=claude)
    await extractor.extract(
        job_id="j2",
        tenant_id="t1",
        state={"campaign_id": "c1"},
        context={},
        config={"default_mode": "auto_trigger"},
    )
    django.auto_trigger_rerun.assert_not_awaited()
    django.create_wf2_request.assert_awaited_once()


@pytest.mark.asyncio
async def test_store_only_mode_does_not_dispatch():
    ctx = {
        "campaign": {"campaign_id": "c1", "status": "active"},
        "company": {},
        "recommendations": [{"a": i} for i in range(6)],
    }
    django = _make_django(ctx)
    claude = _make_claude(
        [
            {
                "category": "creative",
                "headline": "Refresh",
                "confidence": 95,
                "impact": "HIGH",
                "target_workflow": "WF3",
                "target_agent": "CGA",
            }
        ]
    )
    extractor = IntelligenceExtractor(django_client=django, anthropic_client=claude)
    await extractor.extract(
        job_id="j3",
        tenant_id="t1",
        state={"campaign_id": "c1"},
        context={},
        config={"default_mode": "store_only"},
    )
    django.auto_trigger_rerun.assert_not_awaited()
    django.create_wf2_request.assert_not_awaited()
    django.ingest_intelligence_report.assert_awaited_once()
