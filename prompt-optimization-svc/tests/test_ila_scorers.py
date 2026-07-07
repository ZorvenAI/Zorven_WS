"""Unit tests for ILA scorers (US-026).

10+ tests per scorer covering perfect, partial, invalid, and edge inputs.
"""

import json

from app.scorers.ila.learning_depth import learning_depth
from app.scorers.ila.meta_policy import meta_policy


def _learning(**overrides) -> dict:
    """Build a valid learning dict."""
    base = {
        "confidence": 75,
        "impact": "HIGH",
        "insight": "CPA decreased after audience narrowing.",
    }
    base.update(overrides)
    return base


def _ila_output(**overrides) -> str:
    """Build a minimal valid ILA output JSON string."""
    data = {
        "learnings": overrides.get(
            "learnings",
            [_learning()],
        ),
        "contradictions": overrides.get("contradictions", []),
    }
    data.update({k: v for k, v in overrides.items() if k not in data})
    return json.dumps(data)


def _meta_output(**overrides) -> str:
    """Build a minimal valid meta_policy output JSON string."""
    data = {
        "plan_warnings": overrides.get("plan_warnings", ["minor warning"]),
        "published_campaign": overrides.get(
            "published_campaign", {"id": "camp_123", "status": "ACTIVE"}
        ),
        "sandbox_mode": overrides.get("sandbox_mode", False),
    }
    data.update({k: v for k, v in overrides.items() if k not in data})
    return json.dumps(data)


# ── learning_depth tests ──


