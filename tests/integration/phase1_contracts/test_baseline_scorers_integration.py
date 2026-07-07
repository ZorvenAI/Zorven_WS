"""
US-054 Integration Tests — Baseline Scorers Cross-Service Validation.

Exercises BaselineScorerFactory against all 179 real skills across
15 agent services. No mocks.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "prompt-optimization-svc"))

from app.registries.prompt_catalog import PROMPT_CATALOG  # noqa: E402
from app.scorers.baseline.factory import BaselineScorerFactory  # noqa: E402
from app.services.skill_registry_reader import (  # noqa: E402
    AGENT_SERVICE_DIRS,
    SkillRegistryReader,
)


def _make_factory() -> tuple[BaselineScorerFactory, SkillRegistryReader]:
    reader = SkillRegistryReader(repo_root=REPO_ROOT)
    return BaselineScorerFactory(reader), reader


class TestBaselineScorersIntegration:
    """Cross-service integration tests for baseline scorer generation."""

    def test_scorers_for_all_179_skills(self):
        """Generate scorers for every skill, verify non-empty."""
        factory, reader = _make_factory()
        empty_skills = []
        for agent_code in sorted(AGENT_SERVICE_DIRS.keys()):
            skills_file = reader.load_skills(agent_code)
            for skill in skills_file.skills:
                scorers = factory.create_scorers(skill)
                if len(scorers) == 0:
                    empty_skills.append(skill.skill_id)
        assert empty_skills == [], f"Skills with no scorers: {empty_skills}"

    def test_scorer_names_are_unique_per_skill(self):
        """No duplicate scorer names within a skill."""
        factory, reader = _make_factory()
        duplicates = []
        for agent_code in sorted(AGENT_SERVICE_DIRS.keys()):
            skills_file = reader.load_skills(agent_code)
            for skill in skills_file.skills:
                scorers = factory.create_scorers(skill)
                names = [s.__name__ for s in scorers]
                if len(names) != len(set(names)):
                    seen = set()
                    dupes = [n for n in names if n in seen or seen.add(n)]
                    duplicates.append(f"{skill.skill_id}: {dupes}")
        assert duplicates == [], f"Duplicate scorer names:\n" + "\n".join(duplicates)

    def test_scorers_return_feedback_for_empty_output(self):
        """All scorers handle empty string gracefully."""
        factory, reader = _make_factory()
        errors = []
        for agent_code in sorted(AGENT_SERVICE_DIRS.keys()):
            skills_file = reader.load_skills(agent_code)
            first_skill = skills_file.skills[0]
            scorers = factory.create_scorers(first_skill)
            for scorer in scorers:
                try:
                    result = scorer(inputs={}, outputs="")
                    if result.value is None:
                        errors.append(f"{scorer.__name__}: returned None value")
                except Exception as exc:
                    errors.append(f"{scorer.__name__}: raised {exc}")
        assert errors == [], f"Scorer errors:\n" + "\n".join(errors)

    def test_scorers_return_feedback_for_valid_json(self):
        """All scorers handle valid JSON without raising."""
        factory, reader = _make_factory()
        valid_output = json.dumps({"test_field": "test_value", "count": 42})
        errors = []
        for agent_code in sorted(AGENT_SERVICE_DIRS.keys()):
            skills_file = reader.load_skills(agent_code)
            first_skill = skills_file.skills[0]
            scorers = factory.create_scorers(first_skill)
            for scorer in scorers:
                try:
                    result = scorer(inputs={}, outputs=valid_output)
                    if result.value is None:
                        errors.append(f"{scorer.__name__}: returned None value")
                except Exception as exc:
                    errors.append(f"{scorer.__name__}: raised {exc}")
        assert errors == [], f"Scorer errors:\n" + "\n".join(errors)

    def test_scorer_values_in_valid_range(self):
        """All returned values are in [0.0, 1.0]."""
        factory, reader = _make_factory()
        outputs_to_test = [
            "",
            "not json",
            json.dumps({}),
            json.dumps({"field": "value"}),
        ]
        violations = []
        for agent_code in sorted(AGENT_SERVICE_DIRS.keys()):
            skills_file = reader.load_skills(agent_code)
            first_skill = skills_file.skills[0]
            scorers = factory.create_scorers(first_skill)
            for scorer in scorers:
                for output in outputs_to_test:
                    result = scorer(inputs={}, outputs=output)
                    if not (0.0 <= result.value <= 1.0):
                        violations.append(
                            f"{scorer.__name__}: value={result.value} "
                            f"for output={output!r}"
                        )
        assert violations == [], f"Out-of-range values:\n" + "\n".join(violations)

    def test_prompt_catalog_scorers_resolve(self):
        """Non-system catalog prompts generate scorers where skills resolve."""
        factory, _ = _make_factory()
        resolved_count = 0
        for entry in PROMPT_CATALOG:
            if entry.tags.get("prompt_type") == "system":
                continue
            agent_code = entry.tags.get("agent_code", "")
            scorers = factory.create_scorers_for_prompt(agent_code, entry.name)
            if scorers:
                resolved_count += 1
        assert resolved_count > 0
