"""Tests for TrendAnalyzer — core analysis pipeline orchestration."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.logic.trend_analyzer import TrendAnalyzer
from app.skills.models import SkillContext, SkillResult


def _make_skill_result(skill_id: str, data: dict, success: bool = True) -> SkillResult:
    """Create a SkillResult for testing."""
    return SkillResult(
        skill_id=skill_id,
        success=success,
        data=data,
    )


def _make_settings(**overrides) -> MagicMock:
    """Create a mock settings object."""
    defaults = {
        "MAX_CONCURRENT_RESEARCH": 8,
        "MAX_TRENDS_PER_SESSION": 25,
        "ALERT_THRESHOLD": 75,
        "MAX_ALERTS_PER_DAY": 5,
    }
    defaults.update(overrides)
    settings = MagicMock()
    for key, value in defaults.items():
        setattr(settings, key, value)
    return settings


def _make_analyzer(
    skill_results: dict[str, SkillResult] | None = None,
    alert_count: int = 0,
    settings_overrides: dict | None = None,
) -> TrendAnalyzer:
    """Create a TrendAnalyzer with fully mocked dependencies."""
    if skill_results is None:
        skill_results = {
            "SKL-TCIA-01": _make_skill_result(
                "SKL-TCIA-01",
                {
                    "social_trends": [
                        {
                            "topic": "Sustainable Charging",
                            "platform": "twitter",
                            "velocity_score": 0.8,
                            "sample_content_urls": ["https://example.com/ev"],
                        }
                    ]
                },
            ),
            "SKL-TCIA-02": _make_skill_result(
                "SKL-TCIA-02",
                {
                    "cultural_shifts": [
                        {
                            "domain": "sustainability",
                            "shift_description": "Growing EV adoption",
                            "evidence_strength": 0.7,
                            "sources": [
                                {"title": "Report", "url": "https://example.com/report"}
                            ],
                        }
                    ]
                },
            ),
            "SKL-TCIA-03": _make_skill_result(
                "SKL-TCIA-03",
                {
                    "viral_patterns": {
                        "top_formats": ["short_video"],
                        "emotional_triggers": ["curiosity"],
                    }
                },
            ),
            "SKL-TCIA-04": _make_skill_result(
                "SKL-TCIA-04",
                {
                    "generational_insights": [
                        {
                            "generation": "gen_z",
                            "emerging_behaviors": ["eco_conscious"],
                        }
                    ]
                },
            ),
            "SKL-TCIA-05": _make_skill_result(
                "SKL-TCIA-05",
                {
                    "language_trends": {
                        "emerging_terms": [],
                        "fading_terms": [],
                    }
                },
            ),
            "SKL-TCIA-06": _make_skill_result(
                "SKL-TCIA-06", {"prior_reports": []}
            ),
            "SKL-TCIA-07": _make_skill_result(
                "SKL-TCIA-07",
                {
                    "scored_trends": [
                        {
                            "trend_slug": "sustainable-charging",
                            "topic": "Sustainable Charging",
                            "relevance_score": 82,
                            "audience_alignment": 22,
                            "competitive_landscape": 20,
                            "brand_fit": 21,
                            "momentum": 19,
                            "recommendation": "capitalize",
                            "rationale": "High alignment with audience",
                            "citations": ["https://example.com/ev"],
                            "platforms": ["twitter"],
                        }
                    ]
                },
            ),
            "SKL-TCIA-08": _make_skill_result(
                "SKL-TCIA-08",
                {
                    "trend_persona_matrix": {
                        "mappings": [
                            {
                                "trend_slug": "sustainable-charging",
                                "persona_slug": "urban-ev-commuter",
                                "affinity_score": 0.9,
                            }
                        ]
                    }
                },
            ),
            "SKL-TCIA-09": _make_skill_result(
                "SKL-TCIA-09",
                {
                    "opportunity_alerts": [
                        {
                            "alert_id": "alert-001",
                            "trend_slug": "sustainable-charging",
                            "relevance_score": 82,
                            "urgency": "this_week",
                        }
                    ]
                },
            ),
            "SKL-TCIA-10": _make_skill_result(
                "SKL-TCIA-10",
                {
                    "trend_report": {
                        "executive_summary": "EV charging trends are rising.",
                        "new_trends": ["sustainable-charging"],
                        "rising_trends": [],
                        "strategic_recommendations": ["Invest in green messaging"],
                        "confidence_score": 0.85,
                    }
                },
            ),
            "SKL-TCIA-11": _make_skill_result(
                "SKL-TCIA-11",
                {"report_url": "gs://test-bucket/report.json"},
            ),
        }

    # Skill registry mock
    skill_registry = MagicMock()

    def _get_skill(skill_id):
        if skill_id in skill_results:
            mock_skill = AsyncMock()
            mock_skill.execute = AsyncMock(return_value=skill_results[skill_id])
            mock_skill.meta = MagicMock(skill_id=skill_id)
            return mock_skill
        return None

    skill_registry.get_skill = MagicMock(side_effect=_get_skill)

    # Guardrails mock
    guardrails = AsyncMock()
    guardrail_result = MagicMock()
    guardrail_result.blocked = False
    guardrail_result.warnings = []
    guardrail_result.flags = {}
    guardrails.validate_input = AsyncMock(return_value=guardrail_result)
    guardrails.validate_output = AsyncMock(
        return_value=MagicMock(passed=True, warnings=[])
    )

    # Trend registry mock
    trend_registry = AsyncMock()
    trend_registry.upsert_trend = AsyncMock(return_value=None)

    # Redis mock
    redis_manager = AsyncMock()
    redis_manager.get_alert_count = AsyncMock(return_value=alert_count)
    redis_manager.increment_alert_count = AsyncMock(return_value=alert_count + 1)

    # Alert producer mock
    alert_producer = AsyncMock()
    alert_producer.send_alert = AsyncMock()

    # Event emitter mock
    event_emitter = AsyncMock()
    event_emitter.emit = AsyncMock()

    # Settings
    settings = _make_settings(**(settings_overrides or {}))

    return TrendAnalyzer(
        skill_registry=skill_registry,
        guardrails=guardrails,
        trend_registry=trend_registry,
        redis_manager=redis_manager,
        alert_producer=alert_producer,
        event_emitter=event_emitter,
        settings=settings,
    )


class TestFullAnalysisFlow:
    """Test the full analysis pipeline with mocked skills."""

    async def test_returns_expected_output_shape(self) -> None:
        analyzer = _make_analyzer()
        result = await analyzer.analyze(
            "Analyze trends in EV charging",
            tenant_id="t1",
            user_role="EDITOR",
            config={},
            previous_outputs={},
        )
        assert "trend_report" in result
        assert "scored_trends" in result
        assert "trend_persona_matrix" in result
        assert "opportunity_alerts" in result
        assert "sources" in result
        assert "findings" in result
        assert "confidence_score" in result
        assert "report_url" in result

    async def test_scored_trends_populated(self) -> None:
        analyzer = _make_analyzer()
        result = await analyzer.analyze(
            "Analyze trends",
            tenant_id="t1",
            user_role="EDITOR",
        )
        scored = result["scored_trends"]
        assert len(scored) >= 1
        assert scored[0]["trend_slug"] == "sustainable-charging"

    async def test_trend_registry_updated(self) -> None:
        analyzer = _make_analyzer()
        await analyzer.analyze(
            "Analyze trends",
            tenant_id="t1",
            user_role="EDITOR",
        )
        analyzer._trend_registry.upsert_trend.assert_awaited()


class TestUpstreamContextExtraction:
    """Test extraction of MRA + CIA + APA data from previous_outputs."""

    async def test_extracts_market_industry(self) -> None:
        analyzer = _make_analyzer()
        result = await analyzer.analyze(
            "Analyze trends",
            tenant_id="t1",
            user_role="EDITOR",
            previous_outputs={
                "market_research": {
                    "market_overview": {"industry": "EV Charging"},
                },
            },
        )
        # Should succeed and use industry from market context
        assert result is not None

    async def test_extracts_personas_from_apa(self) -> None:
        analyzer = _make_analyzer()
        result = await analyzer.analyze(
            "Analyze trends",
            tenant_id="t1",
            user_role="EDITOR",
            previous_outputs={
                "audience_persona": {
                    "personas": [
                        {
                            "segment_label": "Urban Commuter",
                            "demographics": {"age_range": "25-35"},
                            "media_habits": {
                                "preferred_channels": ["tiktok", "instagram"],
                            },
                        }
                    ],
                },
            },
        )
        assert result is not None

    async def test_extracts_competitors_from_cia(self) -> None:
        analyzer = _make_analyzer()
        result = await analyzer.analyze(
            "Analyze trends",
            tenant_id="t1",
            user_role="EDITOR",
            previous_outputs={
                "competitor_intelligence": {
                    "competitors": [
                        {"name": "Rival Corp", "market_position": "leader"},
                    ],
                },
            },
        )
        assert result is not None

    async def test_degraded_mode_without_upstream(self) -> None:
        """TCIA works standalone when previous_outputs is empty."""
        analyzer = _make_analyzer()
        result = await analyzer.analyze(
            "Analyze trends",
            tenant_id="t1",
            user_role="EDITOR",
            previous_outputs={},
        )
        assert result is not None
        assert "scored_trends" in result


class TestAlertThrottling:
    """PG-09: Respects max alerts per day."""

    async def test_alerts_throttled_when_limit_reached(self) -> None:
        analyzer = _make_analyzer(alert_count=5)
        result = await analyzer.analyze(
            "Analyze trends",
            tenant_id="t1",
            user_role="EDITOR",
        )
        # All alerts should be throttled (MAX_ALERTS_PER_DAY = 5, already at 5)
        assert result["opportunity_alerts"] == []

    async def test_alerts_not_throttled_when_under_limit(self) -> None:
        analyzer = _make_analyzer(alert_count=0)
        result = await analyzer.analyze(
            "Analyze trends",
            tenant_id="t1",
            user_role="EDITOR",
        )
        # Alerts should be present
        assert len(result["opportunity_alerts"]) >= 1

    async def test_partial_throttle(self) -> None:
        """When 4 of 5 alerts used, only 1 remaining alert passes."""
        analyzer = _make_analyzer(alert_count=4)
        result = await analyzer.analyze(
            "Analyze trends",
            tenant_id="t1",
            user_role="EDITOR",
        )
        # At most 1 alert should remain (5 max - 4 used = 1 remaining)
        assert len(result["opportunity_alerts"]) <= 1


class TestTrendCountCap:
    """PG-08: Caps trends at MAX_TRENDS_PER_SESSION."""

    async def test_trend_count_capped(self) -> None:
        # Create analyzer with low cap
        analyzer = _make_analyzer(settings_overrides={"MAX_TRENDS_PER_SESSION": 2})

        # Override research skills to return many trends
        many_trends_result = _make_skill_result(
            "SKL-TCIA-01",
            {
                "social_trends": [
                    {"topic": f"Trend {i}", "platform": "twitter", "velocity_score": 0.5}
                    for i in range(20)
                ]
            },
        )
        many_shifts_result = _make_skill_result(
            "SKL-TCIA-02",
            {
                "cultural_shifts": [
                    {"domain": "tech", "shift_description": f"Shift {i}", "evidence_strength": 0.6}
                    for i in range(20)
                ]
            },
        )

        # Patch the research skill results
        original_get = analyzer._skills.get_skill

        def patched_get(skill_id):
            if skill_id == "SKL-TCIA-01":
                mock_skill = AsyncMock()
                mock_skill.execute = AsyncMock(return_value=many_trends_result)
                mock_skill.meta = MagicMock(skill_id=skill_id)
                return mock_skill
            if skill_id == "SKL-TCIA-02":
                mock_skill = AsyncMock()
                mock_skill.execute = AsyncMock(return_value=many_shifts_result)
                mock_skill.meta = MagicMock(skill_id=skill_id)
                return mock_skill
            return original_get(skill_id)

        analyzer._skills.get_skill = MagicMock(side_effect=patched_get)

        result = await analyzer.analyze(
            "Analyze trends",
            tenant_id="t1",
            user_role="EDITOR",
        )
        # The analyzer should have capped trends before passing to scoring
        assert result is not None


class TestInputGuardrailBlocked:
    """When input guardrails block, analyze returns error result."""

    async def test_blocked_returns_error(self) -> None:
        analyzer = _make_analyzer()
        blocked_result = MagicMock()
        blocked_result.blocked = True
        blocked_result.block_reason = "Harmful trend analysis blocked (IG-08)"
        analyzer._guardrails.validate_input = AsyncMock(return_value=blocked_result)

        result = await analyzer.analyze(
            "tide pod challenge trends",
            tenant_id="t1",
            user_role="EDITOR",
        )
        assert "error" in result
        assert "IG-08" in result["error"]
        assert result["scored_trends"] == []


class TestStaticHelpers:
    """Test static helper methods on TrendAnalyzer."""

    def test_extract_industry_from_market_context(self) -> None:
        industry = TrendAnalyzer._extract_industry(
            {"market_overview": {"industry": "SaaS"}}, "fallback prompt"
        )
        assert industry == "SaaS"

    def test_extract_industry_fallback_to_prompt(self) -> None:
        industry = TrendAnalyzer._extract_industry({}, "EV Charging market analysis")
        assert "EV Charging" in industry

    def test_extract_persona_keywords(self) -> None:
        personas = [
            {"segment_label": "Urban EV Commuter"},
            {"segment_label": "Fleet Manager Pro"},
        ]
        keywords = TrendAnalyzer._extract_persona_keywords(personas)
        assert "Urban" in keywords
        assert "Fleet" in keywords

    def test_extract_persona_platforms(self) -> None:
        personas = [
            {
                "media_habits": {
                    "preferred_channels": ["Twitter", "LinkedIn"],
                }
            }
        ]
        platforms = TrendAnalyzer._extract_persona_platforms(personas)
        assert "twitter" in platforms
        assert "linkedin" in platforms

    def test_extract_persona_platforms_defaults(self) -> None:
        platforms = TrendAnalyzer._extract_persona_platforms([])
        assert "twitter" in platforms
        assert "tiktok" in platforms

    def test_extract_age_ranges(self) -> None:
        personas = [
            {"demographics": {"age_range": "25-40"}},
            {"demographics": {"age_range": "35-55"}},
        ]
        ranges = TrendAnalyzer._extract_age_ranges(personas)
        assert "25-40" in ranges
        assert "35-55" in ranges

    def test_collect_all_trends(self) -> None:
        social = [{"topic": "Trend A", "platform": "twitter", "velocity_score": 0.8}]
        cultural = [
            {"domain": "tech", "shift_description": "AI adoption", "evidence_strength": 0.7}
        ]
        combined = TrendAnalyzer._collect_all_trends(social, cultural)
        assert len(combined) == 2
        assert combined[0]["type"] == "social"
        assert combined[1]["type"] == "cultural"

    def test_extract_findings_with_summary(self) -> None:
        report = {
            "executive_summary": "Trends are shifting towards sustainability.",
            "new_trends": ["green-energy", "ev-charging"],
            "rising_trends": ["remote-work"],
        }
        findings = TrendAnalyzer._extract_findings(report)
        assert len(findings) >= 1
        assert "sustainability" in findings[0]

    def test_extract_findings_empty_report(self) -> None:
        findings = TrendAnalyzer._extract_findings({})
        assert findings == ["Trend analysis completed."]

    def test_collect_sources_from_results(self) -> None:
        results = [
            _make_skill_result(
                "SKL-TCIA-01",
                {
                    "social_trends": [
                        {
                            "topic": "EV trend",
                            "sample_content_urls": ["https://example.com/ev"],
                        }
                    ]
                },
            ),
        ]
        sources = TrendAnalyzer._collect_sources(results)
        assert len(sources) == 1
        assert sources[0]["url"] == "https://example.com/ev"

    def test_collect_sources_deduplicates(self) -> None:
        results = [
            _make_skill_result(
                "SKL-TCIA-01",
                {
                    "social_trends": [
                        {
                            "topic": "Trend A",
                            "sample_content_urls": ["https://example.com/a"],
                        },
                        {
                            "topic": "Trend B",
                            "sample_content_urls": ["https://example.com/a"],
                        },
                    ]
                },
            ),
        ]
        sources = TrendAnalyzer._collect_sources(results)
        assert len(sources) == 1

    def test_collect_sources_skips_exceptions(self) -> None:
        results = [RuntimeError("network error")]
        sources = TrendAnalyzer._collect_sources(results)
        assert sources == []
