"""Tests for individual TCIA skills — SKL-TCIA-01, 02, 07, 09."""

import json
from unittest.mock import AsyncMock, MagicMock

from app.skills.models import SkillContext, SkillMeta, SkillResult


# ===== SKL-TCIA-01: Social Trend Scanner =====


class TestSocialTrendScanner:
    """Tests for SKL-TCIA-01."""

    def setup_method(self) -> None:
        from app.skills.skl_tcia_01_social_trend_scanner import SocialTrendScanner

        self.tavily = AsyncMock()
        self.scraper = AsyncMock()
        self.skill = SocialTrendScanner(
            tavily_client=self.tavily,
            scraper_client=self.scraper,
        )

    def test_meta(self) -> None:
        assert self.skill.meta.skill_id == "SKL-TCIA-01"
        assert self.skill.meta.name == "social_trend_scanner"
        assert self.skill.meta.circuit_breaker_dependency == "tavily"
        assert "VIEWER" in self.skill.meta.allowed_roles

    async def test_execute_returns_social_trends(self) -> None:
        self.tavily.search = AsyncMock(
            return_value=[
                {
                    "title": "EV Charging Growth",
                    "url": "https://example.com/ev",
                    "content": "#EVcharging is trending, #sustainable energy",
                },
            ]
        )
        ctx = SkillContext(tenant_id="t1", user_role="EDITOR")
        result = await self.skill.execute(
            {"industry": "EV Charging", "platforms": ["twitter"]}, ctx
        )
        assert result.success
        assert result.skill_id == "SKL-TCIA-01"
        trends = result.data["social_trends"]
        assert len(trends) >= 1
        assert trends[0]["platform"] == "twitter"

    async def test_extracts_hashtags(self) -> None:
        self.tavily.search = AsyncMock(
            return_value=[
                {
                    "title": "Test",
                    "url": "https://example.com",
                    "content": "Check out #EVcharging and #renewable trends",
                },
            ]
        )
        ctx = SkillContext(tenant_id="t1", user_role="EDITOR")
        result = await self.skill.execute(
            {"industry": "EV", "platforms": ["twitter"]}, ctx
        )
        trends = result.data["social_trends"]
        assert "#EVcharging" in trends[0]["hashtags"]
        assert "#renewable" in trends[0]["hashtags"]

    async def test_handles_tavily_failure(self) -> None:
        self.tavily.search = AsyncMock(side_effect=Exception("API error"))
        ctx = SkillContext(tenant_id="t1", user_role="EDITOR")
        result = await self.skill.execute(
            {"industry": "EV", "platforms": ["twitter"]}, ctx
        )
        # Should not raise, returns empty trends
        assert result.success
        assert result.data["social_trends"] == []

    async def test_multiple_platforms(self) -> None:
        self.tavily.search = AsyncMock(
            return_value=[
                {
                    "title": "Trend",
                    "url": "https://example.com",
                    "content": "Trending content",
                },
            ]
        )
        ctx = SkillContext(tenant_id="t1", user_role="EDITOR")
        result = await self.skill.execute(
            {"industry": "EV", "platforms": ["twitter", "reddit", "tiktok"]},
            ctx,
        )
        assert result.success
        trends = result.data["social_trends"]
        platforms = {t["platform"] for t in trends}
        assert "twitter" in platforms
        assert "reddit" in platforms
        assert "tiktok" in platforms

    async def test_with_circuit_breaker(self) -> None:
        cb_tavily = AsyncMock()
        cb_tavily.call = AsyncMock(
            return_value=[
                {
                    "title": "CB Result",
                    "url": "https://example.com/cb",
                    "content": "Protected by circuit breaker",
                },
            ]
        )
        from app.skills.skl_tcia_01_social_trend_scanner import SocialTrendScanner

        skill = SocialTrendScanner(
            tavily_client=self.tavily,
            scraper_client=self.scraper,
            cb_tavily=cb_tavily,
        )
        ctx = SkillContext(tenant_id="t1", user_role="EDITOR")
        result = await skill.execute(
            {"industry": "EV", "platforms": ["twitter"]}, ctx
        )
        assert result.success
        cb_tavily.call.assert_awaited()

    async def test_persona_keywords_in_query(self) -> None:
        self.tavily.search = AsyncMock(return_value=[])
        ctx = SkillContext(tenant_id="t1", user_role="EDITOR")
        await self.skill.execute(
            {
                "industry": "EV",
                "platforms": ["twitter"],
                "persona_keywords": ["urban", "commuter"],
            },
            ctx,
        )
        # Verify the search was called with persona keywords in query
        call_args = self.tavily.search.call_args
        assert "urban" in call_args[0][0] or "urban" in str(call_args)


