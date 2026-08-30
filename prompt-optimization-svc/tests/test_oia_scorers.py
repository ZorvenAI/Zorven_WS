"""Unit tests for OIA onboarding intelligence scorers (L-03).

Covers all 8 scorers: perfect, partial, invalid, and edge inputs.
"""

import json

from app.scorers.oia.extraction_accuracy import extraction_accuracy
from app.scorers.oia.followup_usefulness import followup_usefulness
from app.scorers.oia.media_analysis_accuracy import media_analysis_accuracy
from app.scorers.oia.questionnaire_coverage import questionnaire_coverage
from app.scorers.oia.research_factuality import research_factuality
from app.scorers.oia.stream_attachment import stream_attachment
from app.scorers.oia.sufficiency_agreement import sufficiency_agreement
from app.scorers.oia.summary_faithfulness import summary_faithfulness
from app.scorers.oia import OIA_SCORERS

# ── Helper builders ──


def _research_output(**overrides) -> str:
    data = {
        "sourced_facts": overrides.get(
            "sourced_facts",
            [
                {"claim": "Revenue is $1M", "source_url": "https://example.com"},
                {"claim": "10 employees", "source_url": "https://example.com/about"},
            ],
        ),
        "open_unknowns": overrides.get(
            "open_unknowns",
            ["founding year unclear", "market share unknown"],
        ),
        "source_urls": overrides.get(
            "source_urls",
            ["https://example.com", "https://example.com/about"],
        ),
    }
    data.update({k: v for k, v in overrides.items() if k not in data})
    return json.dumps(data)


def _questionnaire_output(**overrides) -> str:
    data = {
        "questions": overrides.get(
            "questions",
            [
                {
                    "text": "What is your brand voice?",
                    "rationale": "Needed for brand strategy",
                    "workflow_id": "wf2",
                },
                {
                    "text": "Who is your target audience?",
                    "rationale": "Audience profiling",
                    "workflow_id": "wf1",
                },
                {
                    "text": "What is your budget?",
                    "rationale": "Campaign planning",
                    "workflow_id": "wf3",
                },
            ],
        ),
    }
    data.update({k: v for k, v in overrides.items() if k not in data})
    return json.dumps(data)


def _stream_output(**overrides) -> str:
    data = {
        "matched_questions": overrides.get(
            "matched_questions",
            [
                {"question_id": "q1", "answer": "We target millennials"},
                {"question_id": "q2", "answer": "Budget is $50k"},
            ],
        ),
        "ad_hoc_questions": overrides.get(
            "ad_hoc_questions",
            [{"text": "What about social media?"}],
        ),
    }
    data.update({k: v for k, v in overrides.items() if k not in data})
    return json.dumps(data)


def _sufficiency_output(**overrides) -> str:
    data = {
        "sufficient": overrides.get("sufficient", True),
        "confidence": overrides.get("confidence", 0.85),
        "reasoning": overrides.get("reasoning", "All key fields populated"),
        "field_coverage": overrides.get(
            "field_coverage", {"legal_name": True, "industry": True}
        ),
    }
    data.update({k: v for k, v in overrides.items() if k not in data})
    return json.dumps(data)


def _media_output(**overrides) -> str:
    data = {
        "extracted_text": overrides.get("extracted_text", "ACME Corp Logo Design"),
        "usage_tags": overrides.get("usage_tags", ["logo", "branding"]),
    }
    data.update({k: v for k, v in overrides.items() if k not in data})
    return json.dumps(data)


def _summary_output(**overrides) -> str:
    data = {
        "summary": overrides.get(
            "summary",
            "Meeting covered brand strategy and target audience definition.",
        ),
        "key_moments": overrides.get(
            "key_moments",
            [
                {"text": "Brand voice discussion", "timestamp": 120.5},
                {"text": "Audience definition", "t_start": 300.0},
            ],
        ),
        "speakers": overrides.get(
            "speakers",
            [{"name": "Alice", "role": "founder"}, {"name": "Bob", "role": "agent"}],
        ),
    }
    data.update({k: v for k, v in overrides.items() if k not in data})
    return json.dumps(data)


def _extraction_output(**overrides) -> str:
    data = {
        "extracted_fields": overrides.get(
            "extracted_fields",
            {
                "legal_name": "Acme Corp",
                "industry": "Technology",
                "founding_year": "2020",
            },
        ),
    }
    data.update({k: v for k, v in overrides.items() if k not in data})
    return json.dumps(data)


# ── research_factuality tests ──


