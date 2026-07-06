"""Unit tests for optimization budgets registry (US-058).

Tests AGENT_BUDGETS, DEFAULT_BUDGET, and get_budget() — pure functions,
no external dependencies.
"""

from app.registries.optimization_budgets import (
    AGENT_BUDGETS,
    DEFAULT_BUDGET,
    get_budget,
)

ALL_15_AGENTS = [
    "mra",
    "cia",
    "apa",
    "tcia",
    "voca",
    "bpa",
    "baa",
    "bpv",
    "nta",
    "bsa",
    "caa",
    "cga",
    "adpub",
    "coa",
    "ila",
]

WF1_AGENTS = ["mra", "cia", "apa", "tcia", "voca"]


class TestOptimizationBudgets:
    """Tests for per-agent optimization budgets."""

    def test_all_15_agents_have_budgets(self):
        for code in ALL_15_AGENTS:
            assert code in AGENT_BUDGETS, f"Missing budget for agent '{code}'"

    def test_budget_count_is_15(self):
        assert len(AGENT_BUDGETS) == 15

    def test_get_budget_known_agent(self):
        assert get_budget("cga") == 500

    def test_get_budget_unknown_agent_returns_default(self):
        assert get_budget("xyz") == DEFAULT_BUDGET

    def test_get_budget_case_insensitive(self):
        assert get_budget("CGA") == get_budget("cga")

    def test_default_budget_is_200(self):
        assert DEFAULT_BUDGET == 200

    def test_all_budgets_positive(self):
        for code, budget in AGENT_BUDGETS.items():
            assert budget > 0, f"Budget for '{code}' must be positive"

    def test_wf3_agents_have_highest_budgets(self):
        cga_budget = AGENT_BUDGETS["cga"]
        for wf1_code in WF1_AGENTS:
            assert cga_budget >= AGENT_BUDGETS[wf1_code], (
                f"CGA budget ({cga_budget}) should be >= "
                f"{wf1_code} budget ({AGENT_BUDGETS[wf1_code]})"
            )

    def test_budget_values_are_integers(self):
        for code, budget in AGENT_BUDGETS.items():
            assert isinstance(budget, int), f"Budget for '{code}' must be int"

    def test_get_budget_empty_string(self):
        assert get_budget("") == DEFAULT_BUDGET