# ===== SKL-TCIA-02: Cultural Shift Monitor =====


class TestCulturalShiftMonitor:
    """Tests for SKL-TCIA-02."""

    def setup_method(self) -> None:
        from app.skills.skl_tcia_02_cultural_shift_monitor import CulturalShiftMonitor

        self.tavily = AsyncMock()
        self.skill = CulturalShiftMonitor(tavily_client=self.tavily)

    def test_meta(self) -> None:
        assert self.skill.meta.skill_id == "SKL-TCIA-02"
        assert self.skill.meta.name == "cultural_shift_monitor"
        assert self.skill.meta.circuit_breaker_dependency == "tavily"

    async def test_execute_returns_cultural_shifts(self) -> None:
        self.tavily.search = AsyncMock(
            return_value=[
                {
                    "title": "Sustainability in Consumer Culture",
                    "url": "https://example.com/culture",
                    "content": "Major cultural shift towards eco-consciousness",
                },
            ]
        )
        ctx = SkillContext(tenant_id="t1", user_role="EDITOR")
        result = await self.skill.execute(
            {
                "industry": "EV Charging",
                "cultural_domains": ["sustainability"],
            },
            ctx,
        )
        assert result.success
        assert result.skill_id == "SKL-TCIA-02"
        shifts = result.data["cultural_shifts"]
        assert len(shifts) >= 1
        assert shifts[0]["domain"] == "sustainability"

    async def test_shift_includes_sources(self) -> None:
        self.tavily.search = AsyncMock(
            return_value=[
                {
                    "title": "Culture Report",
                    "url": "https://example.com/report",
                    "content": "Shift details here",
                },
            ]
        )
        ctx = SkillContext(tenant_id="t1", user_role="EDITOR")
        result = await self.skill.execute(
            {"industry": "EV", "cultural_domains": ["values"]}, ctx
        )
        shifts = result.data["cultural_shifts"]
        assert len(shifts[0]["sources"]) >= 1
        assert shifts[0]["sources"][0]["url"] == "https://example.com/report"

    async def test_handles_tavily_failure(self) -> None:
        self.tavily.search = AsyncMock(side_effect=Exception("API error"))
        ctx = SkillContext(tenant_id="t1", user_role="EDITOR")
        result = await self.skill.execute(
            {"industry": "EV", "cultural_domains": ["values"]}, ctx
        )
        assert result.success
        assert result.data["cultural_shifts"] == []

    async def test_multiple_domains(self) -> None:
        self.tavily.search = AsyncMock(
            return_value=[
                {
                    "title": "Domain Trend",
                    "url": "https://example.com",
                    "content": "Trend content",
                },
            ]
        )
        ctx = SkillContext(tenant_id="t1", user_role="EDITOR")
        result = await self.skill.execute(
            {
                "industry": "EV",
                "cultural_domains": ["values", "lifestyle", "sustainability"],
            },
            ctx,
        )
        assert result.success
        domains = {s["domain"] for s in result.data["cultural_shifts"]}
        assert "values" in domains
        assert "lifestyle" in domains
        assert "sustainability" in domains

    async def test_description_truncated(self) -> None:
        self.tavily.search = AsyncMock(
            return_value=[
                {
                    "title": "Long Content",
                    "url": "https://example.com",
                    "content": "x" * 1000,
                },
            ]
        )
        ctx = SkillContext(tenant_id="t1", user_role="EDITOR")
        result = await self.skill.execute(
            {"industry": "EV", "cultural_domains": ["tech"]}, ctx
        )
        shifts = result.data["cultural_shifts"]
        assert len(shifts[0]["shift_description"]) <= 500


