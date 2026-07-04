"""Unit tests for CAA scorers (US-023).

10+ tests per scorer covering perfect, partial, invalid, and edge inputs.
"""

import json

from app.scorers.caa.budget_rationality import budget_rationality
from app.scorers.caa.funnel_coverage import funnel_coverage
from app.scorers.caa.structure_validity import structure_validity
from app.scorers.caa.targeting_quality import targeting_quality


def _caa_output(**overrides) -> str:
    """Build a minimal valid CAA output JSON string."""
    data = {
        "blueprint": overrides.get(
            "blueprint",
            {
                "campaign_name": "Test Campaign",
                "campaign_objective": "AWARENESS",
                "ad_sets": [
                    {
                        "name": "TOFU - Broad",
                        "funnel_stage": "tofu",
                        "targeting": {"demographics": {"age_min": 18}},
                        "daily_budget": 50.0,
                    },
                    {
                        "name": "BOFU - Converters",
                        "funnel_stage": "bofu",
                        "targeting": {"demographics": {"age_min": 25}},
                        "daily_budget": 50.0,
                    },
                ],
            },
        ),
        "funnel_map": overrides.get(
            "funnel_map",
            {
                "stages": [
                    {"stage": "tofu", "budget_pct": 50},
                    {"stage": "mofu", "budget_pct": 25},
                    {"stage": "bofu", "budget_pct": 20},
                    {"stage": "retention", "budget_pct": 5},
                ]
            },
        ),
        "targeting_specs": overrides.get(
            "targeting_specs",
            [
                {
                    "ad_set_name": "TOFU",
                    "demographics": {"age_min": 18, "age_max": 65, "genders": ["ALL"]},
                    "interests": ["Technology", "Software"],
                    "custom_audiences": ["repeat_buyers"],
                    "lookalike_audiences": [],
                },
                {
                    "ad_set_name": "BOFU",
                    "demographics": {"age_min": 25, "age_max": 55, "genders": ["ALL"]},
                    "interests": ["SaaS", "Startups"],
                    "custom_audiences": [],
                    "lookalike_audiences": ["lookalike_buyers_1pct"],
                },
            ],
        ),
        "placement_budget": overrides.get("placement_budget", {}),
    }
    data.update({k: v for k, v in overrides.items() if k not in data})
    return json.dumps(data)


# ── structure_validity tests (AC-1) ──


