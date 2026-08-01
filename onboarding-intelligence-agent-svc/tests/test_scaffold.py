"""AC-1 — the tree matches Design §4.4 and the stubs are honest.

The second half matters more than it looks. A stub whose body is ``pass``
returns ``None`` silently, so a later story can ship a no-op that passes its
own tests. Asserting that every scaffolded symbol raises ``NotImplementedError``
turns that class of mistake into a failing test today.
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]

#: Every module Design §4.4 names, by dotted path.
EXPECTED_MODULES = [
    "app.main",
    "app.api.routes",
    "app.api.ws",
    "app.api.deps",
    "app.api.schemas",
    "app.cache.redis_manager",
    "app.cache.session_store",
    "app.cache.idempotency",
    "app.circuit_breaker.breaker",
    "app.core.config",
    "app.core.errors",
    "app.core.logging",
    "app.core.telemetry",
    "app.events.catalog",
    "app.logic.guardrails",
    "app.logic.planner",
    "app.logic.prep_executor",
    "app.logic.live_session",
    "app.logic.process_executor",
    "app.messaging.producer",
    "app.messaging.consumer",
    "app.messaging.schemas",
    "app.prompts.loader",
    "app.prompts.fallbacks",
    "app.providers.stt",
    "app.providers.ocr",
    "app.providers.vision",
    "app.providers.llm",
    "app.providers.storage",
    "app.rbac.engine",
    "app.services.backend_client",
    "app.services.poi_client",
    "app.skills.base",
    "app.skills.models",
    "app.skills.registry",
]

SKILL_MODULES = [
    f"app.skills.{name}"
    for name in [
        "research_business",
        "generate_questionnaire",
        "refine_questionnaire",
        "analyze_transcript_stream",
        "evaluate_answer_sufficiency",
        "generate_followups",
        "analyze_captured_media",
        "summarize_recording",
        "check_workflow_coverage",
        "extract_and_map_fields",
        "register_meeting_assets",
        "autogen_strategy_identity",
        "record_golden_candidates",
        "surface_conflicts_and_escalate",
        "fetch_prompts",
        "redact_pii",
    ]
]

#: Modules A-05 actually implements. Everything else is a stub.
IMPLEMENTED = {
    "app.main",
    "app.api.routes",
    "app.cache.redis_manager",
    "app.core.config",
    "app.core.logging",
    "app.core.telemetry",
    "app.messaging.producer",
    # Implemented by A-03.
    "app.events.catalog",
    "app.events.emitter",
    "app.messaging.consumer",
    "app.messaging.schemas",
    "app.messaging.topics",
    "app.messaging.provision",
    # Implemented by A-06.
    "app.core.errors",
    "app.logic.guardrails",
    "app.rbac.engine",
    "app.skills.base",
    "app.skills.models",
    "app.skills.registry",
}

#: A-06 turned the sixteen skill modules into registry-resolvable classes.
#: They are no longer bare stubs — the class is real and instantiable, and it
#: is the *body* that is deferred. test_skill_bodies_are_deferred covers them.
IMPLEMENTED |= set(SKILL_MODULES)


@pytest.mark.parametrize("dotted", EXPECTED_MODULES + SKILL_MODULES)
def test_module_exists_and_imports(dotted):
    """Importing must not raise — a stub raises when *called*, not on import."""
    assert importlib.import_module(dotted) is not None


def test_all_sixteen_skills_are_scaffolded():
    assert len(SKILL_MODULES) == 16


@pytest.mark.parametrize(
    "dotted", [m for m in EXPECTED_MODULES + SKILL_MODULES if m not in IMPLEMENTED]
)
def test_stub_raises_not_implemented(dotted):
    """Every scaffolded symbol refuses to run rather than doing nothing."""
    module = importlib.import_module(dotted)
    symbols = [
        obj
        for name, obj in vars(module).items()
        if not name.startswith("_")
        and (inspect.isclass(obj) or inspect.isfunction(obj))
        and getattr(obj, "__module__", None) == dotted
    ]
    assert symbols, f"{dotted} scaffolds no symbol"

    for symbol in symbols:
        with pytest.raises(NotImplementedError):
            if inspect.iscoroutinefunction(symbol):
                import asyncio

                asyncio.run(symbol())
            else:
                symbol()


def test_config_directory_and_skills_manifest_exist():
    assert (ROOT / "config" / "skills.yaml").is_file()


def test_skills_yaml_declares_all_sixteen_skills():
    """A-05 landed this empty; A-06 filled it from Design §8."""
    parsed = yaml.safe_load((ROOT / "config" / "skills.yaml").read_text())
    assert parsed["service"] == "onboarding-intelligence-agent"
    assert parsed["version"] == 1
    assert len(parsed["skills"]) == 16


@pytest.mark.parametrize("dotted", SKILL_MODULES)
def test_skill_bodies_are_deferred(dotted):
    """The class resolves and instantiates; run/stream still refuse to run.

    A-06 needs the class to exist so the registry can resolve the declaration
    at startup. What stays deferred is the body — which must raise rather than
    return None, so a later story cannot ship a silent no-op.
    """
    import asyncio
    import inspect

    from app.skills.base import BaseSkill, StreamingSkill
    from app.skills.models import SkillContext, SkillMeta, TenantContext

    module = importlib.import_module(dotted)
    name = dotted.rsplit(".", 1)[1]
    cls = getattr(module, "".join(p.title() for p in name.split("_")))

    assert issubclass(cls, (BaseSkill, StreamingSkill)), dotted
    skill = cls(SkillMeta(skill_id="SKL-OIA-00", name=name))

    context = SkillContext(
        input_prompt="p",
        tenant_context=TenantContext(tenant_id="t-1", role="ADMIN"),
    )

    with pytest.raises(NotImplementedError):
        if isinstance(skill, StreamingSkill):
            stream = skill.stream(context)
            if inspect.isasyncgen(stream):
                asyncio.run(anext(stream))
        else:
            asyncio.run(skill.run(context))


def test_fleet_files_are_present():
    for name in ("Dockerfile", "pyproject.toml", "requirements.txt", "CLAUDE.md"):
        assert (ROOT / name).is_file(), name


def test_dockerfile_exposes_the_assigned_port():
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "EXPOSE 8120" in dockerfile
    assert "--port" in dockerfile and "8120" in dockerfile


def test_pyproject_pins_the_fleet_toolchain():
    """AC-1: Python 3.12, Black 88, mypy --strict, asyncio_mode = auto."""
    pyproject = (ROOT / "pyproject.toml").read_text()
    assert 'asyncio_mode = "auto"' in pyproject
    assert "line-length = 88" in pyproject
    assert "strict = true" in pyproject
    assert 'python_version = "3.12"' in pyproject
