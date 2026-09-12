"""
US-058 Integration Tests — Scorer and Registry Coverage Cross-Checks.

Validates that scorer functions, budget registries, optimization groups,
and skill definitions are consistent across all 15 agents. No mocks.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "prompt-optimization-svc"))

from app.registries.optimization_budgets import AGENT_BUDGETS, get_budget  # noqa: E402
from app.registries.optimization_groups import OPTIMIZATION_GROUPS  # noqa: E402
from app.scorers.common.json_compliance import json_compliance  # noqa: E402
from app.scorers.common.pii_safety import pii_safety  # noqa: E402
from app.scorers.common.token_efficiency import token_efficiency  # noqa: E402
from app.services.skill_registry_reader import (  # noqa: E402
    AGENT_SERVICE_DIRS,
    SkillRegistryReader,
)


class TestScorerCoverageIntegration:
    """Cross-service scorer and registry consistency checks."""

    def test_all_common_scorers_return_feedback(self):
        """All common scorers return Feedback with correct name and value."""
        from mlflow.entities.assessment import Feedback

        scorers = [
            ("json_compliance", json_compliance),
            ("pii_safety", pii_safety),
            ("token_efficiency", token_efficiency),
        ]
        for name, scorer_fn in scorers:
            result = scorer_fn(
                inputs="test input", outputs="test output", expectations=None
            )
            assert isinstance(result, Feedback), f"{name} didn't return Feedback"
            assert result.name == name
            assert 0.0 <= result.value <= 1.0

    def test_scorer_handles_none_gracefully(self):
        """All common scorers handle None output without crashing."""
        scorers = [json_compliance, pii_safety, token_efficiency]
        for scorer_fn in scorers:
            result = scorer_fn(inputs="test", outputs=None, expectations=None)
            assert 0.0 <= result.value <= 1.0

    def test_optimization_budgets_cover_all_agents(self):
        """Budget registry covers every agent in AGENT_SERVICE_DIRS."""
        for agent_code in AGENT_SERVICE_DIRS:
            budget = get_budget(agent_code)
            assert budget > 0, f"No positive budget for agent '{agent_code}'"
            assert agent_code in AGENT_BUDGETS

    def test_optimization_groups_cover_all_agents(self):
        """Union of all optimization groups covers all 15 workflow agents.

        Utility agents (e.g. OIA) may also appear in optimization groups
        but are not required to — the invariant is that every workflow
        agent has a group, not that no utility agent does.
        """
        from app.services.skill_registry_reader import ALL_AGENT_CODES

        covered = set()
        for group in OPTIMIZATION_GROUPS.values():
            covered.update(group.agent_codes)
        workflow_agents = set(AGENT_SERVICE_DIRS.keys())
        missing = workflow_agents - covered
        unknown = covered - ALL_AGENT_CODES
        assert not missing, f"Workflow agents without an optimization group: {missing}"
        assert not unknown, f"Agent codes in groups but not in any registry: {unknown}"

    def test_skill_definitions_load_all_agents(self):
        """SkillRegistryReader loads all 15 agents' skills.yaml successfully."""
        reader = SkillRegistryReader(repo_root=REPO_ROOT)
        for agent_code in AGENT_SERVICE_DIRS:
            skills_file = reader.load_skills(agent_code)
            assert len(skills_file.skills) > 0, f"Agent '{agent_code}' has no skills"
            for skill in skills_file.skills:
                assert skill.skill_id.startswith("SKL-")
                assert skill.timeout_ms >= 0

    def test_guardrail_chain_runs_all_checks(self):
        """run_candidate_guardrails with valid preamble-free template runs all checks."""
        from app.logic.guardrails import run_candidate_guardrails

        result = run_candidate_guardrails(
            candidate_text="You are a helpful assistant.",
            base_text="You are an assistant.",
            current_cost_usd=0.0,
        )
        assert result.all_passed is True
        guardrail_ids = [r.guardrail_id for r in result.results]
        # At minimum OPT-02, OPT-06, OPT-09, OPT-12 should run
        assert "OPT-02" in guardrail_ids
        assert "OPT-06" in guardrail_ids
        assert "OPT-09" in guardrail_ids
        assert "OPT-12" in guardrail_ids