# ===== SKL-TCIA-07: Cultural Relevance Scorer =====


class TestCulturalRelevanceScorer:
    """Tests for SKL-TCIA-07."""

    def setup_method(self) -> None:
        from app.skills.skl_tcia_07_cultural_relevance_scorer import (
            CulturalRelevanceScorer,
        )

        self.anthropic = AsyncMock()
        self.skill = CulturalRelevanceScorer(anthropic_client=self.anthropic)

    def test_meta(self) -> None:
        assert self.skill.meta.skill_id == "SKL-TCIA-07"
        assert self.skill.meta.name == "cultural_relevance_scorer"
        assert self.skill.meta.circuit_breaker_dependency == "llm"
        assert "VIEWER" not in self.skill.meta.allowed_roles

    async def test_execute_with_anthropic(self) -> None:
        scored = [
            {
                "trend_slug": "ev-growth",
                "topic": "EV Growth",
                "relevance_score": 85,
                "audience_alignment": 22,
                "competitive_landscape": 21,
                "brand_fit": 22,
                "momentum": 20,
                "recommendation": "capitalize",
                "rationale": "Strong alignment",
                "citations": ["https://example.com"],
                "platforms": ["twitter"],
            }
        ]
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=json.dumps(scored), type="text")]
        mock_msg.usage = MagicMock(input_tokens=500, output_tokens=300)
        self.anthropic.messages.create = AsyncMock(return_value=mock_msg)

        ctx = SkillContext(tenant_id="t1", user_role="EDITOR")
        result = await self.skill.execute(
            {
                "trends": [{"topic": "EV Growth", "type": "social"}],
                "personas": [],
                "competitor_landscape": {},
                "market_context": {},
            },
            ctx,
        )
        assert result.success
        assert len(result.data["scored_trends"]) == 1
        assert result.data["scored_trends"][0]["relevance_score"] == 85
        assert result.tokens_used == 800

    async def test_stub_mode_without_anthropic(self) -> None:
        from app.skills.skl_tcia_07_cultural_relevance_scorer import (
            CulturalRelevanceScorer,
        )

        skill = CulturalRelevanceScorer(anthropic_client=None)
        ctx = SkillContext(tenant_id="t1", user_role="EDITOR")
        result = await skill.execute(
            {
                "trends": [
                    {"topic": "EV Growth", "type": "social"},
                    {"topic": "Remote Work", "type": "cultural"},
                ],
            },
            ctx,
        )
        assert result.success
        scored = result.data["scored_trends"]
        assert len(scored) == 2
        # Stub always returns score of 50
        assert scored[0]["relevance_score"] == 50
        assert scored[0]["recommendation"] == "monitor"

    async def test_handles_json_in_markdown_fences(self) -> None:
        scored_json = json.dumps(
            [
                {
                    "trend_slug": "test",
                    "topic": "Test",
                    "relevance_score": 70,
                    "audience_alignment": 18,
                    "competitive_landscape": 17,
                    "brand_fit": 18,
                    "momentum": 17,
                    "recommendation": "monitor",
                    "rationale": "Test",
                    "citations": [],
                    "platforms": [],
                }
            ]
        )
        mock_msg = MagicMock()
        mock_msg.content = [
            MagicMock(text=f"```json\n{scored_json}\n```", type="text")
        ]
        mock_msg.usage = MagicMock(input_tokens=100, output_tokens=100)
        self.anthropic.messages.create = AsyncMock(return_value=mock_msg)

        ctx = SkillContext(tenant_id="t1", user_role="EDITOR")
        result = await self.skill.execute(
            {"trends": [{"topic": "Test"}]}, ctx
        )
        assert result.success
        assert len(result.data["scored_trends"]) == 1

    async def test_handles_llm_failure(self) -> None:
        self.anthropic.messages.create = AsyncMock(
            side_effect=Exception("LLM timeout")
        )
        ctx = SkillContext(tenant_id="t1", user_role="EDITOR")
        result = await self.skill.execute(
            {"trends": [{"topic": "Test"}]}, ctx
        )
        # Should fall back to stub
        assert result.success
        assert result.data["scored_trends"][0]["relevance_score"] == 50

    async def test_parse_json_invalid_returns_empty(self) -> None:
        from app.skills.skl_tcia_07_cultural_relevance_scorer import (
            CulturalRelevanceScorer,
        )

        result = CulturalRelevanceScorer._parse_json_response("not valid json")
        assert result == []

    async def test_parse_json_object_returns_empty(self) -> None:
        from app.skills.skl_tcia_07_cultural_relevance_scorer import (
            CulturalRelevanceScorer,
        )

        result = CulturalRelevanceScorer._parse_json_response('{"key": "value"}')
        assert result == []

    async def test_set_odoo_client(self) -> None:
        mock_odoo = AsyncMock()
        mock_redis = AsyncMock()
        self.skill.set_odoo_client(mock_odoo, mock_redis)
        assert self.skill._odoo_client is mock_odoo
        assert self.skill._redis is mock_redis


