"""
US-054 Unit Tests — Baseline Scorers.

All tests use real SkillRegistryReader loading real skills.yaml files.
No mocks.
"""

import json
from pathlib import Path

import pytest

from app.scorers.baseline.checks import (
    make_enum_compliance_scorer,
    make_field_presence_scorer,
    make_max_length_scorer,
    make_schema_completeness_scorer,
)
from app.scorers.baseline.factory import BaselineScorerFactory
from app.services.skill_registry_reader import (
    AGENT_SERVICE_DIRS,
    SkillRegistryReader,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def reader():
    r = SkillRegistryReader(repo_root=REPO_ROOT)
    yield r
    r.clear_cache()


@pytest.fixture
def factory(reader):
    return BaselineScorerFactory(reader)


ALL_AGENT_CODES = sorted(AGENT_SERVICE_DIRS.keys())


# ---------------------------------------------------------------------------
# Field presence scorer
# ---------------------------------------------------------------------------


class TestFieldPresenceScorer:
    def test_returns_1_when_present(self):
        scorer = make_field_presence_scorer("query", "SKL-MRA-01")
        result = scorer(inputs={}, outputs=json.dumps({"query": "test"}))
        assert result.value == 1.0

    def test_returns_0_when_missing(self):
        scorer = make_field_presence_scorer("query", "SKL-MRA-01")
        result = scorer(inputs={}, outputs=json.dumps({"other": "value"}))
        assert result.value == 0.0
        assert "missing" in result.rationale.lower()

    def test_returns_0_for_invalid_json(self):
        scorer = make_field_presence_scorer("query", "SKL-MRA-01")
        result = scorer(inputs={}, outputs="not json")
        assert result.value == 0.0

    def test_returns_0_for_none_output(self):
        scorer = make_field_presence_scorer("query", "SKL-MRA-01")
        result = scorer(inputs={}, outputs=None)
        assert result.value == 0.0


# ---------------------------------------------------------------------------
# Max length scorer
# ---------------------------------------------------------------------------


class TestMaxLengthScorer:
    def test_returns_1_when_within_limit(self):
        scorer = make_max_length_scorer("title", 100, "SKL-CGA-01")
        result = scorer(inputs={}, outputs=json.dumps({"title": "Short title"}))
        assert result.value == 1.0

    def test_returns_penalty_when_over(self):
        scorer = make_max_length_scorer("title", 10, "SKL-CGA-01")
        result = scorer(
            inputs={}, outputs=json.dumps({"title": "This is a very long title"})
        )
        assert 0.0 < result.value < 1.0
        assert "exceeds" in result.rationale.lower()

    def test_returns_1_when_field_missing(self):
        scorer = make_max_length_scorer("title", 100, "SKL-CGA-01")
        result = scorer(inputs={}, outputs=json.dumps({"other": "value"}))
        assert result.value == 1.0
        assert "skipped" in result.rationale.lower()

    def test_returns_0_for_invalid_json(self):
        scorer = make_max_length_scorer("title", 100, "SKL-CGA-01")
        result = scorer(inputs={}, outputs="not json")
        assert result.value == 0.0


# ---------------------------------------------------------------------------
# Enum compliance scorer
# ---------------------------------------------------------------------------


class TestEnumComplianceScorer:
    def test_returns_1_for_valid_value(self):
        scorer = make_enum_compliance_scorer(
            "status", ["active", "paused", "completed"], "SKL-COA-01"
        )
        result = scorer(inputs={}, outputs=json.dumps({"status": "active"}))
        assert result.value == 1.0

    def test_returns_0_for_invalid_value(self):
        scorer = make_enum_compliance_scorer(
            "status", ["active", "paused", "completed"], "SKL-COA-01"
        )
        result = scorer(inputs={}, outputs=json.dumps({"status": "unknown"}))
        assert result.value == 0.0
        assert "not in allowed" in result.rationale.lower()

    def test_returns_0_for_missing_field(self):
        scorer = make_enum_compliance_scorer(
            "status", ["active", "paused"], "SKL-COA-01"
        )
        result = scorer(inputs={}, outputs=json.dumps({"other": "value"}))
        assert result.value == 0.0


# ---------------------------------------------------------------------------
# Schema completeness scorer
# ---------------------------------------------------------------------------


class TestSchemaCompletenessScorer:
    def test_all_present(self):
        scorer = make_schema_completeness_scorer(
            ["query", "results", "sources"], "SKL-MRA-01"
        )
        output = json.dumps({"query": "q", "results": [], "sources": []})
        result = scorer(inputs={}, outputs=output)
        assert result.value == 1.0

    def test_partial(self):
        scorer = make_schema_completeness_scorer(
            ["a", "b", "c", "d", "e"], "SKL-MRA-01"
        )
        output = json.dumps({"a": 1, "b": 2, "c": 3})
        result = scorer(inputs={}, outputs=output)
        assert result.value == pytest.approx(0.6)

    def test_none_present(self):
        scorer = make_schema_completeness_scorer(["a", "b", "c"], "SKL-MRA-01")
        output = json.dumps({"x": 1})
        result = scorer(inputs={}, outputs=output)
        assert result.value == 0.0

    def test_empty_output(self):
        scorer = make_schema_completeness_scorer(["a", "b"], "SKL-MRA-01")
        result = scorer(inputs={}, outputs="not json")
        assert result.value == 0.0


# ---------------------------------------------------------------------------
# BaselineScorerFactory
# ---------------------------------------------------------------------------


class TestBaselineScorerFactory:
    def test_create_scorers_returns_list(self, factory, reader):
        skill = reader.get_skill("mra", "SKL-MRA-01")
        scorers = factory.create_scorers(skill)
        assert len(scorers) > 0
        assert all(callable(s) for s in scorers)

    def test_create_scorers_includes_completeness(self, factory, reader):
        skill = reader.get_skill("mra", "SKL-MRA-01")
        scorers = factory.create_scorers(skill)
        names = [s.__name__ for s in scorers]
        completeness = [n for n in names if "schema_completeness" in n]
        assert len(completeness) == 1

    def test_create_scorers_for_prompt_known(self, factory):
        scorers = factory.create_scorers_for_prompt("mra", "zorven-wf1-mra-synthesis")
        assert len(scorers) > 0

    def test_create_scorers_for_prompt_unknown_returns_empty(self, factory):
        scorers = factory.create_scorers_for_prompt("mra", "zorven-wf1-mra-nonexistent")
        assert scorers == []

    @pytest.mark.parametrize("agent_code", ALL_AGENT_CODES)
    def test_all_15_agents_first_skill_generates_scorers(
        self, factory, reader, agent_code
    ):
        skills_file = reader.load_skills(agent_code)
        first_skill = skills_file.skills[0]
        scorers = factory.create_scorers(first_skill)
        # At minimum, schema_completeness is always generated
        assert len(scorers) >= 1
