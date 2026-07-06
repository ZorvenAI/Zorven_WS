"""
US-057 Unit Tests — OPT-12 Schema Preamble Protection Guardrail.

All tests use real SkillRegistryReader loading real skills.yaml files.
No mocks.
"""

from pathlib import Path

import pytest

from app.logic.gepa_guardrails import check_preamble_protection
from app.logic.guardrails import GuardrailResult, run_candidate_guardrails
from app.logic.preamble_validator import (
    PreambleProtectionResult,
    _parse_input_table,
    _parse_output_table,
    validate_preamble_protection,
)
from app.services.schema_preamble import (
    PREAMBLE_END,
    PREAMBLE_START,
    SchemaPreambleGenerator,
)
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
def generator(reader):
    return SchemaPreambleGenerator(reader)


@pytest.fixture
def mra_skill(reader):
    skills_file = reader.load_skills("mra")
    return skills_file.skills[0]


@pytest.fixture
def cga_skill_with_max_length(reader):
    """Find a CGA skill that has output fields with max_length."""
    skills_file = reader.load_skills("cga")
    for skill in skills_file.skills:
        for f in skill.output_schema:
            if f.max_length is not None:
                return skill
    return None


@pytest.fixture
def preamble_template(generator, mra_skill):
    """A real template with preamble injected."""
    preamble = generator.generate(mra_skill)
    return generator.inject("You are a market research analyst.", preamble)


@pytest.fixture
def cga_preamble_template(generator, cga_skill_with_max_length):
    """A real CGA template with preamble containing max_length fields."""
    if cga_skill_with_max_length is None:
        return None
    preamble = generator.generate(cga_skill_with_max_length)
    return generator.inject("You are a creative generation agent.", preamble)


ALL_AGENT_CODES = sorted(AGENT_SERVICE_DIRS.keys())


# ---------------------------------------------------------------------------
# PreambleProtectionResult
# ---------------------------------------------------------------------------


class TestPreambleProtectionResult:
    def test_dataclass_default_values(self):
        result = PreambleProtectionResult()
        assert result.valid is True
        assert result.preamble_present is True
        assert result.preamble_at_top is True
        assert result.fields_removed == []
        assert result.fields_added == []
        assert result.max_length_weakened == []
        assert result.required_relaxed == []
        assert result.violation_reasons == []

    def test_invalid_when_violations_present(self):
        result = PreambleProtectionResult(
            valid=False,
            violation_reasons=["Preamble markers missing from candidate"],
        )
        assert result.valid is False
        assert len(result.violation_reasons) == 1


# ---------------------------------------------------------------------------
# _parse_output_table
# ---------------------------------------------------------------------------


class TestParseOutputTable:
    def test_parse_output_table_real_preamble(self, generator, mra_skill):
        preamble = generator.generate(mra_skill)
        fields = _parse_output_table(preamble)
        assert len(fields) > 0
        assert all("field" in f and "type" in f and "max_length" in f for f in fields)

    def test_parse_output_table_includes_max_length(self, generator, mra_skill):
        preamble = generator.generate(mra_skill)
        fields = _parse_output_table(preamble)
        # At least verify the field names match the skill output_schema
        preamble_field_names = [f["field"] for f in fields]
        schema_field_names = [f.field for f in mra_skill.output_schema]
        assert preamble_field_names == schema_field_names

    def test_parse_output_table_dash_as_none(self):
        preamble = (
            "## Required Output\n"
            "| Field | Type | Max Length |\n"
            "|-------|------|------------|\n"
            "| notes | string | \u2014 |\n"
        )
        fields = _parse_output_table(preamble)
        assert len(fields) == 1
        assert fields[0]["max_length"] is None


# ---------------------------------------------------------------------------
# _parse_input_table
# ---------------------------------------------------------------------------


class TestParseInputTable:
    def test_parse_input_table_real_preamble(self, generator, mra_skill):
        preamble = generator.generate(mra_skill)
        fields = _parse_input_table(preamble)
        assert len(fields) > 0
        assert all("field" in f and "type" in f and "required" in f for f in fields)

    def test_parse_input_table_required_flags(self):
        preamble = (
            "## Expected Input\n"
            "| Field | Type | Required |\n"
            "|-------|------|----------|\n"
            "| query | string | yes |\n"
            "| notes | string | no |\n"
        )
        fields = _parse_input_table(preamble)
        assert len(fields) == 2
        assert fields[0]["required"] is True
        assert fields[1]["required"] is False


