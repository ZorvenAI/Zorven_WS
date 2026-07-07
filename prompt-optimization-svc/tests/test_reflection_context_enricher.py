"""
US-055 Unit Tests — Reflection Context Enricher.

All tests use real SkillRegistryReader loading real skills.yaml files.
No mocks.
"""

from pathlib import Path

import pytest

from app.services.reflection_context_enricher import ReflectionContextEnricher
from app.services.skill_registry_reader import (
    AGENT_SERVICE_DIRS,
    SkillRegistryReader,
)
from app.services.gepa_optimizer import ZorvenGepaOptimizer
from app.services.joint_optimizer import JointOptimizer

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def reader():
    r = SkillRegistryReader(repo_root=REPO_ROOT)
    yield r
    r.clear_cache()


@pytest.fixture
def enricher(reader):
    return ReflectionContextEnricher(reader)


ALL_AGENT_CODES = sorted(AGENT_SERVICE_DIRS.keys())


# ---------------------------------------------------------------------------
# build_task_description
# ---------------------------------------------------------------------------


class TestBuildTaskDescription:
    def test_returns_nonempty_for_known_prompt(self, enricher):
        desc = enricher.build_task_description("mra", ["zorven-wf1-mra-synthesis"])
        assert len(desc) > 0

    def test_contains_skill_id(self, enricher):
        desc = enricher.build_task_description("mra", ["zorven-wf1-mra-synthesis"])
        assert "SKL-MRA" in desc

    def test_contains_field_names(self, enricher, reader):
        skill = reader.get_skill_for_prompt("mra", "zorven-wf1-mra-synthesis")
        assert skill is not None
        desc = enricher.build_task_description("mra", ["zorven-wf1-mra-synthesis"])
        for field in skill.output_schema:
            assert field.field in desc

    def test_contains_max_length(self, enricher, reader):
        skill = reader.get_skill_for_prompt("mra", "zorven-wf1-mra-synthesis")
        assert skill is not None
        fields_with_max = [f for f in skill.output_schema if f.max_length]
        if fields_with_max:
            desc = enricher.build_task_description("mra", ["zorven-wf1-mra-synthesis"])
            for field in fields_with_max:
                assert f"max_length={field.max_length}" in desc

    def test_contains_enum_values(self, enricher, reader):
        # Find a skill with enum values
        for agent_code in ALL_AGENT_CODES:
            skills_file = reader.load_skills(agent_code)
            for skill in skills_file.skills:
                enum_fields = [f for f in skill.output_schema if f.enum_values]
                if enum_fields:
                    prompt_names = [
                        f"zorven-wf1-{agent_code}-{skill.name.lower().replace(' ', '-')}"
                    ]
                    desc = enricher.build_task_description(agent_code, prompt_names)
                    if desc:
                        for ef in enum_fields:
                            assert "enum:" in desc
                        return
        pytest.skip("No skills with enum_values found")

    def test_contains_required_flag(self, enricher):
        desc = enricher.build_task_description("mra", ["zorven-wf1-mra-synthesis"])
        assert "required" in desc

    def test_returns_empty_for_unknown_prompt(self, enricher):
        desc = enricher.build_task_description("mra", ["zorven-wf1-mra-nonexistent"])
        assert desc == ""

    def test_multiple_prompts_produces_multiple_sections(self, enricher, reader):
        # Get two distinct skill names for MRA
        skills_file = reader.load_skills("mra")
        if len(skills_file.skills) < 2:
            pytest.skip("MRA has fewer than 2 skills")
        s1 = skills_file.skills[0]
        s2 = skills_file.skills[1]
        # Build prompt names that would match these skills
        p1 = f"zorven-wf1-mra-{s1.name.lower().replace(' ', '-')}"
        p2 = f"zorven-wf1-mra-{s2.name.lower().replace(' ', '-')}"
        desc = enricher.build_task_description("mra", [p1, p2])
        if desc:
            assert s1.skill_id in desc
            assert s2.skill_id in desc


# ---------------------------------------------------------------------------
# enrich_gepa_kwargs
# ---------------------------------------------------------------------------


