"""Tests for the Phase 3 IntelligenceExtractor flow."""

from unittest.mock import AsyncMock

import pytest

from app.logic.parser import parse_claude_response
from app.logic.scoring import adjust_confidence, detect_contradictions
from app.api.schemas import LearningOut
from app.services.anthropic_client import AnthropicClient
from app.services.django_client import DjangoClient
from app.services.extractor import IntelligenceExtractor


@pytest.fixture
def campaign_ctx():
    return {
        "campaign": {
            "campaign_id": "camp-1",
            "campaign_name": "Spring Promo",
            "objective": "CONVERSIONS",
            "status": "active",
            "daily_budget_usd": 100.0,
        },
        "company": {
            "name": "Acme",
            "industry": "DTC",
            "positioning_statement": "Premium snacks for busy parents",
            "value_proposition": "Healthy fast snacks",
        },
        "recommendations": [
            {"action_type": "REFRESH", "rationale": "CTR fatigue"},
            {"action_type": "SCALE", "rationale": "ROAS > 2.0"},
            {"action_type": "PAUSE", "rationale": "CPA exceeded target"},
            {"action_type": "REALLOCATE", "rationale": "Ad set 2 underperforms"},
            {"action_type": "REFRESH", "rationale": "Frequency > 3.5"},
        ],
    }


def test_parser_filters_invalid_categories():
    raw = {
        "summary": "ok",
        "learnings": [
            {
                "category": "audience",
                "headline": "Lookalike beats interest",
                "confidence": 80,
                "impact": "HIGH",
                "target_workflow": "WF1",
                "target_agent": "APA",
            },
            {"category": "garbage", "headline": "should drop"},
        ],
    }
    summary, learnings = parse_claude_response(raw)
    assert summary == "ok"
    assert len(learnings) == 1
    assert learnings[0].category == "audience"
    assert learnings[0].confidence == 80


def test_parser_clamps_confidence():
    raw = {
        "learnings": [
            {
                "category": "creative",
                "headline": "x",
                "confidence": 150,
                "impact": "LOW",
                "target_workflow": "WF3",
                "target_agent": "CGA",
            }
        ]
    }
    _, learnings = parse_claude_response(raw)
    assert learnings[0].confidence == 100


def test_adjust_confidence_boost_with_evidence(campaign_ctx):
    le = LearningOut(
        learning_id="l1",
        category="creative",
        headline="x",
        confidence=60,
        impact="MEDIUM",
        target_workflow="WF3",
        target_agent="CGA",
    )
    out = adjust_confidence(le, campaign_ctx)
    assert out.confidence == 70  # +10 from rec count


def test_detect_contradictions_flags_wf2_against_existing_strategy(campaign_ctx):
    learnings = [
        LearningOut(
            learning_id="l1",
            category="messaging",
            headline="Re-position",
            confidence=80,
            impact="HIGH",
            target_workflow="WF2",
            target_agent="BPA",
        ),
        LearningOut(
            learning_id="l2",
            category="creative",
            headline="Refresh",
            confidence=70,
            impact="MEDIUM",
            target_workflow="WF3",
            target_agent="CGA",
        ),
    ]
    contras = detect_contradictions(learnings, campaign_ctx)
    assert len(contras) == 1
    assert contras[0]["learning_id"] == "l1"


@pytest.mark.asyncio
async def test_extractor_with_mocked_claude(campaign_ctx):
    django = DjangoClient()
    django.get_campaign_context = AsyncMock(return_value=campaign_ctx)

    claude = AnthropicClient(api_key=None)
    # Force enabled with a mocked complete_json
    claude._client = object()  # type: ignore[attr-defined]
    claude.complete_json = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "summary": "Strong creative fatigue signal.",
            "learnings": [
                {
                    "category": "creative",
                    "headline": "Refresh top ad set",
                    "detail": {"evidence": "CTR -28% over 7d"},
                    "confidence": 75,
                    "impact": "HIGH",
                    "target_workflow": "WF3",
                    "target_agent": "CGA",
                }
            ],
        }
    )

    extractor = IntelligenceExtractor(
        django_client=django, anthropic_client=claude
    )
    report = await extractor.extract(
        job_id="job-1",
        tenant_id="t1",
        state={"campaign_id": "camp-1"},
        context={"trigger_source": "manual"},
        config={"default_mode": "store_only"},
    )
    assert report.campaign_id == "camp-1"
    assert report.summary.startswith("Strong creative")
    assert len(report.learnings) == 1
    assert report.learnings[0].category == "creative"
    # +10 from evidence count
    assert report.learnings[0].confidence == 85
    assert report.contradictions == []
    assert report.rag_writes == 1


@pytest.mark.asyncio
async def test_extractor_falls_back_to_mock_when_no_context():
    django = DjangoClient()
    django.get_campaign_context = AsyncMock(return_value=None)
    claude = AnthropicClient(api_key=None)  # disabled

    extractor = IntelligenceExtractor(
        django_client=django, anthropic_client=claude
    )
    report = await extractor.extract(
        job_id="job-2",
        tenant_id=None,
        state={"campaign_id": "camp-x"},
        context={},
        config={},
    )
    assert len(report.learnings) == 1
    # Mock confidence 50, then -5 because empty context has no campaign status.
    assert report.learnings[0].confidence == 45