class TestResearchFactuality:
    def test_valid_complete_output(self):
        result = research_factuality(
            inputs="test", outputs=_research_output(), expectations=None
        )
        assert result.value == 1.0

    def test_missing_sourced_facts(self):
        out = _research_output(sourced_facts=[])
        result = research_factuality(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_facts_without_source_url(self):
        out = _research_output(sourced_facts=[{"claim": "Revenue is $1M"}])
        result = research_factuality(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_missing_unknowns(self):
        out = _research_output(open_unknowns=[])
        result = research_factuality(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_missing_source_urls(self):
        out = _research_output(source_urls=[])
        result = research_factuality(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_none_output(self):
        result = research_factuality(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0

    def test_invalid_json(self):
        result = research_factuality(inputs="test", outputs="{{bad", expectations=None)
        assert result.value == 0.0

    def test_dict_input(self):
        data = json.loads(_research_output())
        result = research_factuality(inputs="test", outputs=data, expectations=None)
        assert result.value == 1.0

    def test_feedback_name(self):
        result = research_factuality(
            inputs="test", outputs=_research_output(), expectations=None
        )
        assert result.name == "research_factuality"

    def test_all_fields_missing(self):
        result = research_factuality(
            inputs="test", outputs=json.dumps({}), expectations=None
        )
        assert result.value == 0.0


# ── questionnaire_coverage tests ──


class TestQuestionnaireCoverage:
    def test_valid_complete_output(self):
        result = questionnaire_coverage(
            inputs="test", outputs=_questionnaire_output(), expectations=None
        )
        assert result.value == 1.0

    def test_missing_questions(self):
        out = _questionnaire_output(questions=[])
        result = questionnaire_coverage(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_questions_without_workflow_id(self):
        out = _questionnaire_output(
            questions=[{"text": "What is your name?", "rationale": "Identification"}]
        )
        result = questionnaire_coverage(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_questions_without_rationale(self):
        out = _questionnaire_output(
            questions=[{"text": "What is your name?", "workflow_id": "wf1"}]
        )
        result = questionnaire_coverage(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_none_output(self):
        result = questionnaire_coverage(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0

    def test_feedback_name(self):
        result = questionnaire_coverage(
            inputs="test", outputs=_questionnaire_output(), expectations=None
        )
        assert result.name == "questionnaire_coverage"


# ── stream_attachment tests ──


class TestStreamAttachment:
    def test_valid_complete_output(self):
        result = stream_attachment(
            inputs="test", outputs=_stream_output(), expectations=None
        )
        assert result.value == 1.0

    def test_missing_matched_questions(self):
        out = _stream_output(matched_questions=[])
        result = stream_attachment(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_matches_without_answer(self):
        out = _stream_output(matched_questions=[{"question_id": "q1"}])
        result = stream_attachment(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_no_ad_hoc(self):
        out = _stream_output(ad_hoc_questions=[])
        result = stream_attachment(inputs="test", outputs=out, expectations=None)
        assert result.value == 1.0

    def test_none_output(self):
        result = stream_attachment(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0

    def test_feedback_name(self):
        result = stream_attachment(
            inputs="test", outputs=_stream_output(), expectations=None
        )
        assert result.name == "stream_attachment"


# ── sufficiency_agreement tests ──


class TestSufficiencyAgreement:
    def test_agrees_with_admin(self):
        out = _sufficiency_output(sufficient=True)
        exp = json.dumps({"admin_sufficient": True})
        result = sufficiency_agreement(inputs="test", outputs=out, expectations=exp)
        assert result.value == 1.0

    def test_disagrees_with_admin(self):
        out = _sufficiency_output(sufficient=True)
        exp = json.dumps({"admin_sufficient": False})
        result = sufficiency_agreement(inputs="test", outputs=out, expectations=exp)
        assert result.value == 0.0

    def test_no_expectations_with_reasoning(self):
        out = _sufficiency_output()
        result = sufficiency_agreement(inputs="test", outputs=out, expectations=None)
        assert result.value > 0.5

    def test_no_sufficient_field(self):
        out = json.dumps({"confidence": 0.9})
        result = sufficiency_agreement(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_none_output(self):
        result = sufficiency_agreement(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0

    def test_feedback_name(self):
        result = sufficiency_agreement(
            inputs="test", outputs=_sufficiency_output(), expectations=None
        )
        assert result.name == "sufficiency_agreement"


# ── followup_usefulness tests ──


class TestFollowupUsefulness:
    def test_stub_returns_zero(self):
        result = followup_usefulness(
            inputs="test", outputs=json.dumps({"followups": []}), expectations=None
        )
        assert result.value == 0.0

    def test_stub_documents_gap(self):
        result = followup_usefulness(inputs="test", outputs="{}", expectations=None)
        assert "EVT-105" in result.rationale
        assert "G-04" in result.rationale

    def test_stub_returns_zero_with_any_input(self):
        result = followup_usefulness(
            inputs="anything", outputs="anything", expectations="anything"
        )
        assert result.value == 0.0

    def test_feedback_name(self):
        result = followup_usefulness(inputs="test", outputs="{}", expectations=None)
        assert result.name == "followup_usefulness"


# ── media_analysis_accuracy tests ──


class TestMediaAnalysisAccuracy:
    def test_valid_complete_output(self):
        result = media_analysis_accuracy(
            inputs="test", outputs=_media_output(), expectations=None
        )
        assert result.value > 0.5

    def test_missing_extracted_text(self):
        out = _media_output(extracted_text="")
        result = media_analysis_accuracy(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_missing_usage_tags(self):
        out = _media_output(usage_tags=[])
        result = media_analysis_accuracy(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_with_matching_expectations(self):
        out = _media_output(usage_tags=["logo", "branding"])
        exp = json.dumps({"expected_tags": ["logo", "branding"]})
        result = media_analysis_accuracy(inputs="test", outputs=out, expectations=exp)
        assert result.value == 1.0

    def test_with_mismatched_expectations(self):
        out = _media_output(usage_tags=["logo"])
        exp = json.dumps({"expected_tags": ["website", "product"]})
        result = media_analysis_accuracy(inputs="test", outputs=out, expectations=exp)
        assert result.value < 1.0

    def test_none_output(self):
        result = media_analysis_accuracy(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0

    def test_feedback_name(self):
        result = media_analysis_accuracy(
            inputs="test", outputs=_media_output(), expectations=None
        )
        assert result.name == "media_analysis_accuracy"


# ── summary_faithfulness tests ──


class TestSummaryFaithfulness:
    def test_valid_complete_output(self):
        result = summary_faithfulness(
            inputs="test", outputs=_summary_output(), expectations=None
        )
        assert result.value == 1.0

    def test_missing_summary_text(self):
        out = _summary_output(summary="")
        result = summary_faithfulness(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_missing_key_moments(self):
        out = _summary_output(key_moments=[])
        result = summary_faithfulness(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_moments_without_timestamps(self):
        out = _summary_output(key_moments=[{"text": "Discussion point"}])
        result = summary_faithfulness(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_missing_speakers(self):
        out = _summary_output(speakers=[])
        result = summary_faithfulness(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_none_output(self):
        result = summary_faithfulness(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0

    def test_feedback_name(self):
        result = summary_faithfulness(
            inputs="test", outputs=_summary_output(), expectations=None
        )
        assert result.name == "summary_faithfulness"


# ── extraction_accuracy tests ──


class TestExtractionAccuracy:
    def test_valid_complete_output(self):
        result = extraction_accuracy(
            inputs="test", outputs=_extraction_output(), expectations=None
        )
        assert result.value > 0.5

    def test_empty_fields(self):
        out = _extraction_output(extracted_fields={})
        result = extraction_accuracy(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_fields_with_none_values(self):
        out = _extraction_output(
            extracted_fields={"legal_name": None, "industry": None}
        )
        result = extraction_accuracy(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_with_matching_expectations(self):
        out = _extraction_output(
            extracted_fields={"legal_name": "Acme Corp", "industry": "Tech"}
        )
        exp = json.dumps(
            {"admin_fields": {"legal_name": "Acme Corp", "industry": "Tech"}}
        )
        result = extraction_accuracy(inputs="test", outputs=out, expectations=exp)
        assert result.value == 1.0

    def test_with_mismatched_expectations(self):
        out = _extraction_output(extracted_fields={"legal_name": "Acme Ltd"})
        exp = json.dumps({"admin_fields": {"legal_name": "Acme Corporation"}})
        result = extraction_accuracy(inputs="test", outputs=out, expectations=exp)
        assert result.value < 1.0

    def test_none_output(self):
        result = extraction_accuracy(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0

    def test_feedback_name(self):
        result = extraction_accuracy(
            inputs="test", outputs=_extraction_output(), expectations=None
        )
        assert result.name == "extraction_accuracy"


# ── Scorer conformance ──


class TestOiaScorerConformance:
    def test_oia_scorers_list_has_eight_entries(self):
        assert len(OIA_SCORERS) == 8

    def test_all_are_scorer_instances(self):
        from mlflow.genai.scorers import Scorer

        for s in OIA_SCORERS:
            assert isinstance(s, Scorer), f"{s.name} is not a Scorer"

    def test_all_return_zero_on_none(self):
        for s in OIA_SCORERS:
            result = s(inputs="test", outputs=None, expectations=None)
            assert result.value == 0.0, f"{s.name} did not return 0.0 for None"

    def test_all_handle_invalid_json(self):
        for s in OIA_SCORERS:
            result = s(inputs="test", outputs="{{bad", expectations=None)
            assert result.value == 0.0, f"{s.name} did not return 0.0 for bad JSON"

    def test_all_values_in_range(self):
        outputs = [
            _research_output(),
            _questionnaire_output(),
            _stream_output(),
            _sufficiency_output(),
            json.dumps({"followups": []}),
            _media_output(),
            _summary_output(),
            _extraction_output(),
        ]
        for s, out in zip(OIA_SCORERS, outputs):
            result = s(inputs="test", outputs=out, expectations=None)
            assert (
                0.0 <= result.value <= 1.0
            ), f"{s.name} value {result.value} out of range"

    def test_all_accept_keyword_args(self):
        outputs = [
            _research_output(),
            _questionnaire_output(),
            _stream_output(),
            _sufficiency_output(),
            json.dumps({}),
            _media_output(),
            _summary_output(),
            _extraction_output(),
        ]
        for s, out in zip(OIA_SCORERS, outputs):
            result = s(inputs="test", outputs=out, expectations=None)
            assert result is not None, f"{s.name} returned None"
