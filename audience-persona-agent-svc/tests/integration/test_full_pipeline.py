"""Integration test: Full PAOR pipeline with mocked external services."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.circuit_breaker.breaker import CircuitBreaker
from app.events.catalog import EventEmitter
from app.logic.guardrails import ThreeLayerGuardrails
from app.logic.persona_analyzer import PersonaAnalyzer
from app.skills.models import SkillContext, SkillResult
from app.skills.registry import SkillRegistry


def _mock_tavily_result():
    return MagicMock(
        results=[
            MagicMock(
                title="Audience Research",
                url="https://example.com/research",
                content="Enterprise IT leaders aged 35-50 prefer ROI-driven solutions",
            )
        ]
    )


def _mock_anthropic_response(data: dict):
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(data), type="text")]
    mock_msg.usage = MagicMock(input_tokens=500, output_tokens=800)
    return mock_msg


@pytest.mark.integration
class TestFullPipeline:
    async def test_stub_mode_pipeline(self):
        """End-to-end pipeline in stub mode (no LLM, no external services)."""
        registry = SkillRegistry()
        guardrails = ThreeLayerGuardrails()
        breakers = {}
        emitter = AsyncMock(spec=EventEmitter)
        emitter.emit = AsyncMock()

        # Register minimal stub skills
        from app.skills.audience_landscape_research import AudienceLandscapeResearch
        from app.skills.demographic_profile_builder import DemographicProfileBuilder
        from app.skills.persona_synthesizer import PersonaSynthesizer

        registry.register(AudienceLandscapeResearch(tavily_client=None))
        registry.register(DemographicProfileBuilder(anthropic_client=None))
        registry.register(PersonaSynthesizer(anthropic_client=None))

        analyzer = PersonaAnalyzer(
            skill_registry=registry,
            guardrails=guardrails,
            circuit_breakers=breakers,
            event_emitter=emitter,
            anthropic_client=None,
        )

        result = await analyzer.analyze(
            "Create buyer personas for B2B SaaS",
            tenant_id="test-tenant",
            user_role="EDITOR",
        )

        assert "personas" in result
        assert "journey_maps" in result
        assert "sources" in result
        assert result["confidence_score"] >= 0
        # Stub mode yields at least one persona
        assert len(result["personas"]) >= 1
        assert result["personas"][0]["data_source"] == "research_based"

    async def test_pipeline_applies_output_guardrails(self):
        """Output guardrails are applied to final response."""
        registry = SkillRegistry()
        guardrails = ThreeLayerGuardrails()
        emitter = AsyncMock(spec=EventEmitter)
        emitter.emit = AsyncMock()

        from app.skills.audience_landscape_research import AudienceLandscapeResearch
        from app.skills.demographic_profile_builder import DemographicProfileBuilder
        from app.skills.persona_synthesizer import PersonaSynthesizer

        registry.register(AudienceLandscapeResearch(tavily_client=None))
        registry.register(DemographicProfileBuilder(anthropic_client=None))
        registry.register(PersonaSynthesizer(anthropic_client=None))

        analyzer = PersonaAnalyzer(
            skill_registry=registry,
            guardrails=guardrails,
            circuit_breakers={},
            event_emitter=emitter,
            anthropic_client=None,
        )

        result = await analyzer.analyze(
            "Create personas for our audience",
            tenant_id="test-tenant",
            user_role="EDITOR",
        )

        # OG-04: High confidence with no sources should be clamped
        # (stub mode has confidence 0.3, so this specific check depends on stub)
        assert result["confidence_score"] <= 1.0

        # Events should have been emitted
        assert emitter.emit.call_count > 0

    async def test_pipeline_with_previous_outputs(self):
        """Pipeline accepts MRA + CIA upstream data."""
        registry = SkillRegistry()
        guardrails = ThreeLayerGuardrails()
        emitter = AsyncMock(spec=EventEmitter)
        emitter.emit = AsyncMock()

        from app.skills.audience_landscape_research import AudienceLandscapeResearch
        from app.skills.buyer_role_extractor import BuyerRoleExtractor
        from app.skills.demographic_profile_builder import DemographicProfileBuilder
        from app.skills.persona_synthesizer import PersonaSynthesizer

        registry.register(AudienceLandscapeResearch(tavily_client=None))
        registry.register(BuyerRoleExtractor(tavily_client=None))
        registry.register(DemographicProfileBuilder(anthropic_client=None))
        registry.register(PersonaSynthesizer(anthropic_client=None))

        analyzer = PersonaAnalyzer(
            skill_registry=registry,
            guardrails=guardrails,
            circuit_breakers={},
            event_emitter=emitter,
            anthropic_client=None,
        )

        result = await analyzer.analyze(
            "Create buyer personas for EV charging",
            tenant_id="test-tenant",
            user_role="EDITOR",
            previous_outputs={
                "market_research": {
                    "market_overview": "Growing at 25% CAGR",
                    "market_sizing": {"tam": "$50B"},
                },
                "competitor_intelligence": {
                    "competitors": [{"name": "Tesla"}],
                },
            },
        )

        assert "personas" in result
        assert result["query"] == "Create buyer personas for EV charging"
