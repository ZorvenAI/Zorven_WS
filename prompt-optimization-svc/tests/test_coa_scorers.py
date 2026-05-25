"""Unit tests for COA scorers (US-024).

10+ tests per scorer covering perfect, partial, invalid, and edge inputs.
"""

import json

from app.scorers.coa.data_grounding import data_grounding
from app.scorers.coa.guardrail_compliance import guardrail_compliance
from app.scorers.coa.prioritization_quality import prioritization_quality
from app.scorers.coa.recommendation_actionability import recommendation_actionability


def _rec(**overrides) -> dict:
    """Build a valid recommendation dict."""
    base = {
        "action_type": "pause",
        "entity_type": "ad_set",
        "current_values": {"cpa": 45.0, "daily_budget": 100.0},
        "proposed_values": {"status": "PAUSED"},
        "rationale": "CPA of $45 exceeds target of $25 by 1.8x — pausing to save budget.",
        "priority": "high",
    }
    base.update(overrides)
    return base


def _coa_output(**overrides) -> str:
    """Build a minimal valid COA output JSON string."""
    data = {
        "recommendations": overrides.get("recommendations", [_rec()]),
        "guardrail_report": overrides.get(
            "guardrail_report",
            {
                "results": [
                    {
                        "passed": True,
                        "rule_id": "PG-01",
                        "message": "Budget within limits",
                        "action": "allow",
                    },
                    {
                        "passed": True,
                        "rule_id": "PG-05",
                        "message": "CPA kill confirmed",
                        "action": "allow",
                    },
                ],
                "all_passed": True,
                "blocked": False,
            },
        ),
        "metrics": overrides.get("metrics", {"spend": 500, "ctr": 2.1, "roas": 1.8}),
    }
    data.update({k: v for k, v in overrides.items() if k not in data})
    return json.dumps(data)


# ── recommendation_actionability tests ──


class TestRecommendationActionability:
    def test_complete_recommendation(self):
        result = recommendation_actionability(
            inputs="test", outputs=_coa_output(), expectations=None
        )
        assert result.value == 1.0

    def test_missing_action_type(self):
        out = _coa_output(recommendations=[_rec(action_type="")])
        result = recommendation_actionability(
            inputs="test", outputs=out, expectations=None
        )
        assert result.value == 0.0

    def test_missing_current_values(self):
        out = _coa_output(recommendations=[_rec(current_values="not_a_dict")])
        result = recommendation_actionability(
            inputs="test", outputs=out, expectations=None
        )
        assert result.value == 0.0

    def test_invalid_action_type(self):
        out = _coa_output(recommendations=[_rec(action_type="invalid_action")])
        result = recommendation_actionability(
            inputs="test", outputs=out, expectations=None
        )
        assert result.value == 0.0

    def test_empty_rationale(self):
        out = _coa_output(recommendations=[_rec(rationale="")])
        result = recommendation_actionability(
            inputs="test", outputs=out, expectations=None
        )
        assert result.value == 0.0

    def test_mixed_valid_invalid(self):
        out = _coa_output(recommendations=[_rec(), _rec(action_type="")])
        result = recommendation_actionability(
            inputs="test", outputs=out, expectations=None
        )
        assert result.value == 0.5

    def test_no_recommendations(self):
        out = _coa_output(recommendations=[])
        result = recommendation_actionability(
            inputs="test", outputs=out, expectations=None
        )
        assert result.value == 0.0

    def test_none_output(self):
        result = recommendation_actionability(
            inputs="test", outputs=None, expectations=None
        )
        assert result.value == 0.0

    def test_non_list_recommendations(self):
        out = _coa_output(recommendations="bad")
        result = recommendation_actionability(
            inputs="test", outputs=out, expectations=None
        )
        assert result.value == 0.0

    def test_non_dict_entries(self):
        result = recommendation_actionability(
            inputs="test",
            outputs=json.dumps({"recommendations": ["bad", 42]}),
            expectations=None,
        )
        assert result.value == 0.0

    def test_dict_input(self):
        data = json.loads(_coa_output())
        result = recommendation_actionability(
            inputs="test", outputs=data, expectations=None
        )
        assert result.value == 1.0

    def test_feedback_name(self):
        result = recommendation_actionability(
            inputs="test", outputs=_coa_output(), expectations=None
        )
        assert result.name == "recommendation_actionability"

    def test_scale_action_valid(self):
        out = _coa_output(
            recommendations=[
                _rec(action_type="scale", proposed_values={"budget_increase_pct": 20})
            ]
        )
        result = recommendation_actionability(
            inputs="test", outputs=out, expectations=None
        )
        assert result.value == 1.0