# ===== SKL-TCIA-09: Opportunity Alert Generator =====


class TestOpportunityAlertGenerator:
    """Tests for SKL-TCIA-09."""

    def setup_method(self) -> None:
        from app.skills.skl_tcia_09_opportunity_alert_generator import (
            OpportunityAlertGenerator,
        )

        self.skill = OpportunityAlertGenerator()

    def test_meta(self) -> None:
        assert self.skill.meta.skill_id == "SKL-TCIA-09"
        assert self.skill.meta.name == "opportunity_alert_generator"
        assert self.skill.meta.circuit_breaker_dependency == "llm"
        assert "VIEWER" not in self.skill.meta.allowed_roles

    async def test_generates_alerts_above_threshold(self) -> None:
        ctx = SkillContext(tenant_id="t1", user_role="EDITOR")
        result = await self.skill.execute(
            {
                "scored_trends": [
                    {
                        "trend_slug": "ev-growth",
                        "relevance_score": 85,
                        "recommendation": "capitalize",
                        "rationale": "Strong momentum",
                    },
                    {
                        "trend_slug": "remote-work",
                        "relevance_score": 60,
                        "recommendation": "monitor",
                        "rationale": "Moderate interest",
                    },
                ],
                "trend_persona_matrix": {"mappings": []},
                "alert_threshold": 75,
            },
            ctx,
        )
        assert result.success
        alerts = result.data["opportunity_alerts"]
        # Only ev-growth (85) should generate alert, remote-work (60) below threshold
        assert len(alerts) == 1
        assert alerts[0]["trend_slug"] == "ev-growth"

    async def test_urgency_immediate(self) -> None:
        ctx = SkillContext(tenant_id="t1", user_role="EDITOR")
        result = await self.skill.execute(
            {
                "scored_trends": [
                    {
                        "trend_slug": "viral-trend",
                        "relevance_score": 95,
                        "recommendation": "capitalize",
                        "rationale": "Extremely high velocity",
                    },
                ],
                "trend_persona_matrix": {"mappings": []},
                "alert_threshold": 75,
            },
            ctx,
        )
        alerts = result.data["opportunity_alerts"]
        assert alerts[0]["urgency"] == "immediate"

    async def test_urgency_this_week(self) -> None:
        ctx = SkillContext(tenant_id="t1", user_role="EDITOR")
        result = await self.skill.execute(
            {
                "scored_trends": [
                    {
                        "trend_slug": "rising-trend",
                        "relevance_score": 85,
                        "recommendation": "capitalize",
                        "rationale": "Growing fast",
                    },
                ],
                "trend_persona_matrix": {"mappings": []},
                "alert_threshold": 75,
            },
            ctx,
        )
        alerts = result.data["opportunity_alerts"]
        assert alerts[0]["urgency"] == "this_week"

    async def test_urgency_this_month(self) -> None:
        ctx = SkillContext(tenant_id="t1", user_role="EDITOR")
        result = await self.skill.execute(
            {
                "scored_trends": [
                    {
                        "trend_slug": "slow-trend",
                        "relevance_score": 76,
                        "recommendation": "capitalize",
                        "rationale": "Steady growth",
                    },
                ],
                "trend_persona_matrix": {"mappings": []},
                "alert_threshold": 75,
            },
            ctx,
        )
        alerts = result.data["opportunity_alerts"]
        assert alerts[0]["urgency"] == "this_month"

    async def test_no_alerts_below_threshold(self) -> None:
        ctx = SkillContext(tenant_id="t1", user_role="EDITOR")
        result = await self.skill.execute(
            {
                "scored_trends": [
                    {
                        "trend_slug": "low-trend",
                        "relevance_score": 40,
                        "recommendation": "avoid",
                        "rationale": "Low relevance",
                    },
                ],
                "trend_persona_matrix": {"mappings": []},
                "alert_threshold": 75,
            },
            ctx,
        )
        assert result.data["opportunity_alerts"] == []

    async def test_affected_personas_extracted(self) -> None:
        ctx = SkillContext(tenant_id="t1", user_role="EDITOR")
        result = await self.skill.execute(
            {
                "scored_trends": [
                    {
                        "trend_slug": "ev-growth",
                        "relevance_score": 88,
                        "recommendation": "capitalize",
                        "rationale": "Strong alignment",
                    },
                ],
                "trend_persona_matrix": {
                    "mappings": [
                        {
                            "trend_slug": "ev-growth",
                            "persona_slug": "urban-commuter",
                            "affinity_score": 0.9,
                        },
                        {
                            "trend_slug": "ev-growth",
                            "persona_slug": "fleet-manager",
                            "affinity_score": 0.3,  # Below 0.5 threshold
                        },
                    ]
                },
                "alert_threshold": 75,
            },
            ctx,
        )
        alerts = result.data["opportunity_alerts"]
        # Only urban-commuter has affinity > 0.5
        assert "urban-commuter" in alerts[0]["affected_personas"]
        assert "fleet-manager" not in alerts[0]["affected_personas"]

    async def test_alert_has_alert_id(self) -> None:
        ctx = SkillContext(tenant_id="t1", user_role="EDITOR")
        result = await self.skill.execute(
            {
                "scored_trends": [
                    {
                        "trend_slug": "test",
                        "relevance_score": 80,
                        "recommendation": "capitalize",
                        "rationale": "Test",
                    },
                ],
                "trend_persona_matrix": {"mappings": []},
                "alert_threshold": 75,
            },
            ctx,
        )
        alerts = result.data["opportunity_alerts"]
        assert alerts[0]["alert_id"]  # Non-empty UUID

    async def test_empty_input_no_alerts(self) -> None:
        ctx = SkillContext(tenant_id="t1", user_role="EDITOR")
        result = await self.skill.execute(
            {
                "scored_trends": [],
                "trend_persona_matrix": {"mappings": []},
                "alert_threshold": 75,
            },
            ctx,
        )
        assert result.success
        assert result.data["opportunity_alerts"] == []