class TestStructureValidity:
    def test_valid_blueprint(self):
        result = structure_validity(
            inputs="test", outputs=_caa_output(), expectations=None
        )
        assert result.value == 1.0

    def test_missing_blueprint(self):
        result = structure_validity(
            inputs="test", outputs='{"other": 1}', expectations=None
        )
        assert result.value == 0.0

    def test_missing_ad_sets(self):
        bp = {"campaign_name": "Test", "campaign_objective": "AWARENESS"}
        result = structure_validity(
            inputs="test", outputs=_caa_output(blueprint=bp), expectations=None
        )
        assert result.value < 1.0

    def test_empty_ad_sets(self):
        bp = {"campaign_name": "Test", "campaign_objective": "AWARENESS", "ad_sets": []}
        result = structure_validity(
            inputs="test", outputs=_caa_output(blueprint=bp), expectations=None
        )
        assert result.value < 1.0

    def test_ad_set_missing_name(self):
        bp = {
            "campaign_name": "Test",
            "campaign_objective": "AWARENESS",
            "ad_sets": [{"funnel_stage": "tofu", "targeting": {}}],
        }
        result = structure_validity(
            inputs="test", outputs=_caa_output(blueprint=bp), expectations=None
        )
        assert result.value < 1.0

    def test_ad_set_missing_targeting(self):
        bp = {
            "campaign_name": "Test",
            "campaign_objective": "AWARENESS",
            "ad_sets": [{"name": "TOFU", "funnel_stage": "tofu"}],
        }
        result = structure_validity(
            inputs="test", outputs=_caa_output(blueprint=bp), expectations=None
        )
        assert result.value < 1.0

    def test_invalid_json(self):
        result = structure_validity(
            inputs="test", outputs="not json", expectations=None
        )
        assert result.value == 0.0

    def test_none_output(self):
        result = structure_validity(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0

    def test_dict_input(self):
        data = json.loads(_caa_output())
        result = structure_validity(inputs="test", outputs=data, expectations=None)
        assert result.value == 1.0

    def test_non_list_ad_sets(self):
        bp = {
            "campaign_name": "Test",
            "campaign_objective": "AWARENESS",
            "ad_sets": "bad",
        }
        result = structure_validity(
            inputs="test", outputs=_caa_output(blueprint=bp), expectations=None
        )
        assert result.value < 1.0

    def test_feedback_name(self):
        result = structure_validity(
            inputs="test", outputs=_caa_output(), expectations=None
        )
        assert result.name == "structure_validity"

    def test_non_dict_ad_set_entries(self):
        bp = {
            "campaign_name": "Test",
            "campaign_objective": "AWARENESS",
            "ad_sets": ["bad", 42],
        }
        result = structure_validity(
            inputs="test", outputs=_caa_output(blueprint=bp), expectations=None
        )
        assert result.value < 1.0


# ── budget_rationality tests (AC-2) ──


class TestBudgetRationality:
    def test_sums_to_100(self):
        result = budget_rationality(
            inputs="test", outputs=_caa_output(), expectations=None
        )
        assert result.value == 1.0

    def test_sums_to_99(self):
        out = _caa_output(
            funnel_map={
                "stages": [
                    {"stage": "tofu", "budget_pct": 49},
                    {"stage": "mofu", "budget_pct": 25},
                    {"stage": "bofu", "budget_pct": 20},
                    {"stage": "retention", "budget_pct": 5},
                ]
            }
        )
        result = budget_rationality(inputs="test", outputs=out, expectations=None)
        assert result.value == 1.0  # within ±1% tolerance

    def test_sums_to_95(self):
        out = _caa_output(
            funnel_map={
                "stages": [
                    {"stage": "tofu", "budget_pct": 45},
                    {"stage": "mofu", "budget_pct": 25},
                    {"stage": "bofu", "budget_pct": 20},
                    {"stage": "retention", "budget_pct": 5},
                ]
            }
        )
        result = budget_rationality(inputs="test", outputs=out, expectations=None)
        assert 0.0 < result.value < 1.0

    def test_sums_to_80(self):
        out = _caa_output(
            funnel_map={
                "stages": [
                    {"stage": "tofu", "budget_pct": 30},
                    {"stage": "mofu", "budget_pct": 25},
                    {"stage": "bofu", "budget_pct": 20},
                    {"stage": "retention", "budget_pct": 5},
                ]
            }
        )
        result = budget_rationality(inputs="test", outputs=out, expectations=None)
        assert result.value < 0.2

    def test_missing_funnel_map(self):
        out = json.dumps({"blueprint": {}, "targeting_specs": []})
        result = budget_rationality(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_empty_stages(self):
        out = _caa_output(funnel_map={"stages": []})
        result = budget_rationality(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_none_output(self):
        result = budget_rationality(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0

    def test_single_stage_100(self):
        out = _caa_output(funnel_map={"stages": [{"stage": "tofu", "budget_pct": 100}]})
        result = budget_rationality(inputs="test", outputs=out, expectations=None)
        assert result.value == 1.0

    def test_feedback_name(self):
        result = budget_rationality(
            inputs="test", outputs=_caa_output(), expectations=None
        )
        assert result.name == "budget_rationality"

    def test_non_numeric_budget(self):
        out = _caa_output(
            funnel_map={"stages": [{"stage": "tofu", "budget_pct": "bad"}]}
        )
        result = budget_rationality(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_dict_format_stages(self):
        """funnel_map as dict of stage dicts."""
        out = _caa_output(
            funnel_map={
                "tofu": {"budget_pct": 50},
                "mofu": {"budget_pct": 25},
                "bofu": {"budget_pct": 20},
                "retention": {"budget_pct": 5},
            }
        )
        result = budget_rationality(inputs="test", outputs=out, expectations=None)
        assert result.value == 1.0


# ── funnel_coverage tests (AC-3) ──


class TestFunnelCoverage:
    def test_new_brand_tofu_50(self):
        result = funnel_coverage(
            inputs="test", outputs=_caa_output(), expectations={"brand_maturity": "new"}
        )
        assert result.value >= 0.9

    def test_new_brand_tofu_below_50(self):
        out = _caa_output(
            funnel_map={
                "stages": [
                    {"stage": "tofu", "budget_pct": 30},
                    {"stage": "mofu", "budget_pct": 30},
                    {"stage": "bofu", "budget_pct": 30},
                    {"stage": "retention", "budget_pct": 10},
                ]
            }
        )
        result = funnel_coverage(
            inputs="test", outputs=out, expectations={"brand_maturity": "new"}
        )
        assert result.value < 0.9

    def test_established_brand_bofu_30(self):
        out = _caa_output(
            funnel_map={
                "stages": [
                    {"stage": "tofu", "budget_pct": 20},
                    {"stage": "mofu", "budget_pct": 25},
                    {"stage": "bofu", "budget_pct": 40},
                    {"stage": "retention", "budget_pct": 15},
                ]
            }
        )
        result = funnel_coverage(
            inputs="test", outputs=out, expectations={"brand_maturity": "established"}
        )
        assert result.value >= 0.9

    def test_established_brand_bofu_below_30(self):
        out = _caa_output(
            funnel_map={
                "stages": [
                    {"stage": "tofu", "budget_pct": 40},
                    {"stage": "mofu", "budget_pct": 35},
                    {"stage": "bofu", "budget_pct": 15},
                    {"stage": "retention", "budget_pct": 10},
                ]
            }
        )
        result = funnel_coverage(
            inputs="test", outputs=out, expectations={"brand_maturity": "established"}
        )
        assert result.value < 0.9

    def test_all_4_stages_present(self):
        result = funnel_coverage(
            inputs="test", outputs=_caa_output(), expectations=None
        )
        assert result.value > 0.5

    def test_missing_stages(self):
        out = _caa_output(funnel_map={"stages": [{"stage": "tofu", "budget_pct": 100}]})
        result = funnel_coverage(inputs="test", outputs=out, expectations=None)
        assert result.value < 0.9

    def test_default_new_brand(self):
        result = funnel_coverage(
            inputs="test", outputs=_caa_output(), expectations=None
        )
        r2 = funnel_coverage(
            inputs="test", outputs=_caa_output(), expectations={"brand_maturity": "new"}
        )
        assert result.value == r2.value

    def test_none_output(self):
        result = funnel_coverage(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0

    def test_malformed_funnel_map(self):
        out = _caa_output(funnel_map="bad")
        result = funnel_coverage(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_emerging_brand(self):
        out = _caa_output(
            funnel_map={
                "stages": [
                    {"stage": "tofu", "budget_pct": 35},
                    {"stage": "mofu", "budget_pct": 30},
                    {"stage": "bofu", "budget_pct": 25},
                    {"stage": "retention", "budget_pct": 10},
                ]
            }
        )
        result = funnel_coverage(
            inputs="test", outputs=out, expectations={"brand_maturity": "emerging"}
        )
        assert result.value >= 0.9

    def test_feedback_name(self):
        result = funnel_coverage(
            inputs="test", outputs=_caa_output(), expectations=None
        )
        assert result.name == "funnel_coverage"


# ── targeting_quality tests (AC-4) ──


class TestTargetingQuality:
    def test_full_targeting(self):
        result = targeting_quality(
            inputs="test", outputs=_caa_output(), expectations=None
        )
        assert result.value == 1.0

    def test_missing_demographics(self):
        out = _caa_output(
            targeting_specs=[
                {
                    "ad_set_name": "TOFU",
                    "interests": ["Tech"],
                    "custom_audiences": ["buyers"],
                    "lookalike_audiences": [],
                }
            ]
        )
        result = targeting_quality(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_missing_interests(self):
        out = _caa_output(
            targeting_specs=[
                {
                    "ad_set_name": "TOFU",
                    "demographics": {"age_min": 18},
                    "interests": [],
                    "custom_audiences": ["buyers"],
                    "lookalike_audiences": [],
                }
            ]
        )
        result = targeting_quality(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_no_custom_or_lookalike(self):
        out = _caa_output(
            targeting_specs=[
                {
                    "ad_set_name": "TOFU",
                    "demographics": {"age_min": 18},
                    "interests": ["Tech"],
                    "custom_audiences": [],
                    "lookalike_audiences": [],
                }
            ]
        )
        result = targeting_quality(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_lookalike_only(self):
        out = _caa_output(
            targeting_specs=[
                {
                    "ad_set_name": "TOFU",
                    "demographics": {"age_min": 18},
                    "interests": ["Tech"],
                    "custom_audiences": [],
                    "lookalike_audiences": ["lookalike_1pct"],
                }
            ]
        )
        result = targeting_quality(inputs="test", outputs=out, expectations=None)
        assert result.value == 1.0

    def test_empty_targeting_specs(self):
        out = _caa_output(targeting_specs=[])
        result = targeting_quality(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_mixed_quality(self):
        out = _caa_output(
            targeting_specs=[
                {
                    "ad_set_name": "good",
                    "demographics": {"age_min": 18},
                    "interests": ["Tech"],
                    "custom_audiences": ["buyers"],
                    "lookalike_audiences": [],
                },
                {
                    "ad_set_name": "bad",
                    "demographics": {},
                    "interests": [],
                    "custom_audiences": [],
                    "lookalike_audiences": [],
                },
            ]
        )
        result = targeting_quality(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.5

    def test_none_output(self):
        result = targeting_quality(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0

    def test_non_list_targeting_specs(self):
        out = _caa_output(targeting_specs="bad")
        result = targeting_quality(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_non_dict_entries(self):
        out = _caa_output(targeting_specs=["bad", 42])
        result = targeting_quality(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_feedback_name(self):
        result = targeting_quality(
            inputs="test", outputs=_caa_output(), expectations=None
        )
        assert result.name == "targeting_quality"


# ── Scorer conformance ──


class TestCaaScorerConformance:
    def test_all_are_scorer_instances(self):
        from mlflow.genai.scorers import Scorer

        for s in [
            structure_validity,
            budget_rationality,
            funnel_coverage,
            targeting_quality,
        ]:
            assert isinstance(s, Scorer), f"{s.name} is not a Scorer"

    def test_all_accept_keyword_args(self):
        for s in [
            structure_validity,
            budget_rationality,
            funnel_coverage,
            targeting_quality,
        ]:
            result = s(inputs="test", outputs=_caa_output(), expectations=None)
            assert result is not None
