"""Tests for template-context separation pattern (US-016)."""

import pytest

from app.logic.placeholder_validator import (
    extract_placeholders,
    validate_template_placeholders,
)
from app.registries.context_variables import (
    CONTEXT_REGISTRY,
    SHARED_VARIABLES,
    VALID_PLACEHOLDER_NAMES,
    WF1_VARIABLES,
    WF2_VARIABLES,
    WF3_VARIABLES,
)
from app.registries.prompt_catalog import PROMPT_CATALOG
from app.services.context_builder import build_context_from_onboarding


# ------------------------------------------------------------------
# Context builder (AC-1)
# ------------------------------------------------------------------


class TestBuildContextFromOnboarding:
    """AC-1: Agents construct context via build_context_from_onboarding."""

    def test_onboarding_produces_context_keys(self):
        ctx = build_context_from_onboarding(
            {"brand_name": "Acme", "industry": "tech"}
        )
        assert ctx["context.brand_name"] == "Acme"
        assert ctx["context.industry"] == "tech"

    def test_company_name_maps_to_brand_name(self):
        ctx = build_context_from_onboarding({"company_name": "Acme"})
        assert ctx["context.brand_name"] == "Acme"

    def test_all_values_stringified(self):
        ctx = build_context_from_onboarding(
            {"brand_name": "Test"},
            runtime_data={"budget": 50000, "count": 5},
        )
        assert ctx["context.budget"] == "50000"
        assert ctx["context.count"] == "5"

    def test_runtime_data_merged(self):
        ctx = build_context_from_onboarding(
            {"brand_name": "Test"},
            runtime_data={"query": "market size"},
        )
        assert ctx["context.query"] == "market size"

    def test_upstream_data_merged(self):
        ctx = build_context_from_onboarding(
            {"brand_name": "Test"},
            upstream_data={"market_research": "MRA output"},
        )
        assert ctx["context.market_research"] == "MRA output"

    def test_context_prefix_preserved(self):
        ctx = build_context_from_onboarding(
            {"brand_name": "Test"},
            runtime_data={"context.query": "already prefixed"},
        )
        assert ctx["context.query"] == "already prefixed"

    def test_none_values_excluded(self):
        ctx = build_context_from_onboarding(
            {"brand_name": "Test", "brand_voice": None}
        )
        assert "context.brand_voice" not in ctx

    def test_none_runtime_values_excluded(self):
        """None values in runtime data are skipped, not stringified."""
        ctx = build_context_from_onboarding(
            {"brand_name": "Test"},
            runtime_data={"query": "valid", "budget": None},
        )
        assert ctx["context.query"] == "valid"
        assert "context.budget" not in ctx

    def test_none_upstream_values_excluded(self):
        ctx = build_context_from_onboarding(
            {"brand_name": "Test"},
            upstream_data={"market_research": "data", "positioning": None},
        )
        assert ctx["context.market_research"] == "data"
        assert "context.positioning" not in ctx

    def test_empty_onboarding_produces_empty_context(self):
        ctx = build_context_from_onboarding({})
        assert len(ctx) == 0


# ------------------------------------------------------------------
# Placeholder validator (AC-2)
# ------------------------------------------------------------------


class TestPlaceholderValidator:
    """AC-2: Templates contain only {context.*} placeholders."""

    def test_valid_template_passes(self):
        template = "Analyze {context.brand_name} in {context.industry}"
        violations = validate_template_placeholders(template)
        assert violations == []

    def test_non_context_placeholder_rejected(self):
        template = "Hello {user_name}, welcome to {context.brand_name}"
        violations = validate_template_placeholders(template)
        assert len(violations) == 1
        assert "user_name" in violations[0]

    def test_multiple_violations(self):
        template = "{name} works at {company} in {context.industry}"
        violations = validate_template_placeholders(template)
        assert len(violations) == 2

    def test_mlflow_double_braces_validated(self):
        """MLflow {{context.var}} placeholders are also validated."""
        template = "Use {{context.brand_name}} for MLflow"
        violations = validate_template_placeholders(template)
        assert violations == []

    def test_mlflow_non_context_rejected(self):
        template = "Use {{user_name}} in template"
        violations = validate_template_placeholders(template)
        assert len(violations) == 1
        assert "user_name" in violations[0]

    def test_no_placeholders_valid(self):
        template = "Plain text without any placeholders"
        violations = validate_template_placeholders(template)
        assert violations == []

    def test_registry_check_rejects_unknown(self):
        template = "Check {context.nonexistent_variable}"
        violations = validate_template_placeholders(
            template, registry=VALID_PLACEHOLDER_NAMES
        )
        assert len(violations) == 1
        assert "not in context variable registry" in violations[0]

    def test_empty_registry_rejects_all(self):
        """Explicit empty registry rejects all placeholders."""
        template = "Check {context.brand_name}"
        violations = validate_template_placeholders(
            template, registry=set()
        )
        assert len(violations) == 1


