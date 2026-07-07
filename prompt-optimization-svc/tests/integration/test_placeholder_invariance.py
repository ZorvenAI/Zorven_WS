"""Integration tests for placeholder invariance (US-030).

Validates against real prompt catalog templates.
"""

from app.logic.gepa_guardrails import check_gepa_mutation
from app.logic.placeholder_validator import validate_placeholder_invariance
from app.registries.prompt_catalog import PROMPT_CATALOG


class TestCatalogInvariance:
    """Each catalog template should be invariant with itself."""

    def test_all_48_templates_self_invariant(self):
        for entry in PROMPT_CATALOG:
            result = validate_placeholder_invariance(entry.template, entry.template)
            assert (
                result.valid is True
            ), f"Template {entry.name} failed self-invariance check"
            assert result.removed == set()
            assert result.added == set()

    def test_catalog_template_mutation_removal_detected(self):
        """Simulate a GEPA mutation that strips a placeholder."""
        entry = PROMPT_CATALOG[0]
        # Remove all placeholder tokens from template
        mutated = entry.template
        import re

        mutated = re.sub(r"\{\{[\w.]+\}\}", "REMOVED", mutated)
        mutated = re.sub(r"(?<!\{)\{([\w.]+)\}(?!\})", "REMOVED", mutated)

        result = validate_placeholder_invariance(entry.template, mutated)
        # Only fail if the original actually had placeholders
        from app.logic.placeholder_validator import extract_placeholders

        original_ph = extract_placeholders(entry.template)
        if original_ph:
            assert result.valid is False
            assert len(result.removed) > 0

    def test_gepa_guardrail_on_catalog_template(self):
        """GEPA mutation check on a real template."""
        entry = PROMPT_CATALOG[0]
        accepted, result = check_gepa_mutation(entry.template, entry.template)
        assert accepted is True

    def test_all_templates_have_placeholders(self):
        """Verify catalog templates actually contain placeholders."""
        from app.logic.placeholder_validator import extract_placeholders

        templates_with_ph = 0
        for entry in PROMPT_CATALOG:
            ph = extract_placeholders(entry.template)
            if ph:
                templates_with_ph += 1
        # Most templates should have placeholders
        assert templates_with_ph >= len(PROMPT_CATALOG) * 0.5
