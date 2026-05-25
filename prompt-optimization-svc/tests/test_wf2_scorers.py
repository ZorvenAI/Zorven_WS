"""Unit tests for WF2 scorers (brand strategy pipeline).

10+ tests per scorer covering perfect, partial, invalid, and edge inputs.
"""

import json

from app.scorers.wf2.positioning_clarity import positioning_clarity
from app.scorers.wf2.architecture_coherence import architecture_coherence
from app.scorers.wf2.voice_consistency import voice_consistency
from app.scorers.wf2.name_quality import name_quality
from app.scorers.wf2.narrative_engagement import narrative_engagement


# ── helpers ──


def _positioning_output(**overrides) -> str:
    """Build a minimal valid BPA positioning output JSON string."""
    data = {
        "recommended_positioning": overrides.get(
            "recommended_positioning",
            {
                "statement": "We are the premium AI-first brand platform.",
                "target_segment": "SMBs",
            },
        ),
        "canvas": overrides.get(
            "canvas",
            {
                "fit_score": 92,
                "elements": ["value_prop", "differentiator"],
            },
        ),
        "differentiation": overrides.get(
            "differentiation",
            {
                "overall_differentiation_score": 72,
                "factors": ["AI-native", "multi-tenant"],
            },
        ),
    }
    data.update({k: v for k, v in overrides.items() if k not in data})
    return json.dumps(data)


def _architecture_output(**overrides) -> str:
    """Build a minimal valid BAA architecture output JSON string."""
    data = {
        "recommendation": overrides.get(
            "recommendation",
            {
                "recommended_model": "branded_house",
                "model_scores": [
                    {"model": "branded_house", "score": 0.9},
                    {"model": "house_of_brands", "score": 0.6},
                ],
            },
        ),
        "hierarchy": overrides.get(
            "hierarchy",
            {
                "root": {"name": "Zorven", "type": "master_brand"},
                "total_depth": 3,
                "branches": ["Platform", "Services"],
            },
        ),
        "naming_hierarchy": overrides.get(
            "naming_hierarchy",
            {
                "consistency_score": 85,
                "naming_pattern": "parent_endorsed",
            },
        ),
    }
    data.update({k: v for k, v in overrides.items() if k not in data})
    return json.dumps(data)


def _voice_output(**overrides) -> str:
    """Build a minimal valid BPV voice/personality output JSON string."""
    data = {
        "aaker_profile": overrides.get(
            "aaker_profile",
            {
                "dimensions": [
                    {"name": "Sincerity", "score": 75},
                    {"name": "Excitement", "score": 85},
                    {"name": "Competence", "score": 90},
                    {"name": "Sophistication", "score": 60},
                    {"name": "Ruggedness", "score": 40},
                ]
            },
        ),
        "archetype": overrides.get(
            "archetype",
            {
                "primary": "Creator",
                "resonance_score": 0.91,
            },
        ),
        "values_hierarchy": overrides.get(
            "values_hierarchy",
            {
                "core_values": ["Innovation", "Trust"],
                "authenticity_score": 0.87,
            },
        ),
    }
    data.update({k: v for k, v in overrides.items() if k not in data})
    return json.dumps(data)


def _naming_output(**overrides) -> str:
    """Build a minimal valid NTA naming output JSON string."""
    data = {
        "name_candidates": overrides.get(
            "name_candidates",
            [
                {"name": "Lumina", "linguistic_score": 0.9, "brand_fit_score": 0.85},
                {"name": "Aethon", "linguistic_score": 0.8, "brand_fit_score": 0.75},
            ],
        ),
        "shortlisted_names": overrides.get(
            "shortlisted_names",
            ["Lumina", "Aethon"],
        ),
        "taglines": overrides.get(
            "taglines",
            [
                {"text": "Build brilliance.", "memorability_score": 0.88},
                {"text": "Brand, amplified.", "memorability_score": 0.82},
            ],
        ),
    }
    data.update({k: v for k, v in overrides.items() if k not in data})
    return json.dumps(data)


