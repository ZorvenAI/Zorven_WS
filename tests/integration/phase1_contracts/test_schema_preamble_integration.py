"""
US-053 Integration Tests — Schema Preamble Cross-Service Validation.

Exercises SchemaPreambleGenerator against all real skills.yaml files
and the prompt catalog. No mocks.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "prompt-optimization-svc"))

from app.registries.prompt_catalog import PROMPT_CATALOG  # noqa: E402
from app.services.schema_preamble import (  # noqa: E402
    PREAMBLE_END,
    PREAMBLE_START,
    SchemaPreambleGenerator,
)
from app.services.skill_registry_reader import (  # noqa: E402
    AGENT_SERVICE_DIRS,
    SkillRegistryReader,
)


def _make_generator() -> SchemaPreambleGenerator:
    reader = SkillRegistryReader(repo_root=REPO_ROOT)
    return SchemaPreambleGenerator(reader)


class TestSchemaPreambleIntegration:
    """Cross-service integration tests for schema preamble generation."""

    def test_generate_preamble_for_all_catalog_prompts(self):
        """Generate preambles for non-system prompts where skills resolve."""
        gen = _make_generator()
        generated_count = 0
        for entry in PROMPT_CATALOG:
            if entry.tags.get("prompt_type") == "system":
                continue
            agent_code = entry.tags.get("agent_code", "")
            result = gen.generate_for_prompt(agent_code, entry.name)
            if result is not None:
                generated_count += 1
                assert PREAMBLE_START in result
                assert PREAMBLE_END in result
        # At least some prompts should resolve
        assert generated_count > 0

    def test_preamble_roundtrip_inject_extract(self):
        """inject then extract → get same preamble back."""
        gen = _make_generator()
        preamble = gen.generate_for_prompt("mra", "zorven-wf1-mra-synthesis")
        assert preamble is not None
        prompt = "Synthesize the following market research findings."
        injected = gen.inject(prompt, preamble)
        extracted = gen.extract(injected)
        assert extracted == preamble

    def test_preamble_roundtrip_inject_strip(self):
        """inject then strip → get original prompt back."""
        gen = _make_generator()
        preamble = gen.generate_for_prompt("mra", "zorven-wf1-mra-synthesis")
        assert preamble is not None
        prompt = "Synthesize the following market research findings."
        injected = gen.inject(prompt, preamble)
        stripped = gen.strip(injected)
        assert stripped == prompt

    def test_all_generated_preambles_contain_markers(self):
        """Every generated preamble has START/END markers."""
        gen = _make_generator()
        reader = SkillRegistryReader(repo_root=REPO_ROOT)
        for agent_code in sorted(AGENT_SERVICE_DIRS.keys()):
            skills_file = reader.load_skills(agent_code)
            for skill in skills_file.skills:
                preamble = gen.generate(skill)
                assert (
                    PREAMBLE_START in preamble
                ), f"Missing START marker for {skill.skill_id}"
                assert (
                    PREAMBLE_END in preamble
                ), f"Missing END marker for {skill.skill_id}"

    def test_preamble_content_matches_skill_schema(self):
        """Field names from skills.yaml appear in the generated preamble."""
        gen = _make_generator()
        reader = SkillRegistryReader(repo_root=REPO_ROOT)
        skill = reader.get_skill("mra", "SKL-MRA-01")
        assert skill is not None
        preamble = gen.generate(skill)
        # Check input fields
        for field in skill.input_schema:
            assert field["field"] in preamble
        # Check output fields
        for field in skill.output_schema:
            assert field.field in preamble

    def test_inject_does_not_modify_template_variables(self):
        """{{context.brand_name}} placeholders survive injection."""
        gen = _make_generator()
        preamble = gen.generate_for_prompt("mra", "zorven-wf1-mra-synthesis")
        assert preamble is not None
        template = "Analyze market for {{context.brand_name}} in {{context.industry}}."
        injected = gen.inject(template, preamble)
        assert "{{context.brand_name}}" in injected
        assert "{{context.industry}}" in injected