# ── guardrail_compliance tests (AC-1) ──


class TestGuardrailCompliance:
    def test_all_passed(self):
        result = guardrail_compliance(
            inputs="test", outputs=_coa_output(), expectations=None
        )
        assert result.value == 1.0

    def test_one_failure(self):
        out = _coa_output(
            guardrail_report={
                "results": [
                    {
                        "passed": True,
                        "rule_id": "PG-01",
                        "message": "OK",
                        "action": "allow",
                    },
                    {
                        "passed": False,
                        "rule_id": "PG-05",
                        "message": "Insufficient conversions",
                        "action": "block",
                    },
                ],
                "all_passed": False,
                "blocked": True,
            }
        )
        result = guardrail_compliance(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_multiple_failures(self):
        out = _coa_output(
            guardrail_report={
                "results": [
                    {
                        "passed": False,
                        "rule_id": "PG-01",
                        "message": "Over budget",
                        "action": "block",
                    },
                    {
                        "passed": False,
                        "rule_id": "PG-04",
                        "message": "Last ad set",
                        "action": "block",
                    },
                ],
                "all_passed": False,
                "blocked": True,
            }
        )
        result = guardrail_compliance(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_missing_guardrail_report(self):
        out = json.dumps({"recommendations": [_rec()]})
        result = guardrail_compliance(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_empty_results(self):
        out = _coa_output(
            guardrail_report={"results": [], "all_passed": True, "blocked": False}
        )
        result = guardrail_compliance(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_none_output(self):
        result = guardrail_compliance(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0

    def test_non_dict_results(self):
        out = _coa_output(guardrail_report={"results": "bad"})
        result = guardrail_compliance(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_feedback_lists_failed_rules(self):
        out = _coa_output(
            guardrail_report={
                "results": [
                    {
                        "passed": False,
                        "rule_id": "PG-02",
                        "message": "Budget too high",
                        "action": "block",
                    }
                ],
                "all_passed": False,
                "blocked": True,
            }
        )
        result = guardrail_compliance(inputs="test", outputs=out, expectations=None)
        assert "PG-02" in result.rationale

    def test_feedback_name(self):
        result = guardrail_compliance(
            inputs="test", outputs=_coa_output(), expectations=None
        )
        assert result.name == "guardrail_compliance"

    def test_ig_failure_ignored(self):
        """IG rules are not PG/OG — should not trigger zero-tolerance."""
        out = _coa_output(
            guardrail_report={
                "results": [
                    {
                        "passed": False,
                        "rule_id": "IG-03",
                        "message": "Low spend",
                        "action": "warn",
                    },
                    {
                        "passed": True,
                        "rule_id": "PG-01",
                        "message": "OK",
                        "action": "allow",
                    },
                ],
                "all_passed": False,
                "blocked": False,
            }
        )
        result = guardrail_compliance(inputs="test", outputs=out, expectations=None)
        assert result.value == 1.0  # IG failure ignored, PG passed

    def test_non_dict_result_entries_skipped(self):
        out = _coa_output(
            guardrail_report={
                "results": [
                    "bad",
                    {
                        "passed": True,
                        "rule_id": "PG-01",
                        "message": "OK",
                        "action": "allow",
                    },
                ],
                "all_passed": True,
                "blocked": False,
            }
        )
        result = guardrail_compliance(inputs="test", outputs=out, expectations=None)
        assert result.value == 1.0


# ── data_grounding tests (AC-2) ──


class TestDataGrounding:
    def test_fully_grounded(self):
        result = data_grounding(inputs="test", outputs=_coa_output(), expectations=None)
        assert result.value == 1.0

    def test_missing_current_values(self):
        out = _coa_output(recommendations=[_rec(current_values=None)])
        result = data_grounding(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_empty_current_values(self):
        out = _coa_output(recommendations=[_rec(current_values={})])
        result = data_grounding(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_no_numeric_metrics(self):
        out = _coa_output(recommendations=[_rec(current_values={"status": "ACTIVE"})])
        result = data_grounding(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_metrics_but_no_rationale_citations(self):
        out = _coa_output(
            recommendations=[_rec(rationale="This ad set should be paused.")]
        )
        result = data_grounding(inputs="test", outputs=out, expectations=None)
        # Has metrics but rationale lacks numbers — partial credit
        assert 0.0 < result.value < 1.0

    def test_mixed_quality(self):
        out = _coa_output(
            recommendations=[
                _rec(),  # fully grounded
                _rec(current_values={}, rationale="no data"),  # not grounded
            ]
        )
        result = data_grounding(inputs="test", outputs=out, expectations=None)
        assert 0.0 < result.value < 1.0

    def test_none_output(self):
        result = data_grounding(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0

    def test_no_recommendations(self):
        out = _coa_output(recommendations=[])
        result = data_grounding(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_feedback_name(self):
        result = data_grounding(inputs="test", outputs=_coa_output(), expectations=None)
        assert result.name == "data_grounding"

    def test_non_list_recommendations(self):
        out = json.dumps({"recommendations": "bad"})
        result = data_grounding(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_rationale_with_matching_numbers(self):
        out = _coa_output(
            recommendations=[
                _rec(rationale="CPA is $45.0, which exceeds our $100 daily budget.")
            ]
        )
        result = data_grounding(inputs="test", outputs=out, expectations=None)
        assert result.value == 1.0

    def test_rationale_with_fabricated_numbers(self):
        """AC-2: rationale citing numbers not in current_values gets partial credit."""
        out = _coa_output(
            recommendations=[
                _rec(
                    current_values={"cpa": 45.0, "daily_budget": 100.0},
                    rationale="CPA is $999, which is terrible.",
                )
            ]
        )
        result = data_grounding(inputs="test", outputs=out, expectations=None)
        # 999 doesn't match any metric — partial credit only
        assert result.value < 1.0


# ── prioritization_quality tests (AC-3) ──


class TestPrioritizationQuality:
    def test_pause_before_scale(self):
        out = _coa_output(
            recommendations=[
                _rec(action_type="pause", priority="high"),
                _rec(action_type="scale", priority="medium"),
            ]
        )
        result = prioritization_quality(inputs="test", outputs=out, expectations=None)
        assert result.value == 1.0

    def test_scale_before_pause(self):
        out = _coa_output(
            recommendations=[
                _rec(action_type="scale", priority="medium"),
                _rec(action_type="pause", priority="high"),
            ]
        )
        result = prioritization_quality(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_high_before_medium(self):
        out = _coa_output(
            recommendations=[
                _rec(priority="high"),
                _rec(action_type="scale", priority="medium"),
            ]
        )
        result = prioritization_quality(inputs="test", outputs=out, expectations=None)
        assert result.value == 1.0

    def test_only_pause(self):
        out = _coa_output(
            recommendations=[_rec(action_type="pause"), _rec(action_type="pause")]
        )
        result = prioritization_quality(inputs="test", outputs=out, expectations=None)
        assert result.value == 1.0

    def test_only_scale(self):
        out = _coa_output(
            recommendations=[
                _rec(action_type="scale"),
                _rec(action_type="adjust_budget"),
            ]
        )
        result = prioritization_quality(inputs="test", outputs=out, expectations=None)
        assert result.value == 1.0

    def test_correct_mixed_order(self):
        out = _coa_output(
            recommendations=[
                _rec(action_type="pause", priority="high"),
                _rec(action_type="pause", priority="high"),
                _rec(action_type="scale", priority="medium"),
            ]
        )
        result = prioritization_quality(inputs="test", outputs=out, expectations=None)
        assert result.value == 1.0

    def test_wrong_mixed_order(self):
        out = _coa_output(
            recommendations=[
                _rec(action_type="scale", priority="medium"),
                _rec(action_type="pause", priority="high"),
                _rec(action_type="scale", priority="medium"),
            ]
        )
        result = prioritization_quality(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_none_output(self):
        result = prioritization_quality(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0

    def test_no_recommendations(self):
        out = _coa_output(recommendations=[])
        result = prioritization_quality(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_single_recommendation(self):
        out = _coa_output(recommendations=[_rec()])
        result = prioritization_quality(inputs="test", outputs=out, expectations=None)
        assert result.value == 1.0

    def test_feedback_name(self):
        result = prioritization_quality(
            inputs="test", outputs=_coa_output(), expectations=None
        )
        assert result.name == "prioritization_quality"


# ── Scorer conformance ──


class TestCoaScorerConformance:
    def test_all_are_scorer_instances(self):
        from mlflow.genai.scorers import Scorer

        for s in [
            recommendation_actionability,
            guardrail_compliance,
            data_grounding,
            prioritization_quality,
        ]:
            assert isinstance(s, Scorer), f"{s.name} is not a Scorer"

    def test_all_accept_keyword_args(self):
        for s in [
            recommendation_actionability,
            guardrail_compliance,
            data_grounding,
            prioritization_quality,
        ]:
            result = s(inputs="test", outputs=_coa_output(), expectations=None)
            assert result is not None
