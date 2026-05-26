"""Unit tests for context variable registry (US-031)."""

from app.registries.context_variables import (
    CONTEXT_REGISTRY,
    SHARED_VARIABLES,
    VALID_PLACEHOLDER_NAMES,
    ContextVariable,
    get_agent_variable_names,
    get_required_variables,
    get_variables_for_agent,
    validate_template_against_registry,
)
from app.registries.prompt_catalog import AGENT_PORTS


class TestRegistryCompleteness:
    """AC-1: Registry populated for all 15 agents."""

    def test_registry_has_at_least_39_variables(self):
        assert len(CONTEXT_REGISTRY) >= 39

    def test_all_15_agents_have_variables(self):
        for agent in AGENT_PORTS:
            vars_for_agent = get_variables_for_agent(agent)
            assert (
                len(vars_for_agent) >= 5
            ), f"Agent {agent} has only {len(vars_for_agent)} variables"

    def test_valid_placeholder_names_matches_registry(self):
        assert VALID_PLACEHOLDER_NAMES == set(CONTEXT_REGISTRY.keys())

    def test_all_names_start_with_context(self):
        for name in CONTEXT_REGISTRY:
            assert name.startswith(
                "context."
            ), f"Variable '{name}' missing context. prefix"

    def test_all_sources_valid(self):
        valid_sources = {"onboarding", "runtime", "upstream"}
        for var in CONTEXT_REGISTRY.values():
            assert (
                var.source in valid_sources
            ), f"Variable {var.name} has invalid source '{var.source}'"

    def test_context_variable_is_frozen(self):
        var = ContextVariable("context.test", source="runtime")
        try:
            var.name = "changed"
            assert False, "Should not be able to modify frozen dataclass"
        except AttributeError:
            pass  # Expected — frozen dataclass


class TestGetVariablesForAgent:
    def test_cga_includes_shared(self):
        vars_for_cga = get_variables_for_agent("cga")
        shared_names = {v.name for v in SHARED_VARIABLES}
        agent_names = {v.name for v in vars_for_cga}
        assert shared_names.issubset(agent_names)

    def test_mra_includes_shared(self):
        vars_for_mra = get_variables_for_agent("mra")
        shared_names = {v.name for v in SHARED_VARIABLES}
        agent_names = {v.name for v in vars_for_mra}
        assert shared_names.issubset(agent_names)

    def test_cga_has_campaign_blueprint(self):
        names = get_agent_variable_names("cga")
        assert "context.campaign_blueprint" in names

    def test_coa_has_performance_data(self):
        names = get_agent_variable_names("coa")
        assert "context.performance_data" in names

    def test_case_insensitive(self):
        vars_lower = get_variables_for_agent("cga")
        vars_upper = get_variables_for_agent("CGA")
        assert len(vars_lower) == len(vars_upper)

    def test_unknown_agent_gets_only_shared(self):
        vars_for_unknown = get_variables_for_agent("nonexistent")
        shared_count = len(SHARED_VARIABLES)
        assert len(vars_for_unknown) == shared_count


class TestGetRequiredVariables:
    def test_brand_name_is_required(self):
        required = get_required_variables("mra")
        names = {v.name for v in required}
        assert "context.brand_name" in names

    def test_industry_is_required(self):
        required = get_required_variables("cga")
        names = {v.name for v in required}
        assert "context.industry" in names

    def test_required_subset_of_all(self):
        all_vars = get_variables_for_agent("bpa")
        required = get_required_variables("bpa")
        assert len(required) <= len(all_vars)


class TestGetAgentVariableNames:
    def test_returns_set_of_strings(self):
        names = get_agent_variable_names("cga")
        assert isinstance(names, set)
        for name in names:
            assert isinstance(name, str)

    def test_non_empty_for_all_agents(self):
        for agent in AGENT_PORTS:
            names = get_agent_variable_names(agent)
            assert len(names) >= 5


class TestValidateTemplateAgainstRegistry:
    """AC-3: validate placeholders are declared."""

    def test_valid_template_no_violations(self):
        template = "Analyze {{context.brand_name}} in {{context.industry}}"
        violations = validate_template_against_registry(template, "mra")
        assert violations == []

    def test_undeclared_placeholder_violation(self):
        template = "Use {{context.nonexistent_var}} for analysis"
        violations = validate_template_against_registry(template, "mra")
        assert len(violations) == 1
        assert "nonexistent_var" in violations[0]

    def test_empty_template_no_violations(self):
        violations = validate_template_against_registry("", "mra")
        assert violations == []

    def test_no_placeholders_no_violations(self):
        violations = validate_template_against_registry("Plain text", "mra")
        assert violations == []

    def test_multiple_undeclared(self):
        template = "{{context.foo}} and {{context.bar}}"
        violations = validate_template_against_registry(template, "mra")
        assert len(violations) == 2