# ---------------------------------------------------------------------------
# validate_preamble_protection
# ---------------------------------------------------------------------------


class TestValidatePreambleProtection:
    def test_identical_templates_valid(self, preamble_template):
        result = validate_preamble_protection(preamble_template, preamble_template)
        assert result.valid is True
        assert result.violation_reasons == []

    def test_preamble_removed_entirely(self, preamble_template, generator):
        mutated = generator.strip(preamble_template)
        result = validate_preamble_protection(preamble_template, mutated)
        assert result.valid is False
        assert result.preamble_present is False

    def test_start_marker_removed(self, preamble_template):
        mutated = preamble_template.replace(PREAMBLE_START, "")
        result = validate_preamble_protection(preamble_template, mutated)
        assert result.valid is False
        assert result.preamble_present is False

    def test_end_marker_removed(self, preamble_template):
        mutated = preamble_template.replace(PREAMBLE_END, "")
        result = validate_preamble_protection(preamble_template, mutated)
        assert result.valid is False
        assert result.preamble_present is False

    def test_preamble_moved_to_middle(self, preamble_template, generator):
        preamble = generator.extract(preamble_template)
        content = generator.strip(preamble_template)
        mutated = content + "\n\n" + preamble
        result = validate_preamble_protection(preamble_template, mutated)
        assert result.valid is False
        assert result.preamble_at_top is False

    def test_preamble_moved_to_end(self, preamble_template, generator):
        preamble = generator.extract(preamble_template)
        mutated = "Some intro text.\n\nMore content.\n\n" + preamble
        result = validate_preamble_protection(preamble_template, mutated)
        assert result.valid is False
        assert result.preamble_at_top is False

    def test_output_field_removed(self, preamble_template, mra_skill):
        # Remove first output field row from the preamble
        first_output = mra_skill.output_schema[0]
        # Find the row in the template and remove it
        lines = preamble_template.splitlines()
        mutated_lines = [
            line
            for line in lines
            if not (
                line.strip().startswith(f"| {first_output.field} ")
                and "Required Output" not in line
            )
        ]
        mutated = "\n".join(mutated_lines)
        result = validate_preamble_protection(preamble_template, mutated)
        assert result.valid is False
        assert first_output.field in result.fields_removed

    def test_output_field_added_is_ok(self, preamble_template):
        # Add a new field row to the output table
        new_row = "| new_field | string | 100 |"
        mutated = preamble_template.replace(
            PREAMBLE_END,
            new_row + "\n" + PREAMBLE_END,
        )
        # Move the row to be inside the output table section
        # Simpler: insert before the Timeout line
        lines = preamble_template.splitlines()
        mutated_lines = []
        for line in lines:
            if line.strip().startswith("Timeout:"):
                mutated_lines.append(new_row)
            mutated_lines.append(line)
        mutated = "\n".join(mutated_lines)
        result = validate_preamble_protection(preamble_template, mutated)
        assert result.valid is True
        assert "new_field" in result.fields_added

    def test_max_length_increased_is_weakening(
        self, cga_preamble_template, cga_skill_with_max_length
    ):
        if cga_preamble_template is None:
            pytest.skip("No CGA skill with max_length found")
        template = cga_preamble_template
        skill = cga_skill_with_max_length
        for field in skill.output_schema:
            if field.max_length is not None:
                original_val = str(field.max_length)
                weakened_val = str(field.max_length + 500)
                old_row = f"| {field.field} | {field.type} | {original_val} |"
                new_row = f"| {field.field} | {field.type} | {weakened_val} |"
                if old_row in template:
                    mutated = template.replace(old_row, new_row, 1)
                    result = validate_preamble_protection(template, mutated)
                    assert result.valid is False
                    assert len(result.max_length_weakened) >= 1
                    assert result.max_length_weakened[0]["field"] == field.field
                    return
        pytest.skip("No matching output row found in CGA preamble")

    def test_max_length_decreased_is_ok(
        self, cga_preamble_template, cga_skill_with_max_length
    ):
        if cga_preamble_template is None:
            pytest.skip("No CGA skill with max_length found")
        template = cga_preamble_template
        skill = cga_skill_with_max_length
        for field in skill.output_schema:
            if field.max_length is not None and field.max_length > 10:
                original_val = str(field.max_length)
                strengthened_val = str(field.max_length - 5)
                old_row = f"| {field.field} | {field.type} | {original_val} |"
                new_row = f"| {field.field} | {field.type} | {strengthened_val} |"
                if old_row in template:
                    mutated = template.replace(old_row, new_row, 1)
                    result = validate_preamble_protection(template, mutated)
                    assert result.valid is True
                    assert result.max_length_weakened == []
                    return
        pytest.skip("No matching output row found in CGA preamble")

    def test_max_length_to_dash_is_weakening(
        self, cga_preamble_template, cga_skill_with_max_length
    ):
        if cga_preamble_template is None:
            pytest.skip("No CGA skill with max_length found")
        template = cga_preamble_template
        skill = cga_skill_with_max_length
        for field in skill.output_schema:
            if field.max_length is not None:
                original_val = str(field.max_length)
                old_row = f"| {field.field} | {field.type} | {original_val} |"
                new_row = f"| {field.field} | {field.type} | \u2014 |"
                if old_row in template:
                    mutated = template.replace(old_row, new_row, 1)
                    result = validate_preamble_protection(template, mutated)
                    assert result.valid is False
                    assert len(result.max_length_weakened) >= 1
                    return
        pytest.skip("No matching output row found in CGA preamble")

    def test_required_input_field_removed(self, preamble_template, mra_skill):
        # Remove a required input field row entirely
        for inp in mra_skill.input_schema:
            if inp.get("required", True):
                field_name = inp.get("field", inp.get("name", "unknown"))
                row = f"| {field_name} | {inp.get('type', 'string')} | yes |"
                if row in preamble_template:
                    mutated = preamble_template.replace(row + "\n", "", 1)
                    result = validate_preamble_protection(preamble_template, mutated)
                    assert result.valid is False
                    assert len(result.required_relaxed) >= 1
                    assert result.required_relaxed[0]["field"] == field_name
                    assert result.required_relaxed[0]["mutated"] is None
                    return
        pytest.skip("No required input fields found in MRA skill")

    def test_required_made_optional(self, preamble_template, mra_skill):
        # Find a required input field and make it optional
        for inp in mra_skill.input_schema:
            if inp.get("required", True):
                field_name = inp.get("field", inp.get("name", "unknown"))
                old_row = f"| {field_name} | {inp.get('type', 'string')} | yes |"
                new_row = f"| {field_name} | {inp.get('type', 'string')} | no |"
                if old_row in preamble_template:
                    mutated = preamble_template.replace(old_row, new_row, 1)
                    result = validate_preamble_protection(preamble_template, mutated)
                    assert result.valid is False
                    assert len(result.required_relaxed) >= 1
                    assert result.required_relaxed[0]["field"] == field_name
                    return
        pytest.skip("No required input fields found in MRA skill")

    def test_optional_made_required_is_ok(self, preamble_template, mra_skill):
        # Find an optional input field and make it required (strengthening)
        for inp in mra_skill.input_schema:
            if not inp.get("required", True):
                field_name = inp.get("field", inp.get("name", "unknown"))
                old_row = f"| {field_name} | {inp.get('type', 'string')} | no |"
                new_row = f"| {field_name} | {inp.get('type', 'string')} | yes |"
                if old_row in preamble_template:
                    mutated = preamble_template.replace(old_row, new_row, 1)
                    result = validate_preamble_protection(preamble_template, mutated)
                    assert result.valid is True
                    assert result.required_relaxed == []
                    return
        pytest.skip("No optional input fields found in MRA skill")

    def test_no_preamble_in_original_passes(self):
        original = "You are a helpful assistant."
        mutated = "You are a very helpful assistant."
        result = validate_preamble_protection(original, mutated)
        assert result.valid is True

    def test_whitespace_before_preamble_ok(self, preamble_template):
        mutated = "\n  \n" + preamble_template
        result = validate_preamble_protection(preamble_template, mutated)
        assert result.valid is True
        assert result.preamble_at_top is True

    def test_multiple_violations_collected(self, preamble_template, mra_skill):
        # Remove a field AND change required → optional simultaneously
        lines = preamble_template.splitlines()
        first_output = mra_skill.output_schema[0]
        # Remove first output field row
        mutated_lines = [
            line
            for line in lines
            if not line.strip().startswith(f"| {first_output.field} ")
        ]
        mutated = "\n".join(mutated_lines)
        # Also flip a required input field if possible
        for inp in mra_skill.input_schema:
            if inp.get("required", True):
                field_name = inp.get("field", inp.get("name", "unknown"))
                old_row = f"| {field_name} | {inp.get('type', 'string')} | yes |"
                new_row = f"| {field_name} | {inp.get('type', 'string')} | no |"
                if old_row in mutated:
                    mutated = mutated.replace(old_row, new_row, 1)
                    break
        result = validate_preamble_protection(preamble_template, mutated)
        assert result.valid is False
        assert len(result.violation_reasons) >= 1


