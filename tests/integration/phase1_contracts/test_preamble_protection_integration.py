"""
US-057 Integration Tests — OPT-12 Schema Preamble Protection Cross-Service.

Exercises preamble protection across all 15 agent services.
No mocks.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "prompt-optimization-svc"))

from app.logic.guardrails import run_candidate_guardrails  # noqa: E402
from app.logic.preamble_validator import validate_preamble_protection  # noqa: E402
from app.services.schema_preamble import SchemaPreambleGenerator  # noqa: E402
from app.services.skill_registry_reader import (  # noqa: E402
    AGENT_SERVICE_DIRS,
    SkillRegistryReader,
)


def _make_reader_and_gen() -> tuple[SkillRegistryReader, SchemaPreambleGenerator]:
    reader = SkillRegistryReader(repo_root=REPO_ROOT)
    return reader, SchemaPreambleGenerator(reader)


ALL_AGENT_CODES = sorted(AGENT_SERVICE_DIRS.keys())


class TestPreambleProtectionIntegration:
    """Cross-service integration tests for OPT-12 preamble protection."""

    def test_all_15_agents_preamble_roundtrip(self):
        """Generate + inject + validate self → valid=True for all agents."""
        reader, gen = _make_reader_and_gen()
        tested = 0
        for agent_code in ALL_AGENT_CODES:
            skills_file = reader.load_skills(agent_code)
            for skill in skills_file.skills:
                if not skill.output_schema:
                    continue
                preamble = gen.generate(skill)
                template = gen.inject("You are an agent.", preamble)
                result = validate_preamble_protection(template, template)
                assert (
                    result.valid is True
                ), f"Self-invariance failed for {skill.skill_id}"
                tested += 1
                break  # One per agent
        assert tested >= 10  # At least 10 of 15 agents have output_schema

    def test_preamble_removal_detected_all_agents(self):
        """Strip preamble → valid=False for all agents."""
        reader, gen = _make_reader_and_gen()
        for agent_code in ALL_AGENT_CODES:
            skills_file = reader.load_skills(agent_code)
            for skill in skills_file.skills:
                if not skill.output_schema:
                    continue
                preamble = gen.generate(skill)
                template = gen.inject("You are an agent.", preamble)
                mutated = gen.strip(template)
                result = validate_preamble_protection(template, mutated)
                assert (
                    result.valid is False
                ), f"Preamble removal not detected for {skill.skill_id}"
                assert result.preamble_present is False
                break

    def test_field_removal_detected_across_agents(self):
        """Remove one output field row → valid=False for agents with ≥2 fields."""
        reader, gen = _make_reader_and_gen()
        tested = 0
        for agent_code in ALL_AGENT_CODES:
            skills_file = reader.load_skills(agent_code)
            for skill in skills_file.skills:
                if len(skill.output_schema) < 2:
                    continue
                preamble = gen.generate(skill)
                template = gen.inject("You are an agent.", preamble)
                first_field = skill.output_schema[0]
                # Remove the first output field's row
                lines = template.splitlines()
                mutated_lines = [
                    line
                    for line in lines
                    if not line.strip().startswith(f"| {first_field.field} ")
                ]
                mutated = "\n".join(mutated_lines)
                result = validate_preamble_protection(template, mutated)
                assert (
                    result.valid is False
                ), f"Field removal not detected for {skill.skill_id}"
                assert first_field.field in result.fields_removed
                tested += 1
                break
        assert tested >= 5

    def test_max_length_weakening_detected_across_agents(self):
        """Increase max_length → valid=False for agents with max_length fields."""
        reader, gen = _make_reader_and_gen()
        tested = 0
        for agent_code in ALL_AGENT_CODES:
            skills_file = reader.load_skills(agent_code)
            for skill in skills_file.skills:
                preamble = gen.generate(skill)
                template = gen.inject("You are an agent.", preamble)
                for field in skill.output_schema:
                    if field.max_length is None:
                        continue
                    old_val = str(field.max_length)
                    new_val = str(field.max_length + 1000)
                    old_row = f"| {field.field} | {field.type} | {old_val} |"
                    new_row = f"| {field.field} | {field.type} | {new_val} |"
                    if old_row in template:
                        mutated = template.replace(old_row, new_row, 1)
                        result = validate_preamble_protection(template, mutated)
                        assert result.valid is False, (
                            f"max_length weakening not detected for "
                            f"{skill.skill_id}.{field.field}"
                        )
                        tested += 1
                        break
                if tested > 0:
                    break
        # Only CGA has max_length, so at least 1
        assert tested >= 1

    def test_required_relaxation_detected_across_agents(self):
        """Flip required yes→no → valid=False for agents with required input fields."""
        reader, gen = _make_reader_and_gen()
        tested = 0
        for agent_code in ALL_AGENT_CODES:
            skills_file = reader.load_skills(agent_code)
            for skill in skills_file.skills:
                if not skill.output_schema:
                    continue
                preamble = gen.generate(skill)
                template = gen.inject("You are an agent.", preamble)
                for inp in skill.input_schema:
                    if not inp.get("required", True):
                        continue
                    field_name = inp.get("field", inp.get("name", "unknown"))
                    field_type = inp.get("type", "string")
                    old_row = f"| {field_name} | {field_type} | yes |"
                    new_row = f"| {field_name} | {field_type} | no |"
                    if old_row in template:
                        mutated = template.replace(old_row, new_row, 1)
                        result = validate_preamble_protection(template, mutated)
                        assert result.valid is False, (
                            f"Required relaxation not detected for "
                            f"{skill.skill_id}.{field_name}"
                        )
                        tested += 1
                        break
                if tested > 0:
                    break
            if tested > 0:
                break
        assert tested >= 1

    def test_guardrail_chain_includes_opt12(self):
        """run_candidate_guardrails includes OPT-12 in results."""
        reader, gen = _make_reader_and_gen()
        skills_file = reader.load_skills("mra")
        skill = skills_file.skills[0]
        preamble = gen.generate(skill)
        template = gen.inject("You are a market research analyst.", preamble)
        chain = run_candidate_guardrails(
            candidate_text=template,
            base_text=template,
            current_cost_usd=0.0,
        )
        guardrail_ids = [r.guardrail_id for r in chain.results]
        assert "OPT-12" in guardrail_ids
        assert chain.all_passed is True
