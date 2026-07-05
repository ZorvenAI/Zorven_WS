"""
US-055 Integration Tests — Reflection Context Enricher Cross-Service Validation.

Exercises ReflectionContextEnricher against all 179 real skills across
15 agent services. No mocks.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "prompt-optimization-svc"))

from app.registries.prompt_catalog import PROMPT_CATALOG  # noqa: E402
from app.services.reflection_context_enricher import (  # noqa: E402
    ReflectionContextEnricher,
)
from app.services.skill_registry_reader import (  # noqa: E402
    AGENT_SERVICE_DIRS,
    SkillRegistryReader,
)


def _make_enricher() -> tuple[ReflectionContextEnricher, SkillRegistryReader]:
    reader = SkillRegistryReader(repo_root=REPO_ROOT)
    return ReflectionContextEnricher(reader), reader


class TestReflectionContextIntegration:
    """Cross-service integration tests for reflection context enrichment."""

    def test_enrichment_for_all_179_skills(self):
        """Every skill produces non-empty formatted context."""
        enricher, reader = _make_enricher()
        empty_skills = []
        for agent_code in sorted(AGENT_SERVICE_DIRS.keys()):
            skills_file = reader.load_skills(agent_code)
            for skill in skills_file.skills:
                context = enricher._format_skill_context(skill)
                if not context:
                    empty_skills.append(skill.skill_id)
        assert empty_skills == [], f"Skills with no context: {empty_skills}"

    def test_context_contains_all_output_fields(self):
        """Context mentions every field from the skill's output_schema."""
        enricher, reader = _make_enricher()
        missing = []
        for agent_code in sorted(AGENT_SERVICE_DIRS.keys()):
            skills_file = reader.load_skills(agent_code)
            for skill in skills_file.skills:
                context = enricher._format_skill_context(skill)
                for field in skill.output_schema:
                    if field.field not in context:
                        missing.append(
                            f"{skill.skill_id}: field '{field.field}' missing"
                        )
        assert missing == [], f"Missing fields in context:\n" + "\n".join(missing)

    def test_context_for_prompt_catalog_entries(self):
        """Non-system catalog prompts produce context where skills resolve."""
        enricher, _ = _make_enricher()
        resolved_count = 0
        for entry in PROMPT_CATALOG:
            if entry.tags.get("prompt_type") == "system":
                continue
            agent_code = entry.tags.get("agent_code", "")
            result = enricher.enrich_gepa_kwargs(agent_code, [entry.name])
            if result:
                resolved_count += 1
        assert resolved_count > 0

    def test_context_no_cross_agent_leakage(self):
        """MRA context doesn't contain CGA skill IDs and vice versa."""
        enricher, reader = _make_enricher()
        # Build MRA context
        mra_skills = reader.load_skills("mra")
        mra_prompt = (
            f"zorven-wf1-mra-{mra_skills.skills[0].name.lower().replace(' ', '-')}"
        )
        mra_desc = enricher.build_task_description("mra", [mra_prompt])

        # Build CGA context
        cga_skills = reader.load_skills("cga")
        cga_prompt = (
            f"zorven-wf3-cga-{cga_skills.skills[0].name.lower().replace(' ', '-')}"
        )
        cga_desc = enricher.build_task_description("cga", [cga_prompt])

        # Cross-check: MRA context should not contain CGA skill IDs
        if mra_desc and cga_desc:
            for skill in cga_skills.skills:
                assert (
                    skill.skill_id not in mra_desc
                ), f"MRA context contains CGA skill {skill.skill_id}"
            for skill in mra_skills.skills:
                assert (
                    skill.skill_id not in cga_desc
                ), f"CGA context contains MRA skill {skill.skill_id}"

    def test_gepa_kwargs_structure(self):
        """enrich_gepa_kwargs returns valid dict structure."""
        enricher, reader = _make_enricher()
        skills_file = reader.load_skills("mra")
        first_skill = skills_file.skills[0]
        prompt_name = f"zorven-wf1-mra-{first_skill.name.lower().replace(' ', '-')}"
        result = enricher.enrich_gepa_kwargs("mra", [prompt_name])
        if result:
            assert isinstance(result, dict)
            assert isinstance(result.get("task_description"), str)
            assert len(result["task_description"]) > 0

    def test_enrichment_deterministic(self):
        """Same inputs produce same output."""
        enricher, _ = _make_enricher()
        prompts = ["zorven-wf1-mra-synthesis"]
        r1 = enricher.build_task_description("mra", prompts)
        r2 = enricher.build_task_description("mra", prompts)
        assert r1 == r2