# ---------------------------------------------------------------------------
# check_preamble_protection
# ---------------------------------------------------------------------------


class TestCheckPreambleProtection:
    def test_returns_guardrail_result(self, preamble_template):
        result = check_preamble_protection(preamble_template, preamble_template)
        assert isinstance(result, GuardrailResult)

    def test_passed_true_for_valid(self, preamble_template):
        result = check_preamble_protection(preamble_template, preamble_template)
        assert result.passed is True
        assert result.guardrail_id == "OPT-12"

    def test_passed_false_for_removed(self, preamble_template, generator):
        mutated = generator.strip(preamble_template)
        result = check_preamble_protection(preamble_template, mutated)
        assert result.passed is False
        assert result.guardrail_id == "OPT-12"

    def test_details_include_audit_fields(self, preamble_template, generator):
        mutated = generator.strip(preamble_template)
        result = check_preamble_protection(
            preamble_template,
            mutated,
            tenant_id="tenant-123",
            prompt_id="prompt-456",
            optimization_run_id="run-789",
        )
        assert result.details["tenant_id"] == "tenant-123"
        assert result.details["prompt_id"] == "prompt-456"
        assert result.details["optimization_run_id"] == "run-789"

    def test_guardrail_id_is_opt12(self, preamble_template):
        result = check_preamble_protection(preamble_template, preamble_template)
        assert result.guardrail_id == "OPT-12"


