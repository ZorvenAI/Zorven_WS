"""Unit tests for OIA onboarding intelligence scorers (L-03).

Covers all 8 scorers: perfect, partial, invalid, and edge inputs.
Output shapes match the actual OIA prompt templates in prompt_catalog.py.
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
# Each mirrors the actual prompt output format from prompt_catalog.py.


def _research_output(**overrides) -> str:
    data = {
        "facts": overrides.get(
            "facts",
            [
                {
                    "statement": "Revenue is $1M",
                    "source_url": "https://example.com",
                },
                {
                    "statement": "10 employees",
                    "source_url": "https://example.com/about",
                },
                {
                    "statement": "Founded in 2015",
                    "source_url": "https://example.com/history",
                },
            ],
        ),
        "competitors_seen": overrides.get("competitors_seen", ["CompetitorA"]),
        "digital_presence": overrides.get(
            "digital_presence",
            {
                "website": "https://acme.com",
                "social_profiles": [],
                "notes": "",
            },
        ),
        "open_unknowns": overrides.get(
            "open_unknowns",
            [
                "founding year unclear",
                "market share unknown",
            ],
        ),
    }
    data.update({k: v for k, v in overrides.items() if k not in data})
    return json.dumps(data)


def _questionnaire_output(**overrides) -> str:
    """Questionnaire prompt returns a bare JSON array."""
    questions = overrides.get(
        "questions",
        [
            {
                "text": "What is your brand voice?",
                "workflow_target": "WF2",
                "target_field": "brand_voice",
            },
            {
                "text": "Who is your target audience?",
                "workflow_target": "WF1",
                "target_field": "target_audience",
            },
            {
                "text": "What is your budget?",
                "workflow_target": "WF3",
                "target_field": "",
            },
        ],
    )
    return json.dumps(questions)


def _stream_output(**overrides) -> str:
    data = {
        "attachments": overrides.get(
            "attachments",
            [
                {
                    "question_id": "q1",
                    "relevance": 0.85,
                    "evidence": [
                        {
                            "recording_id": "r_01",
                            "t_start": 120.5,
                            "t_end": 123.8,
                        }
                    ],
                },
                {
                    "question_id": "q2",
                    "relevance": 0.72,
                    "evidence": [
                        {
                            "recording_id": "r_01",
                            "t_start": 200.0,
                            "t_end": 210.0,
                        }
                    ],
                },
            ],
        ),
        "adhoc_questions": overrides.get(
            "adhoc_questions",
            [
                {
                    "text": "What about social media?",
                    "t_start": 125.0,
                    "inferred_target_field": "social_channels",
                }
            ],
        ),
        "notable_facts": overrides.get("notable_facts", []),
    }
    data.update({k: v for k, v in overrides.items() if k not in data})
    return json.dumps(data)


def _sufficiency_output(**overrides) -> str:
    data = {
        "score": overrides.get("score", 0.85),
        "missing_aspects": overrides.get(
            "missing_aspects", ["founding year not mentioned"]
        ),
    }
    data.update({k: v for k, v in overrides.items() if k not in data})
    return json.dumps(data)


def _media_output(**overrides) -> str:
    data = {
        "caption": overrides.get("caption", "A business invoice from ACME Corp"),
        "doc_type": overrides.get("doc_type", "invoice"),
        "sensitivity_class": overrides.get("sensitivity_class", "FINANCIAL"),
    }
    data.update({k: v for k, v in overrides.items() if k not in data})
    return json.dumps(data)


def _summary_output(**overrides) -> str:
    data = {
        "text": overrides.get(
            "text",
            "Meeting covered brand strategy and target " "audience definition.",
        ),
        "key_moments": overrides.get(
            "key_moments",
            [
                {"t": 120.5, "label": "Brand voice discussion"},
                {"t": 300.0, "label": "Audience definition"},
            ],
        ),
    }
    data.update({k: v for k, v in overrides.items() if k not in data})
    return json.dumps(data)


def _extraction_output(**overrides) -> str:
    data = {
        "fields": overrides.get(
            "fields",
            [
                {
                    "field_name": "legal_name",
                    "value": "Acme Corp",
                    "confidence": 0.95,
                    "evidence": [
                        {
                            "recording_id": "r1",
                            "t_start": 12.5,
                            "t_end": 18.3,
                        }
                    ],
                },
                {
                    "field_name": "industry",
                    "value": "Technology",
                    "confidence": 0.88,
                    "evidence": [
                        {
                            "recording_id": "r1",
                            "t_start": 30.0,
                            "t_end": 35.0,
                        }
                    ],
                },
                {
                    "field_name": "founding_year",
                    "value": "2020",
                    "confidence": 0.70,
                    "evidence": [
                        {
                            "recording_id": "r1",
                            "t_start": 45.0,
                            "t_end": 50.0,
                        }
                    ],
                },
            ],
        ),
    }
    data.update({k: v for k, v in overrides.items() if k not in data})
    return json.dumps(data)


# ── research_factuality tests ──


class TestResearchFactuality:
    def test_valid_complete_output(self):
        result = research_factuality(
            inputs="test",
            outputs=_research_output(),
            expectations=None,
        )
        assert result.value == 1.0

    def test_missing_facts(self):
        out = _research_output(facts=[])
        result = research_factuality(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_facts_without_source_url(self):
        out = _research_output(facts=[{"statement": "Revenue is $1M"}])
        result = research_factuality(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_missing_unknowns(self):
        out = _research_output(open_unknowns=[])
        result = research_factuality(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_single_source_partial_diversity(self):
        out = _research_output(
            facts=[
                {
                    "statement": "A",
                    "source_url": "https://one.com",
                },
                {
                    "statement": "B",
                    "source_url": "https://one.com",
                },
            ]
        )
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
            inputs="test",
            outputs=_research_output(),
            expectations=None,
        )
        assert result.name == "research_factuality"

    def test_all_fields_missing(self):
        result = research_factuality(
            inputs="test",
            outputs=json.dumps({}),
            expectations=None,
        )
        assert result.value == 0.0


# ── questionnaire_coverage tests ──


class TestQuestionnaireCoverage:
    def test_valid_complete_output(self):
        result = questionnaire_coverage(
            inputs="test",
            outputs=_questionnaire_output(),
            expectations=None,
        )
        assert result.value == 1.0

    def test_empty_array(self):
        out = json.dumps([])
        result = questionnaire_coverage(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_questions_without_workflow_target(self):
        out = json.dumps(
            [
                {
                    "text": "What is your name?",
                    "target_field": "legal_name",
                }
            ]
        )
        result = questionnaire_coverage(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_questions_without_target_field(self):
        out = json.dumps(
            [
                {
                    "text": "What is your name?",
                    "workflow_target": "WF1",
                }
            ]
        )
        result = questionnaire_coverage(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_dict_wrapper_still_works(self):
        out = json.dumps(
            {
                "questions": [
                    {
                        "text": "Q?",
                        "workflow_target": "WF1",
                        "target_field": "x",
                    }
                ]
            }
        )
        result = questionnaire_coverage(inputs="test", outputs=out, expectations=None)
        assert result.value > 0.0

    def test_none_output(self):
        result = questionnaire_coverage(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0

    def test_feedback_name(self):
        result = questionnaire_coverage(
            inputs="test",
            outputs=_questionnaire_output(),
            expectations=None,
        )
        assert result.name == "questionnaire_coverage"


# ── stream_attachment tests ──


class TestStreamAttachment:
    def test_valid_complete_output(self):
        result = stream_attachment(
            inputs="test",
            outputs=_stream_output(),
            expectations=None,
        )
        assert result.value == 1.0

    def test_empty_attachments(self):
        out = _stream_output(attachments=[])
        result = stream_attachment(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_attachment_without_relevance(self):
        out = _stream_output(attachments=[{"question_id": "q1"}])
        result = stream_attachment(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_no_adhoc_questions(self):
        out = _stream_output(adhoc_questions=[])
        result = stream_attachment(inputs="test", outputs=out, expectations=None)
        assert result.value == 1.0

    def test_none_output(self):
        result = stream_attachment(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0

    def test_feedback_name(self):
        result = stream_attachment(
            inputs="test",
            outputs=_stream_output(),
            expectations=None,
        )
        assert result.name == "stream_attachment"


# ── sufficiency_agreement tests ──


class TestSufficiencyAgreement:
    def test_agrees_with_admin(self):
        out = _sufficiency_output(score=0.85)
        exp = json.dumps({"admin_sufficient": True})
        result = sufficiency_agreement(inputs="test", outputs=out, expectations=exp)
        assert result.value == 1.0

    def test_disagrees_with_admin(self):
        out = _sufficiency_output(score=0.85)
        exp = json.dumps({"admin_sufficient": False})
        result = sufficiency_agreement(inputs="test", outputs=out, expectations=exp)
        assert result.value == 0.0

    def test_low_score_agrees_insufficient(self):
        out = _sufficiency_output(score=0.2)
        exp = json.dumps({"admin_sufficient": False})
        result = sufficiency_agreement(inputs="test", outputs=out, expectations=exp)
        assert result.value == 1.0

    def test_no_expectations_with_missing_aspects(self):
        out = _sufficiency_output()
        result = sufficiency_agreement(inputs="test", outputs=out, expectations=None)
        assert result.value > 0.5

    def test_no_score_field(self):
        out = json.dumps({"missing_aspects": []})
        result = sufficiency_agreement(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_none_output(self):
        result = sufficiency_agreement(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0

    def test_feedback_name(self):
        result = sufficiency_agreement(
            inputs="test",
            outputs=_sufficiency_output(),
            expectations=None,
        )
        assert result.name == "sufficiency_agreement"


# ── followup_usefulness tests ──


class TestFollowupUsefulness:
    def test_stub_returns_zero(self):
        result = followup_usefulness(
            inputs="test",
            outputs=json.dumps({"followups": []}),
            expectations=None,
        )
        assert result.value == 0.0

    def test_stub_documents_gap(self):
        result = followup_usefulness(inputs="test", outputs="{}", expectations=None)
        assert "EVT-105" in result.rationale
        assert "G-04" in result.rationale

    def test_stub_returns_zero_with_any_input(self):
        result = followup_usefulness(
            inputs="anything",
            outputs="anything",
            expectations="anything",
        )
        assert result.value == 0.0

    def test_feedback_name(self):
        result = followup_usefulness(inputs="test", outputs="{}", expectations=None)
        assert result.name == "followup_usefulness"


# ── media_analysis_accuracy tests ──


class TestMediaAnalysisAccuracy:
    def test_valid_complete_output(self):
        result = media_analysis_accuracy(
            inputs="test",
            outputs=_media_output(),
            expectations=None,
        )
        assert result.value == 1.0

    def test_missing_caption(self):
        out = _media_output(caption="")
        result = media_analysis_accuracy(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_missing_doc_type(self):
        out = _media_output(doc_type="")
        result = media_analysis_accuracy(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_invalid_doc_type(self):
        out = _media_output(doc_type="unknown_type")
        result = media_analysis_accuracy(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_valid_sensitivity_classes(self):
        for cls in ["GENERAL", "IDENTITY", "FINANCIAL"]:
            out = _media_output(sensitivity_class=cls)
            result = media_analysis_accuracy(
                inputs="test", outputs=out, expectations=None
            )
            assert result.value == 1.0

    def test_with_matching_expectations(self):
        out = _media_output(
            doc_type="invoice",
            sensitivity_class="FINANCIAL",
        )
        exp = json.dumps(
            {
                "doc_type": "invoice",
                "sensitivity_class": "FINANCIAL",
            }
        )
        result = media_analysis_accuracy(inputs="test", outputs=out, expectations=exp)
        assert result.value == 1.0

    def test_with_mismatched_expectations(self):
        out = _media_output(
            doc_type="invoice",
            sensitivity_class="GENERAL",
        )
        exp = json.dumps(
            {
                "doc_type": "receipt",
                "sensitivity_class": "FINANCIAL",
            }
        )
        result = media_analysis_accuracy(inputs="test", outputs=out, expectations=exp)
        assert result.value < 1.0

    def test_none_output(self):
        result = media_analysis_accuracy(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0

    def test_feedback_name(self):
        result = media_analysis_accuracy(
            inputs="test",
            outputs=_media_output(),
            expectations=None,
        )
        assert result.name == "media_analysis_accuracy"


# ── summary_faithfulness tests ──


class TestSummaryFaithfulness:
    def test_valid_complete_output(self):
        result = summary_faithfulness(
            inputs="test",
            outputs=_summary_output(),
            expectations=None,
        )
        assert result.value == 1.0

    def test_missing_text(self):
        out = _summary_output(text="")
        result = summary_faithfulness(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_missing_key_moments(self):
        out = _summary_output(key_moments=[])
        result = summary_faithfulness(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_moments_without_timestamps(self):
        out = _summary_output(key_moments=[{"label": "Discussion point"}])
        result = summary_faithfulness(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_moments_without_labels(self):
        out = _summary_output(key_moments=[{"t": 120.5}])
        result = summary_faithfulness(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_none_output(self):
        result = summary_faithfulness(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0

    def test_feedback_name(self):
        result = summary_faithfulness(
            inputs="test",
            outputs=_summary_output(),
            expectations=None,
        )
        assert result.name == "summary_faithfulness"


# ── extraction_accuracy tests ──


class TestExtractionAccuracy:
    def test_valid_complete_output(self):
        result = extraction_accuracy(
            inputs="test",
            outputs=_extraction_output(),
            expectations=None,
        )
        assert result.value > 0.5

    def test_empty_fields(self):
        out = _extraction_output(fields=[])
        result = extraction_accuracy(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_fields_with_none_values(self):
        out = _extraction_output(
            fields=[
                {
                    "field_name": "legal_name",
                    "value": None,
                    "confidence": 0.5,
                    "evidence": [],
                },
                {
                    "field_name": "industry",
                    "value": None,
                    "confidence": 0.5,
                    "evidence": [],
                },
            ]
        )
        result = extraction_accuracy(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_with_matching_expectations(self):
        out = _extraction_output(
            fields=[
                {
                    "field_name": "legal_name",
                    "value": "Acme Corp",
                    "confidence": 0.95,
                    "evidence": [],
                },
                {
                    "field_name": "industry",
                    "value": "Tech",
                    "confidence": 0.9,
                    "evidence": [],
                },
            ]
        )
        exp = json.dumps(
            {
                "admin_fields": {
                    "legal_name": "Acme Corp",
                    "industry": "Tech",
                }
            }
        )
        result = extraction_accuracy(inputs="test", outputs=out, expectations=exp)
        assert result.value == 1.0

    def test_with_mismatched_expectations(self):
        out = _extraction_output(
            fields=[
                {
                    "field_name": "legal_name",
                    "value": "Acme Ltd",
                    "confidence": 0.8,
                    "evidence": [],
                }
            ]
        )
        exp = json.dumps({"admin_fields": {"legal_name": "Acme Corporation"}})
        result = extraction_accuracy(inputs="test", outputs=out, expectations=exp)
        assert result.value < 1.0

    def test_none_output(self):
        result = extraction_accuracy(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0

    def test_feedback_name(self):
        result = extraction_accuracy(
            inputs="test",
            outputs=_extraction_output(),
            expectations=None,
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
            result = s(
                inputs="test",
                outputs="{{bad",
                expectations=None,
            )
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
