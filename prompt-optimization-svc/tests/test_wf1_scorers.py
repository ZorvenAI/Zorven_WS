"""Unit tests for WF1 discovery & research scorers.

10+ tests per scorer covering perfect, partial, invalid, and edge inputs.
"""

import json

from app.scorers.wf1.market_completeness import market_completeness
from app.scorers.wf1.competitor_accuracy import competitor_accuracy
from app.scorers.wf1.persona_quality import persona_quality
from app.scorers.wf1.trend_relevance import trend_relevance
from app.scorers.wf1.voca_sentiment import voca_sentiment


# ── Helper builders ──


def _mra_output(**overrides) -> str:
    """Build a minimal valid MRA (market research) output JSON string."""
    data = {
        "market_sizing": overrides.get(
            "market_sizing",
            {"TAM": 1_000_000, "SAM": 500_000, "SOM": 100_000},
        ),
        "competitive_landscape": overrides.get(
            "competitive_landscape",
            [{"name": "Competitor A"}, {"name": "Competitor B"}],
        ),
        "industry_trends": overrides.get(
            "industry_trends",
            ["AI adoption", "Cloud migration"],
        ),
        "findings": overrides.get(
            "findings",
            ["Key insight 1", "Key insight 2"],
        ),
    }
    data.update({k: v for k, v in overrides.items() if k not in data})
    return json.dumps(data)


def _cia_output(**overrides) -> str:
    """Build a minimal valid CIA (competitor intel) output JSON string."""
    data = {
        "competitors": overrides.get(
            "competitors",
            [
                {"name": "Rival A", "market_position": "leader"},
                {"name": "Rival B", "market_position": "challenger"},
            ],
        ),
        "positioning_gaps": overrides.get(
            "positioning_gaps",
            ["gap 1", "gap 2"],
        ),
        "benchmarking_report": overrides.get(
            "benchmarking_report",
            {"metric_a": 85, "metric_b": 90},
        ),
    }
    data.update({k: v for k, v in overrides.items() if k not in data})
    return json.dumps(data)


def _apa_output(**overrides) -> str:
    """Build a minimal valid APA (audience persona) output JSON string."""
    data = {
        "personas": overrides.get(
            "personas",
            [
                {
                    "name": "Tech Enthusiast",
                    "demographics": {"age": "25-34", "gender": "mixed"},
                    "psychographics": {"values": ["innovation"]},
                },
                {
                    "name": "Budget Buyer",
                    "demographics": {"age": "35-44", "income": "medium"},
                    "psychographics": {"values": ["value"]},
                },
            ],
        ),
        "journey_maps": overrides.get(
            "journey_maps",
            [{"stage": "awareness", "touchpoints": ["social", "search"]}],
        ),
    }
    data.update({k: v for k, v in overrides.items() if k not in data})
    return json.dumps(data)


def _tcia_output(**overrides) -> str:
    """Build a minimal valid TCIA (trend cultural) output JSON string."""
    data = {
        "trend_report": overrides.get(
            "trend_report",
            {
                "trend_scorecard": [
                    {"trend": "AI", "relevance_score": 95},
                    {"trend": "Sustainability", "relevance_score": 80},
                    {"trend": "Remote work", "relevance_score": 70},
                ]
            },
        ),
        "opportunity_alerts": overrides.get(
            "opportunity_alerts",
            ["Alert 1: AI opportunity", "Alert 2: Green market"],
        ),
    }
    data.update({k: v for k, v in overrides.items() if k not in data})
    return json.dumps(data)


def _voca_output(**overrides) -> str:
    """Build a minimal valid VoCA (voice of customer) output JSON string."""
    data = {
        "sentiment": overrides.get(
            "sentiment",
            {"overall_sentiment": "positive", "confidence": 0.92},
        ),
        "nps_analysis": overrides.get(
            "nps_analysis",
            {"score": 45, "promoters": 60, "detractors": 15},
        ),
        "pain_point_priority_matrix": overrides.get(
            "pain_point_priority_matrix",
            {"high": ["pricing"], "medium": ["onboarding"]},
        ),
    }
    data.update({k: v for k, v in overrides.items() if k not in data})
    return json.dumps(data)