# ---------------------------------------------------------------------------
# run_candidate_guardrails with OPT-12
# ---------------------------------------------------------------------------


class TestRunCandidateGuardrailsOPT12:
    def test_opt12_in_chain_all_pass(self, preamble_template):
        chain = run_candidate_guardrails(
            candidate_text=preamble_template,
            base_text=preamble_template,
            current_cost_usd=0.0,
        )
        assert chain.all_passed is True
        guardrail_ids = [r.guardrail_id for r in chain.results]
        assert "OPT-12" in guardrail_ids

    def test_opt12_rejects_in_chain(self, preamble_template, generator):
        mutated = generator.strip(preamble_template)
        chain = run_candidate_guardrails(
            candidate_text=mutated,
            base_text=preamble_template,
            current_cost_usd=0.0,
        )
        assert chain.all_passed is False
        assert chain.first_failure.guardrail_id == "OPT-12"


# ---------------------------------------------------------------------------
# All 15 agents
# ---------------------------------------------------------------------------


class TestAllAgents:
    @pytest.mark.parametrize("agent_code", ALL_AGENT_CODES)
    def test_all_15_agents_self_invariant(self, reader, agent_code):
        """Generate preamble per agent, validate self → valid=True."""
        gen = SchemaPreambleGenerator(reader)
        skills_file = reader.load_skills(agent_code)
        skill = skills_file.skills[0]
        if not skill.output_schema:
            pytest.skip(f"No output_schema for {agent_code} first skill")
        preamble = gen.generate(skill)
        template = gen.inject("You are an agent.", preamble)
        result = validate_preamble_protection(template, template)
        assert result.valid is True, f"Self-invariance failed for {agent_code}"