class TestLearningDepth:
    def test_single_confident_learning(self):
        result = learning_depth(inputs="test", outputs=_ila_output(), expectations=None)
        assert result.value == 1.0

    def test_all_confident_learnings(self):
        out = _ila_output(
            learnings=[
                _learning(confidence=80, impact="HIGH"),
                _learning(confidence=60, impact="MEDIUM"),
                _learning(confidence=50, impact="LOW"),
            ]
        )
        result = learning_depth(inputs="test", outputs=out, expectations=None)
        assert result.value == 1.0

    def test_mixed_confidence(self):
        out = _ila_output(
            learnings=[
                _learning(confidence=80, impact="HIGH"),
                _learning(confidence=30, impact="LOW"),
            ]
        )
        result = learning_depth(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.5

    def test_all_low_confidence(self):
        out = _ila_output(
            learnings=[
                _learning(confidence=10, impact="HIGH"),
                _learning(confidence=20, impact="MEDIUM"),
            ]
        )
        result = learning_depth(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_empty_learnings(self):
        out = _ila_output(learnings=[])
        result = learning_depth(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_missing_learnings_field(self):
        out = json.dumps({"contradictions": []})
        result = learning_depth(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_none_output(self):
        result = learning_depth(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0

    def test_malformed_json(self):
        result = learning_depth(
            inputs="test", outputs="not json at all", expectations=None
        )
        assert result.value == 0.0

    def test_non_dict_learnings(self):
        out = json.dumps({"learnings": "not_a_list"})
        result = learning_depth(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_non_dict_entries_in_learnings(self):
        out = _ila_output(learnings=["bad", 42, None])
        result = learning_depth(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0
        assert "No valid learning dicts" in result.rationale

    def test_invalid_impact_value(self):
        out = _ila_output(learnings=[_learning(confidence=80, impact="INVALID")])
        result = learning_depth(inputs="test", outputs=out, expectations=None)
        # Valid dict but impact not in {HIGH, MEDIUM, LOW} so not counted
        assert result.value == 0.0

    def test_non_int_confidence(self):
        out = _ila_output(learnings=[_learning(confidence="high", impact="HIGH")])
        result = learning_depth(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_contradiction_bonus_noted(self):
        out = _ila_output(
            learnings=[_learning()],
            contradictions=[{"old": "A", "new": "B"}],
        )
        result = learning_depth(inputs="test", outputs=out, expectations=None)
        assert result.value == 1.0
        assert "Contradictions detected" in result.rationale

    def test_no_contradictions_no_bonus(self):
        out = _ila_output(learnings=[_learning()], contradictions=[])
        result = learning_depth(inputs="test", outputs=out, expectations=None)
        assert "Contradictions detected" not in result.rationale

    def test_dict_input_accepted(self):
        data = json.loads(_ila_output())
        result = learning_depth(inputs="test", outputs=data, expectations=None)
        assert result.value == 1.0

    def test_feedback_name(self):
        result = learning_depth(inputs="test", outputs=_ila_output(), expectations=None)
        assert result.name == "learning_depth"

    def test_boundary_confidence_49(self):
        out = _ila_output(learnings=[_learning(confidence=49, impact="HIGH")])
        result = learning_depth(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_boundary_confidence_50(self):
        out = _ila_output(learnings=[_learning(confidence=50, impact="HIGH")])
        result = learning_depth(inputs="test", outputs=out, expectations=None)
        assert result.value == 1.0

    def test_score_rounded(self):
        out = _ila_output(
            learnings=[
                _learning(confidence=80, impact="HIGH"),
                _learning(confidence=80, impact="MEDIUM"),
                _learning(confidence=10, impact="LOW"),
            ]
        )
        result = learning_depth(inputs="test", outputs=out, expectations=None)
        assert result.value == round(2 / 3, 4)


# ── meta_policy tests ──


class TestMetaPolicy:
    def test_all_checks_pass(self):
        result = meta_policy(inputs="test", outputs=_meta_output(), expectations=None)
        assert result.value == 1.0

    def test_zero_warnings_pass(self):
        out = _meta_output(plan_warnings=[])
        result = meta_policy(inputs="test", outputs=out, expectations=None)
        assert result.value == 1.0

    def test_two_warnings_pass(self):
        out = _meta_output(plan_warnings=["w1", "w2"])
        result = meta_policy(inputs="test", outputs=out, expectations=None)
        assert result.value == 1.0

    def test_three_warnings_fail(self):
        out = _meta_output(plan_warnings=["w1", "w2", "w3"])
        result = meta_policy(inputs="test", outputs=out, expectations=None)
        # plan_warnings fails, published_campaign + sandbox_mode pass = 2/3
        assert result.value == round(2 / 3, 4)

    def test_missing_published_campaign(self):
        out = json.dumps(
            {
                "plan_warnings": [],
                "sandbox_mode": True,
            }
        )
        result = meta_policy(inputs="test", outputs=out, expectations=None)
        assert result.value == round(2 / 3, 4)

    def test_published_campaign_not_dict(self):
        out = _meta_output(published_campaign="not_a_dict")
        result = meta_policy(inputs="test", outputs=out, expectations=None)
        assert result.value == round(2 / 3, 4)

    def test_sandbox_mode_not_bool(self):
        out = _meta_output(sandbox_mode="yes")
        result = meta_policy(inputs="test", outputs=out, expectations=None)
        assert result.value == round(2 / 3, 4)

    def test_sandbox_mode_true_is_valid(self):
        out = _meta_output(sandbox_mode=True)
        result = meta_policy(inputs="test", outputs=out, expectations=None)
        assert result.value == 1.0

    def test_all_checks_fail(self):
        out = json.dumps(
            {
                "plan_warnings": ["w1", "w2", "w3", "w4"],
                "published_campaign": "bad",
                "sandbox_mode": "not_bool",
            }
        )
        result = meta_policy(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_none_output(self):
        result = meta_policy(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0

    def test_malformed_json(self):
        result = meta_policy(inputs="test", outputs="not json", expectations=None)
        assert result.value == 0.0

    def test_empty_dict(self):
        result = meta_policy(inputs="test", outputs=json.dumps({}), expectations=None)
        assert result.value == 0.0

    def test_dict_input_accepted(self):
        data = json.loads(_meta_output())
        result = meta_policy(inputs="test", outputs=data, expectations=None)
        assert result.value == 1.0

    def test_feedback_name(self):
        result = meta_policy(inputs="test", outputs=_meta_output(), expectations=None)
        assert result.name == "meta_policy"

    def test_rationale_lists_details(self):
        result = meta_policy(inputs="test", outputs=_meta_output(), expectations=None)
        assert "3/3 checks passed" in result.rationale

    def test_plan_warnings_not_list(self):
        out = _meta_output()
        data = json.loads(out)
        data["plan_warnings"] = "not_a_list"
        result = meta_policy(inputs="test", outputs=json.dumps(data), expectations=None)
        # plan_warnings fails, other two pass = 2/3
        assert result.value == round(2 / 3, 4)


# ── Scorer conformance ──


class TestIlaScorerConformance:
    def test_all_are_scorer_instances(self):
        from mlflow.genai.scorers import Scorer

        for s in [learning_depth, meta_policy]:
            assert isinstance(s, Scorer), f"{s.name} is not a Scorer"

    def test_all_accept_keyword_args(self):
        for s, out in [
            (learning_depth, _ila_output()),
            (meta_policy, _meta_output()),
        ]:
            result = s(inputs="test", outputs=out, expectations=None)
            assert result is not None