def _narrative_output(**overrides) -> str:
    """Build a minimal valid BSA narrative output JSON string."""
    data = {
        "origin_story": overrides.get(
            "origin_story",
            {
                "narrative": "Founded in a garage with a vision to democratize AI.",
                "tone": "inspirational",
            },
        ),
        "mission_vision": overrides.get(
            "mission_vision",
            {
                "mission": "Empower every brand with AI.",
                "vision": "A world where every brand tells its story.",
            },
        ),
        "pitches": overrides.get(
            "pitches",
            {
                "elevator": "We turn brand chaos into AI-powered clarity.",
                "investor": "AI brand platform, $50B TAM, 10x efficiency.",
            },
        ),
        "channel_narratives": overrides.get(
            "channel_narratives",
            {
                "social_media": "Short, punchy brand voice.",
                "website": "Full brand story arc.",
            },
        ),
    }
    data.update({k: v for k, v in overrides.items() if k not in data})
    return json.dumps(data)


# ── positioning_clarity tests ──


class TestPositioningClarity:
    def test_valid_complete_output(self):
        result = positioning_clarity(
            inputs="test", outputs=_positioning_output(), expectations=None
        )
        assert result.value >= 0.8

    def test_perfect_scores(self):
        out = _positioning_output(
            canvas={"fit_score": 1.0},
            differentiation={"overall_differentiation_score": 1.0},
        )
        result = positioning_clarity(inputs="test", outputs=out, expectations=None)
        assert result.value == 1.0

    def test_missing_recommended_positioning(self):
        out = _positioning_output(recommended_positioning={})
        result = positioning_clarity(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_empty_statement(self):
        out = _positioning_output(
            recommended_positioning={"statement": "", "target_segment": "SMBs"}
        )
        result = positioning_clarity(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_missing_canvas(self):
        out = _positioning_output(canvas={})
        result = positioning_clarity(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_canvas_fit_score_out_of_range(self):
        out = _positioning_output(canvas={"fit_score": 1.5})
        result = positioning_clarity(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_missing_differentiation(self):
        out = _positioning_output(differentiation={})
        result = positioning_clarity(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_none_output(self):
        result = positioning_clarity(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0

    def test_invalid_json(self):
        result = positioning_clarity(
            inputs="test", outputs="not json", expectations=None
        )
        assert result.value == 0.0

    def test_dict_input(self):
        data = json.loads(_positioning_output())
        result = positioning_clarity(inputs="test", outputs=data, expectations=None)
        assert result.value >= 0.8

    def test_non_dict_recommended_positioning(self):
        out = _positioning_output(recommended_positioning="just a string")
        result = positioning_clarity(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_non_dict_canvas(self):
        out = _positioning_output(canvas="bad")
        result = positioning_clarity(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_feedback_name(self):
        result = positioning_clarity(
            inputs="test", outputs=_positioning_output(), expectations=None
        )
        assert result.name == "positioning_clarity"

    def test_partial_only_positioning(self):
        out = _positioning_output(canvas={}, differentiation={})
        result = positioning_clarity(inputs="test", outputs=out, expectations=None)
        # Only 40% (positioning) should score
        assert result.value == 0.4

    def test_zero_fit_score(self):
        out = _positioning_output(
            canvas={"fit_score": 0.0},
            differentiation={"overall_differentiation_score": 0.0},
        )
        result = positioning_clarity(inputs="test", outputs=out, expectations=None)
        # 0.4 * 1.0 + 0.3 * 0.0 + 0.3 * 0.0 = 0.4
        assert result.value == 0.4

    def test_empty_dict_output(self):
        result = positioning_clarity(
            inputs="test", outputs=json.dumps({}), expectations=None
        )
        assert result.value == 0.0

    def test_non_numeric_fit_score(self):
        out = _positioning_output(canvas={"fit_score": "high"})
        result = positioning_clarity(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0


# ── architecture_coherence tests ──


class TestArchitectureCoherence:
    def test_valid_complete_output(self):
        result = architecture_coherence(
            inputs="test", outputs=_architecture_output(), expectations=None
        )
        assert result.value == 1.0

    def test_missing_recommendation(self):
        out = _architecture_output(recommendation={})
        result = architecture_coherence(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_missing_recommended_model(self):
        out = _architecture_output(
            recommendation={"model_scores": [{"model": "x", "score": 0.8}]}
        )
        result = architecture_coherence(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_empty_model_scores(self):
        out = _architecture_output(
            recommendation={"recommended_model": "branded_house", "model_scores": []}
        )
        result = architecture_coherence(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_missing_hierarchy(self):
        out = _architecture_output(hierarchy={})
        result = architecture_coherence(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_hierarchy_missing_root(self):
        out = _architecture_output(hierarchy={"total_depth": 3})
        result = architecture_coherence(inputs="test", outputs=out, expectations=None)
        # hierarchy invalid because root is None via .get() -> None, but has_root checks not None
        # Actually hier.get("root") returns None which is not not-None, so has_root = False
        assert result.value < 1.0

    def test_hierarchy_missing_depth(self):
        out = _architecture_output(hierarchy={"root": "Zorven"})
        result = architecture_coherence(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_missing_naming_hierarchy(self):
        out = _architecture_output(naming_hierarchy={})
        result = architecture_coherence(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_naming_consistency_negative(self):
        out = _architecture_output(naming_hierarchy={"consistency_score": -5})
        result = architecture_coherence(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_naming_consistency_100_scale(self):
        """consistency_score on 0-100 scale should normalize to 0-1."""
        out = _architecture_output(
            naming_hierarchy={"consistency_score": 85, "naming_pattern": "endorsed"}
        )
        result = architecture_coherence(inputs="test", outputs=out, expectations=None)
        assert result.value == 1.0  # valid component

    def test_none_output(self):
        result = architecture_coherence(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0

    def test_invalid_json(self):
        result = architecture_coherence(
            inputs="test", outputs="not json", expectations=None
        )
        assert result.value == 0.0

    def test_dict_input(self):
        data = json.loads(_architecture_output())
        result = architecture_coherence(inputs="test", outputs=data, expectations=None)
        assert result.value == 1.0

    def test_non_dict_recommendation(self):
        out = _architecture_output(recommendation="bad")
        result = architecture_coherence(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_non_list_model_scores(self):
        out = _architecture_output(
            recommendation={"recommended_model": "branded_house", "model_scores": "bad"}
        )
        result = architecture_coherence(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_feedback_name(self):
        result = architecture_coherence(
            inputs="test", outputs=_architecture_output(), expectations=None
        )
        assert result.name == "architecture_coherence"

    def test_partial_one_component(self):
        out = _architecture_output(recommendation={}, hierarchy={})
        result = architecture_coherence(inputs="test", outputs=out, expectations=None)
        # Only naming_hierarchy valid -> 1/3
        assert result.value == round(1 / 3.0, 4)

    def test_empty_dict_output(self):
        result = architecture_coherence(
            inputs="test", outputs=json.dumps({}), expectations=None
        )
        assert result.value == 0.0

    def test_non_numeric_consistency_score(self):
        out = _architecture_output(naming_hierarchy={"consistency_score": "high"})
        result = architecture_coherence(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0


# ── voice_consistency tests ──


class TestVoiceConsistency:
    def test_valid_complete_output(self):
        result = voice_consistency(
            inputs="test", outputs=_voice_output(), expectations=None
        )
        assert result.value == 1.0

    def test_missing_aaker_profile(self):
        out = _voice_output(aaker_profile={})
        result = voice_consistency(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_empty_dimensions(self):
        out = _voice_output(aaker_profile={"dimensions": []})
        result = voice_consistency(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_dimensions_invalid_score(self):
        out = _voice_output(
            aaker_profile={"dimensions": [{"name": "Sincerity", "score": "high"}]}
        )
        result = voice_consistency(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_dimensions_score_out_of_range(self):
        out = _voice_output(
            aaker_profile={"dimensions": [{"name": "Sincerity", "score": 150}]}
        )
        result = voice_consistency(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_dimensions_non_dict_entry(self):
        out = _voice_output(aaker_profile={"dimensions": ["bad", 42]})
        result = voice_consistency(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_missing_archetype(self):
        out = _voice_output(archetype={})
        result = voice_consistency(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_archetype_resonance_out_of_range(self):
        out = _voice_output(archetype={"primary": "Creator", "resonance_score": 1.5})
        result = voice_consistency(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_missing_values_hierarchy(self):
        out = _voice_output(values_hierarchy={})
        result = voice_consistency(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_values_hierarchy_non_numeric_authenticity(self):
        out = _voice_output(values_hierarchy={"authenticity_score": "very authentic"})
        result = voice_consistency(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_none_output(self):
        result = voice_consistency(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0

    def test_invalid_json(self):
        result = voice_consistency(inputs="test", outputs="not json", expectations=None)
        assert result.value == 0.0

    def test_dict_input(self):
        data = json.loads(_voice_output())
        result = voice_consistency(inputs="test", outputs=data, expectations=None)
        assert result.value == 1.0

    def test_non_dict_aaker_profile(self):
        out = _voice_output(aaker_profile="bad")
        result = voice_consistency(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_non_dict_archetype(self):
        out = _voice_output(archetype="bad")
        result = voice_consistency(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_feedback_name(self):
        result = voice_consistency(
            inputs="test", outputs=_voice_output(), expectations=None
        )
        assert result.name == "voice_consistency"

    def test_partial_one_component(self):
        out = _voice_output(aaker_profile={}, archetype={})
        result = voice_consistency(inputs="test", outputs=out, expectations=None)
        # Only values_hierarchy valid -> 1/3
        assert result.value == round(1 / 3.0, 4)

    def test_empty_dict_output(self):
        result = voice_consistency(
            inputs="test", outputs=json.dumps({}), expectations=None
        )
        assert result.value == 0.0

    def test_single_valid_dimension(self):
        out = _voice_output(
            aaker_profile={"dimensions": [{"name": "Sincerity", "score": 80}]}
        )
        result = voice_consistency(inputs="test", outputs=out, expectations=None)
        assert result.value >= round(1 / 3.0, 4)


# ── name_quality tests ──


class TestNameQuality:
    def test_valid_complete_output(self):
        result = name_quality(
            inputs="test", outputs=_naming_output(), expectations=None
        )
        assert result.value == 1.0

    def test_missing_name_candidates(self):
        out = _naming_output(name_candidates=[])
        result = name_quality(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_candidates_no_score_fields(self):
        out = _naming_output(name_candidates=[{"name": "Lumina", "meaning": "light"}])
        result = name_quality(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_candidates_non_dict_entries(self):
        out = _naming_output(name_candidates=["bad", 42])
        result = name_quality(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_missing_shortlisted_names(self):
        out = _naming_output(shortlisted_names=[])
        result = name_quality(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_missing_taglines(self):
        out = _naming_output(taglines=[])
        result = name_quality(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_taglines_no_memorability(self):
        out = _naming_output(taglines=[{"text": "Build brilliance.", "impact": "high"}])
        result = name_quality(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_taglines_non_dict_entries(self):
        out = _naming_output(taglines=["just a string"])
        result = name_quality(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_none_output(self):
        result = name_quality(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0

    def test_invalid_json(self):
        result = name_quality(inputs="test", outputs="not json", expectations=None)
        assert result.value == 0.0

    def test_dict_input(self):
        data = json.loads(_naming_output())
        result = name_quality(inputs="test", outputs=data, expectations=None)
        assert result.value == 1.0

    def test_non_list_name_candidates(self):
        out = _naming_output(name_candidates="bad")
        result = name_quality(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_non_list_shortlisted(self):
        out = _naming_output(shortlisted_names="bad")
        result = name_quality(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_non_list_taglines(self):
        out = _naming_output(taglines="bad")
        result = name_quality(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_feedback_name(self):
        result = name_quality(
            inputs="test", outputs=_naming_output(), expectations=None
        )
        assert result.name == "name_quality"

    def test_partial_only_shortlisted(self):
        out = _naming_output(
            name_candidates=[],
            taglines=[],
        )
        result = name_quality(inputs="test", outputs=out, expectations=None)
        # Only shortlisted_names valid -> 1/3
        assert result.value == round(1 / 3.0, 4)

    def test_empty_dict_output(self):
        result = name_quality(inputs="test", outputs=json.dumps({}), expectations=None)
        assert result.value == 0.0

    def test_proportional_two_of_three(self):
        out = _naming_output(taglines=[])
        result = name_quality(inputs="test", outputs=out, expectations=None)
        # name_candidates + shortlisted -> 2/3
        assert result.value == round(2 / 3.0, 4)


# ── narrative_engagement tests ──


class TestNarrativeEngagement:
    def test_valid_complete_output(self):
        result = narrative_engagement(
            inputs="test", outputs=_narrative_output(), expectations=None
        )
        assert result.value == 1.0

    def test_missing_origin_story(self):
        out = _narrative_output(origin_story=None)
        result = narrative_engagement(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_missing_mission_vision(self):
        out = _narrative_output(mission_vision=None)
        result = narrative_engagement(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_missing_pitches(self):
        out = _narrative_output(pitches=None)
        result = narrative_engagement(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_missing_channel_narratives(self):
        out = _narrative_output(channel_narratives=None)
        result = narrative_engagement(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_pitches_as_list(self):
        out = _narrative_output(pitches=["Elevator pitch here", "Investor pitch here"])
        result = narrative_engagement(inputs="test", outputs=out, expectations=None)
        assert result.value == 1.0

    def test_non_dict_origin_story(self):
        out = _narrative_output(origin_story="just a string")
        result = narrative_engagement(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_non_dict_channel_narratives(self):
        out = _narrative_output(channel_narratives="bad")
        result = narrative_engagement(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_non_dict_or_list_pitches(self):
        out = _narrative_output(pitches=42)
        result = narrative_engagement(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_none_output(self):
        result = narrative_engagement(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0

    def test_invalid_json(self):
        result = narrative_engagement(
            inputs="test", outputs="not json", expectations=None
        )
        assert result.value == 0.0

    def test_dict_input(self):
        data = json.loads(_narrative_output())
        result = narrative_engagement(inputs="test", outputs=data, expectations=None)
        assert result.value == 1.0

    def test_feedback_name(self):
        result = narrative_engagement(
            inputs="test", outputs=_narrative_output(), expectations=None
        )
        assert result.name == "narrative_engagement"

    def test_partial_two_sections(self):
        out = _narrative_output(origin_story=None, mission_vision=None)
        result = narrative_engagement(inputs="test", outputs=out, expectations=None)
        # pitches + channel_narratives -> 2/4
        assert result.value == 0.5

    def test_partial_one_section(self):
        out = _narrative_output(origin_story=None, mission_vision=None, pitches=None)
        result = narrative_engagement(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.25

    def test_empty_dict_output(self):
        result = narrative_engagement(
            inputs="test", outputs=json.dumps({}), expectations=None
        )
        assert result.value == 0.0

    def test_all_sections_missing(self):
        out = _narrative_output(
            origin_story=None,
            mission_vision=None,
            pitches=None,
            channel_narratives=None,
        )
        result = narrative_engagement(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0


# ── WF2 Scorer conformance ──


class TestWf2ScorerConformance:
    def test_all_are_scorer_instances(self):
        from mlflow.genai.scorers import Scorer

        for s in [
            positioning_clarity,
            architecture_coherence,
            voice_consistency,
            name_quality,
            narrative_engagement,
        ]:
            assert isinstance(s, Scorer), f"{s.name} is not a Scorer"

    def test_all_accept_keyword_args(self):
        pairs = [
            (positioning_clarity, _positioning_output),
            (architecture_coherence, _architecture_output),
            (voice_consistency, _voice_output),
            (name_quality, _naming_output),
            (narrative_engagement, _narrative_output),
        ]
        for s, helper in pairs:
            result = s(inputs="test", outputs=helper(), expectations=None)
            assert result is not None, f"{s.name} returned None"

    def test_all_return_correct_feedback_names(self):
        pairs = [
            (positioning_clarity, _positioning_output, "positioning_clarity"),
            (architecture_coherence, _architecture_output, "architecture_coherence"),
            (voice_consistency, _voice_output, "voice_consistency"),
            (name_quality, _naming_output, "name_quality"),
            (narrative_engagement, _narrative_output, "narrative_engagement"),
        ]
        for s, helper, expected in pairs:
            result = s(inputs="test", outputs=helper(), expectations=None)
            assert result.name == expected, f"Expected {expected}, got {result.name}"

    def test_all_handle_none_output(self):
        for s in [
            positioning_clarity,
            architecture_coherence,
            voice_consistency,
            name_quality,
            narrative_engagement,
        ]:
            result = s(inputs="test", outputs=None, expectations=None)
            assert result.value == 0.0, f"{s.name} did not return 0.0 for None output"