class TestEnrichGepaKwargs:
    def test_returns_dict_with_task_description(self, enricher):
        result = enricher.enrich_gepa_kwargs("mra", ["zorven-wf1-mra-synthesis"])
        assert isinstance(result, dict)
        assert "task_description" in result
        assert len(result["task_description"]) > 0

    def test_returns_empty_dict_for_unknown(self, enricher):
        result = enricher.enrich_gepa_kwargs("mra", ["zorven-wf1-mra-nonexistent"])
        assert result == {}

    def test_merges_with_existing_kwargs(self, enricher):
        existing = {"display_progress_bar": True, "custom_key": 42}
        result = enricher.enrich_gepa_kwargs(
            "mra", ["zorven-wf1-mra-synthesis"], existing_kwargs=existing
        )
        assert result["display_progress_bar"] is True
        assert result["custom_key"] == 42
        assert "task_description" in result

    def test_does_not_overwrite_existing_task_description(self, enricher):
        existing = {"task_description": "My custom description"}
        result = enricher.enrich_gepa_kwargs(
            "mra", ["zorven-wf1-mra-synthesis"], existing_kwargs=existing
        )
        assert result["task_description"] == "My custom description"


# ---------------------------------------------------------------------------
# _format_skill_context
# ---------------------------------------------------------------------------


class TestFormatSkillContext:
    def test_format_includes_skill_name(self, enricher, reader):
        skill = reader.get_skill("mra", "SKL-MRA-01")
        context = enricher._format_skill_context(skill)
        assert skill.name in context

    def test_format_handles_no_max_length(self, enricher, reader):
        skill = reader.get_skill("mra", "SKL-MRA-01")
        context = enricher._format_skill_context(skill)
        # Should not raise, should produce valid output
        assert skill.skill_id in context
        assert "Output fields:" in context


# ---------------------------------------------------------------------------
# ZorvenGepaOptimizer gepa_kwargs pass-through
# ---------------------------------------------------------------------------

MLFLOW_URI = "http://localhost:5000"


class TestGepaOptimizerKwargs:
    def test_optimize_accepts_gepa_kwargs(self):
        opt = ZorvenGepaOptimizer(mlflow_tracking_uri=MLFLOW_URI)

        def bad_predict(**kwargs):
            raise RuntimeError("test")

        result = opt.optimize(
            prompt_uris=["prompts:/__test_nonexistent/1"],
            predict_fn=bad_predict,
            train_data=[],
            scorers=[],
            agent_code="mra",
            gepa_kwargs={"task_description": "test context"},
        )
        # Should still return a result (with error from bad predict)
        assert result.error is not None
        assert result.agent_code == "mra"

    def test_optimize_default_gepa_kwargs_is_none(self):
        opt = ZorvenGepaOptimizer(mlflow_tracking_uri=MLFLOW_URI)

        def bad_predict(**kwargs):
            raise RuntimeError("test")

        result = opt.optimize(
            prompt_uris=["prompts:/__test_nonexistent/1"],
            predict_fn=bad_predict,
            train_data=[],
            scorers=[],
            agent_code="mra",
        )
        assert result.error is not None


# ---------------------------------------------------------------------------
# JointOptimizer enricher integration
# ---------------------------------------------------------------------------


class TestJointOptimizerEnricher:
    def test_joint_optimizer_accepts_enricher(self, enricher):
        opt = ZorvenGepaOptimizer(mlflow_tracking_uri=MLFLOW_URI)
        joint = JointOptimizer(gepa_optimizer=opt, reflection_enricher=enricher)
        assert joint.reflection_enricher is enricher

    def test_joint_optimizer_without_enricher_still_works(self):
        opt = ZorvenGepaOptimizer(mlflow_tracking_uri=MLFLOW_URI)
        joint = JointOptimizer(gepa_optimizer=opt)
        assert joint.reflection_enricher is None


# ---------------------------------------------------------------------------
# All 15 agents
# ---------------------------------------------------------------------------


class TestAllAgents:
    @pytest.mark.parametrize("agent_code", ALL_AGENT_CODES)
    def test_all_15_agents_first_skill_produces_context(
        self, enricher, reader, agent_code
    ):
        skills_file = reader.load_skills(agent_code)
        first_skill = skills_file.skills[0]
        context = enricher._format_skill_context(first_skill)
        assert len(context) > 0
        assert first_skill.skill_id in context