# ── market_completeness tests ──


class TestMarketCompleteness:
    def test_valid_complete_output(self):
        result = market_completeness(
            inputs="test", outputs=_mra_output(), expectations=None
        )
        assert result.value == 1.0

    def test_missing_market_sizing(self):
        out = _mra_output(market_sizing=None)
        result = market_completeness(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.75

    def test_missing_competitive_landscape(self):
        out = _mra_output(competitive_landscape=[])
        result = market_completeness(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.75

    def test_missing_industry_trends(self):
        out = _mra_output(industry_trends=[])
        result = market_completeness(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.75

    def test_missing_findings(self):
        out = _mra_output(findings=[])
        result = market_completeness(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.75

    def test_none_output(self):
        result = market_completeness(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0

    def test_invalid_json(self):
        result = market_completeness(
            inputs="test", outputs="not json {{", expectations=None
        )
        assert result.value == 0.0

    def test_dict_input(self):
        data = json.loads(_mra_output())
        result = market_completeness(inputs="test", outputs=data, expectations=None)
        assert result.value == 1.0

    def test_market_sizing_not_dict(self):
        out = _mra_output(market_sizing="big market")
        result = market_completeness(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.75

    def test_market_sizing_missing_tam(self):
        out = _mra_output(market_sizing={"SAM": 500_000, "SOM": 100_000})
        result = market_completeness(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.75

    def test_competitive_landscape_not_list(self):
        out = _mra_output(competitive_landscape="some text")
        result = market_completeness(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.75

    def test_all_fields_missing(self):
        result = market_completeness(
            inputs="test", outputs=json.dumps({}), expectations=None
        )
        assert result.value == 0.0

    def test_feedback_name(self):
        result = market_completeness(
            inputs="test", outputs=_mra_output(), expectations=None
        )
        assert result.name == "market_completeness"

    def test_partial_two_fields(self):
        out = _mra_output(market_sizing=None, competitive_landscape=[])
        result = market_completeness(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.5


# ── competitor_accuracy tests ──


class TestCompetitorAccuracy:
    def test_valid_complete_output(self):
        result = competitor_accuracy(
            inputs="test", outputs=_cia_output(), expectations=None
        )
        assert result.value == 1.0

    def test_missing_competitors(self):
        out = _cia_output(competitors=[])
        result = competitor_accuracy(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_competitors_without_market_position(self):
        out = _cia_output(
            competitors=[
                {"name": "Rival A"},
                {"name": "Rival B", "market_position": "leader"},
            ]
        )
        result = competitor_accuracy(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_all_competitors_missing_market_position(self):
        out = _cia_output(competitors=[{"name": "A"}, {"name": "B"}])
        result = competitor_accuracy(inputs="test", outputs=out, expectations=None)
        # competitors present but none have market_position -> that check fails
        assert result.value < 1.0

    def test_missing_positioning_gaps(self):
        out = _cia_output(positioning_gaps=[])
        result = competitor_accuracy(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_missing_benchmarking_report(self):
        out = _cia_output(benchmarking_report=None)
        result = competitor_accuracy(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_none_output(self):
        result = competitor_accuracy(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0

    def test_invalid_json(self):
        result = competitor_accuracy(
            inputs="test", outputs="bad json {{{", expectations=None
        )
        assert result.value == 0.0

    def test_dict_input(self):
        data = json.loads(_cia_output())
        result = competitor_accuracy(inputs="test", outputs=data, expectations=None)
        assert result.value == 1.0

    def test_competitors_not_list(self):
        out = _cia_output(competitors="not a list")
        result = competitor_accuracy(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_benchmarking_report_not_dict(self):
        out = _cia_output(benchmarking_report="just text")
        result = competitor_accuracy(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_feedback_name(self):
        result = competitor_accuracy(
            inputs="test", outputs=_cia_output(), expectations=None
        )
        assert result.name == "competitor_accuracy"

    def test_non_dict_competitor_entries(self):
        out = _cia_output(competitors=["string entry", 42])
        result = competitor_accuracy(inputs="test", outputs=out, expectations=None)
        # entries are not dicts, so none have market_position
        assert result.value < 1.0

    def test_all_fields_missing(self):
        result = competitor_accuracy(
            inputs="test", outputs=json.dumps({}), expectations=None
        )
        assert result.value == 0.0

    def test_empty_benchmarking_report_dict(self):
        """Empty dict is still a dict -- should pass."""
        out = _cia_output(benchmarking_report={})
        result = competitor_accuracy(inputs="test", outputs=out, expectations=None)
        # competitors + positioning_gaps pass, benchmarking_report is {} -> dict check passes
        assert result.value == 1.0


# ── persona_quality tests ──


class TestPersonaQuality:
    def test_valid_complete_output(self):
        result = persona_quality(
            inputs="test", outputs=_apa_output(), expectations=None
        )
        assert result.value == 1.0

    def test_missing_personas(self):
        out = _apa_output(personas=[])
        result = persona_quality(inputs="test", outputs=out, expectations=None)
        # persona_score=0 (empty), journey_maps present -> 0.5
        assert result.value == 0.5

    def test_missing_journey_maps(self):
        out = _apa_output(journey_maps=[])
        result = persona_quality(inputs="test", outputs=out, expectations=None)
        # personas complete -> 0.5, journey absent -> 0
        assert result.value == 0.5

    def test_persona_missing_demographics(self):
        out = _apa_output(
            personas=[
                {
                    "name": "Incomplete",
                    "psychographics": {"values": ["speed"]},
                }
            ]
        )
        result = persona_quality(inputs="test", outputs=out, expectations=None)
        # 0 complete / 1 -> persona_score=0 -> 0 * 0.5 + journey 0.5
        assert result.value == 0.5

    def test_persona_missing_psychographics(self):
        out = _apa_output(
            personas=[
                {
                    "name": "Incomplete",
                    "demographics": {"age": "25-34"},
                }
            ]
        )
        result = persona_quality(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.5

    def test_mixed_persona_quality(self):
        out = _apa_output(
            personas=[
                {
                    "name": "Complete",
                    "demographics": {"age": "25-34"},
                    "psychographics": {"values": ["innovation"]},
                },
                {
                    "name": "Incomplete",
                    "demographics": {"age": "35-44"},
                    # missing psychographics
                },
            ]
        )
        result = persona_quality(inputs="test", outputs=out, expectations=None)
        # 1/2 complete -> 0.5 * 0.5 = 0.25 + journey 0.5 = 0.75
        assert result.value == 0.75

    def test_none_output(self):
        result = persona_quality(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0

    def test_invalid_json(self):
        result = persona_quality(
            inputs="test", outputs="not valid json", expectations=None
        )
        assert result.value == 0.0

    def test_dict_input(self):
        data = json.loads(_apa_output())
        result = persona_quality(inputs="test", outputs=data, expectations=None)
        assert result.value == 1.0

    def test_personas_not_list(self):
        out = _apa_output(personas="not a list")
        result = persona_quality(inputs="test", outputs=out, expectations=None)
        # persona_score=0, journey present -> 0.5
        assert result.value == 0.5

    def test_journey_maps_not_list(self):
        out = _apa_output(journey_maps="not a list")
        result = persona_quality(inputs="test", outputs=out, expectations=None)
        # personas complete -> 0.5, journey not list -> 0
        assert result.value == 0.5

    def test_non_dict_persona_entries(self):
        out = _apa_output(personas=["string", 42, None])
        result = persona_quality(inputs="test", outputs=out, expectations=None)
        # 0 complete / 3 -> persona_score=0
        assert result.value == 0.5

    def test_feedback_name(self):
        result = persona_quality(
            inputs="test", outputs=_apa_output(), expectations=None
        )
        assert result.name == "persona_quality"

    def test_all_missing(self):
        result = persona_quality(
            inputs="test", outputs=json.dumps({}), expectations=None
        )
        assert result.value == 0.0

    def test_demographics_not_dict(self):
        out = _apa_output(
            personas=[
                {
                    "name": "Bad",
                    "demographics": "age 25-34",
                    "psychographics": {"values": ["x"]},
                }
            ]
        )
        result = persona_quality(inputs="test", outputs=out, expectations=None)
        # demographics not dict -> incomplete
        assert result.value == 0.5


# ── trend_relevance tests ──


class TestTrendRelevance:
    def test_valid_complete_output(self):
        result = trend_relevance(
            inputs="test", outputs=_tcia_output(), expectations=None
        )
        assert result.value == 1.0

    def test_missing_trend_report(self):
        out = json.dumps({"opportunity_alerts": ["Alert 1"]})
        result = trend_relevance(inputs="test", outputs=out, expectations=None)
        # trend_score=0 -> 0*0.8 + 1*0.2 = 0.2
        assert result.value == 0.2

    def test_missing_opportunity_alerts(self):
        out = _tcia_output(opportunity_alerts=[])
        result = trend_relevance(inputs="test", outputs=out, expectations=None)
        # trend_score=1.0 -> 1*0.8 + 0*0.2 = 0.8
        assert result.value == 0.8

    def test_empty_scorecard(self):
        out = _tcia_output(trend_report={"trend_scorecard": []})
        result = trend_relevance(inputs="test", outputs=out, expectations=None)
        # scorecard empty -> trend_score=0 -> 0*0.8 + 0.2 = 0.2
        assert result.value == 0.2

    def test_invalid_relevance_scores(self):
        out = _tcia_output(
            trend_report={
                "trend_scorecard": [
                    {"trend": "AI", "relevance_score": -5},
                    {"trend": "Cloud", "relevance_score": 150},
                ]
            }
        )
        result = trend_relevance(inputs="test", outputs=out, expectations=None)
        # Both out of range -> 0/2 -> trend_score=0
        assert result.value == 0.2

    def test_mixed_valid_invalid_scores(self):
        out = _tcia_output(
            trend_report={
                "trend_scorecard": [
                    {"trend": "AI", "relevance_score": 85},
                    {"trend": "Cloud", "relevance_score": -10},
                ]
            }
        )
        result = trend_relevance(inputs="test", outputs=out, expectations=None)
        # 1/2 valid -> 0.5 * 0.8 + 0.2 = 0.6
        assert result.value == 0.6

    def test_none_output(self):
        result = trend_relevance(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0

    def test_invalid_json(self):
        result = trend_relevance(
            inputs="test", outputs="broken json {{", expectations=None
        )
        assert result.value == 0.0

    def test_dict_input(self):
        data = json.loads(_tcia_output())
        result = trend_relevance(inputs="test", outputs=data, expectations=None)
        assert result.value == 1.0

    def test_trend_report_not_dict(self):
        out = _tcia_output(trend_report="not a dict")
        result = trend_relevance(inputs="test", outputs=out, expectations=None)
        # trend_report not dict -> trend_score=0
        assert result.value == 0.2

    def test_scorecard_not_list(self):
        out = _tcia_output(trend_report={"trend_scorecard": "bad"})
        result = trend_relevance(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.2

    def test_non_dict_scorecard_entries(self):
        out = _tcia_output(trend_report={"trend_scorecard": ["string", 42, None]})
        result = trend_relevance(inputs="test", outputs=out, expectations=None)
        # 0/3 valid -> trend_score=0
        assert result.value == 0.2

    def test_feedback_name(self):
        result = trend_relevance(
            inputs="test", outputs=_tcia_output(), expectations=None
        )
        assert result.name == "trend_relevance"

    def test_relevance_score_non_numeric(self):
        out = _tcia_output(
            trend_report={
                "trend_scorecard": [
                    {"trend": "AI", "relevance_score": "high"},
                ]
            }
        )
        result = trend_relevance(inputs="test", outputs=out, expectations=None)
        # string not numeric -> 0/1 valid
        assert result.value == 0.2

    def test_boundary_relevance_scores(self):
        out = _tcia_output(
            trend_report={
                "trend_scorecard": [
                    {"trend": "A", "relevance_score": 0},
                    {"trend": "B", "relevance_score": 100},
                ]
            }
        )
        result = trend_relevance(inputs="test", outputs=out, expectations=None)
        # Both valid (0 and 100 are within range)
        assert result.value == 1.0


# ── voca_sentiment tests ──


class TestVocaSentiment:
    def test_valid_complete_output(self):
        result = voca_sentiment(
            inputs="test", outputs=_voca_output(), expectations=None
        )
        assert result.value == 1.0

    def test_missing_sentiment(self):
        out = _voca_output(sentiment=None)
        result = voca_sentiment(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_sentiment_missing_overall(self):
        out = _voca_output(sentiment={"confidence": 0.9})
        result = voca_sentiment(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_missing_nps_analysis(self):
        out = _voca_output(nps_analysis=None)
        result = voca_sentiment(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_missing_pain_point_matrix(self):
        out = _voca_output(pain_point_priority_matrix=None)
        result = voca_sentiment(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_empty_pain_point_list(self):
        out = _voca_output(pain_point_priority_matrix=[])
        result = voca_sentiment(inputs="test", outputs=out, expectations=None)
        # empty list does not count as present
        assert result.value < 1.0

    def test_pain_point_as_list(self):
        out = _voca_output(
            pain_point_priority_matrix=[{"issue": "pricing", "priority": "high"}]
        )
        result = voca_sentiment(inputs="test", outputs=out, expectations=None)
        assert result.value == 1.0

    def test_none_output(self):
        result = voca_sentiment(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0

    def test_invalid_json(self):
        result = voca_sentiment(
            inputs="test", outputs="not json at all", expectations=None
        )
        assert result.value == 0.0

    def test_dict_input(self):
        data = json.loads(_voca_output())
        result = voca_sentiment(inputs="test", outputs=data, expectations=None)
        assert result.value == 1.0

    def test_sentiment_not_dict(self):
        out = _voca_output(sentiment="positive")
        result = voca_sentiment(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_nps_analysis_not_dict(self):
        out = _voca_output(nps_analysis=[1, 2, 3])
        result = voca_sentiment(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_feedback_name(self):
        result = voca_sentiment(
            inputs="test", outputs=_voca_output(), expectations=None
        )
        assert result.name == "voca_sentiment"

    def test_all_fields_missing(self):
        result = voca_sentiment(
            inputs="test", outputs=json.dumps({}), expectations=None
        )
        assert result.value == 0.0

    def test_pain_point_matrix_invalid_type(self):
        out = _voca_output(pain_point_priority_matrix=42)
        result = voca_sentiment(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0


# ── Scorer conformance ──


class TestWf1ScorerConformance:
    def test_all_are_scorer_instances(self):
        from mlflow.genai.scorers import Scorer

        for s in [
            market_completeness,
            competitor_accuracy,
            persona_quality,
            trend_relevance,
            voca_sentiment,
        ]:
            assert isinstance(s, Scorer), f"{s.name} is not a Scorer"

    def test_all_accept_keyword_args(self):
        pairs = [
            (market_completeness, _mra_output()),
            (competitor_accuracy, _cia_output()),
            (persona_quality, _apa_output()),
            (trend_relevance, _tcia_output()),
            (voca_sentiment, _voca_output()),
        ]
        for s, out in pairs:
            result = s(inputs="test", outputs=out, expectations=None)
            assert result is not None, f"{s.name} returned None"

    def test_all_return_zero_on_none(self):
        for s in [
            market_completeness,
            competitor_accuracy,
            persona_quality,
            trend_relevance,
            voca_sentiment,
        ]:
            result = s(inputs="test", outputs=None, expectations=None)
            assert result.value == 0.0, f"{s.name} did not return 0.0 for None"

    def test_all_handle_invalid_json(self):
        for s in [
            market_completeness,
            competitor_accuracy,
            persona_quality,
            trend_relevance,
            voca_sentiment,
        ]:
            result = s(inputs="test", outputs="{{bad", expectations=None)
            assert result.value == 0.0, f"{s.name} did not return 0.0 for bad JSON"