class TestExtractPlaceholders:
    """Test placeholder extraction."""

    def test_single_brace_placeholder(self):
        assert extract_placeholders("{context.brand_name}") == {
            "context.brand_name"
        }

    def test_double_brace_placeholder(self):
        """MLflow {{var}} syntax is extracted."""
        assert extract_placeholders("{{context.brand_name}}") == {
            "context.brand_name"
        }

    def test_multiple_placeholders(self):
        result = extract_placeholders(
            "{context.brand_name} in {context.industry}"
        )
        assert result == {"context.brand_name", "context.industry"}

    def test_mixed_single_and_double(self):
        result = extract_placeholders(
            "{context.a} and {{context.b}}"
        )
        assert result == {"context.a", "context.b"}

    def test_no_placeholders(self):
        assert extract_placeholders("plain text") == set()


# ------------------------------------------------------------------
# Catalog template validation (AC-2)
# ------------------------------------------------------------------


class TestCatalogTemplatesUseContextOnly:
    """AC-2: All 48 catalog templates use only {context.*} placeholders."""

    @pytest.mark.parametrize("entry", PROMPT_CATALOG, ids=lambda e: e.name)
    def test_template_uses_only_context_placeholders(self, entry):
        violations = validate_template_placeholders(entry.template)
        assert violations == [], (
            f"{entry.name} has non-context placeholders: {violations}"
        )


# ------------------------------------------------------------------
# Context variable registry (AC-3)
# ------------------------------------------------------------------


class TestContextRegistry:
    """AC-3: Placeholder names match the registry in §7.5.5."""

    def test_registry_has_shared_variables(self):
        for var in SHARED_VARIABLES:
            assert var.name in CONTEXT_REGISTRY

    def test_registry_has_wf1_variables(self):
        for var in WF1_VARIABLES:
            assert var.name in CONTEXT_REGISTRY

    def test_registry_has_wf2_variables(self):
        for var in WF2_VARIABLES:
            assert var.name in CONTEXT_REGISTRY

    def test_registry_has_wf3_variables(self):
        for var in WF3_VARIABLES:
            assert var.name in CONTEXT_REGISTRY

    def test_all_variables_start_with_context(self):
        for name in CONTEXT_REGISTRY:
            assert name.startswith("context."), f"{name} missing context. prefix"

    def test_required_variables_present(self):
        required = [v for v in CONTEXT_REGISTRY.values() if v.required]
        assert len(required) >= 2  # brand_name, industry at minimum

    def test_catalog_placeholders_in_registry(self):
        """All placeholders used in catalog templates exist in registry."""
        missing = set()
        for entry in PROMPT_CATALOG:
            placeholders = extract_placeholders(entry.template)
            for ph in placeholders:
                if ph not in VALID_PLACEHOLDER_NAMES:
                    missing.add(ph)
        assert missing == set(), (
            f"Catalog uses unregistered placeholders: {missing}"
        )


# ------------------------------------------------------------------
# Synthetic data in golden datasets (AC-4)
# ------------------------------------------------------------------


class TestSyntheticData:
    """AC-4: Optimization inputs use synthetic data, not real tenant data."""

    def test_catalog_templates_have_no_real_names(self):
        """Templates should not contain real company/person names."""
        real_names = {
            "John", "Jane", "Google", "Apple", "Microsoft",
            "Amazon", "Facebook", "Twitter",
        }
        for entry in PROMPT_CATALOG:
            for name in real_names:
                assert name not in entry.template, (
                    f"{entry.name} contains real name '{name}'"
                )

    def test_context_builder_stringifies_all(self):
        """All context values are strings — no raw objects leak."""
        ctx = build_context_from_onboarding(
            {"brand_name": "Test", "industry": "tech"},
            runtime_data={"budget": 50000, "items": ["a", "b"]},
        )
        for key, value in ctx.items():
            assert isinstance(value, str), (
                f"{key} is {type(value).__name__}, expected str"
            )
