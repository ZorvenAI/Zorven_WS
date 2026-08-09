"""AC-1 — skills load from configuration, not from imports.

The load path against the real config/skills.yaml and the real skill modules,
plus the failure AC-1 names specifically: a declaration whose implementing
class is missing must fail **at startup**, naming the skill, rather than at
first invocation.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.core.errors import ErrorCode, SkillNotFound
from app.skills.base import BaseSkill, StreamingSkill
from app.skills.registry import SkillRegistry, SkillRegistryError

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def registry() -> SkillRegistry:
    loaded = SkillRegistry()
    loaded.load()
    return loaded


def test_all_sixteen_declarations_resolve(registry):
    assert len(registry.skill_ids) == 16


def test_lookup_by_id_and_by_name_reach_the_same_skill(registry):
    by_id = registry.get("SKL-OIA-04")
    by_name = registry.get("analyze_transcript_stream")
    assert by_id is by_name


def test_every_skill_is_a_base_or_streaming_skill(registry):
    for skill_id in registry.skill_ids:
        skill = registry.get(skill_id)
        assert isinstance(skill, (BaseSkill, StreamingSkill)), skill_id


def test_streaming_skills_are_streaming_and_the_rest_are_not(registry):
    streaming = {"SKL-OIA-04", "SKL-OIA-05", "SKL-OIA-06"}
    for skill_id in registry.skill_ids:
        skill = registry.get(skill_id)
        if skill_id in streaming:
            assert isinstance(skill, StreamingSkill), skill_id
        else:
            assert isinstance(skill, BaseSkill), skill_id


def test_meta_matches_the_declaration(registry):
    meta = registry.meta("SKL-OIA-10")
    assert meta.name == "extract_and_map_fields"
    assert meta.timeout_ms == 120000
    assert meta.max_retries == 1
    assert meta.circuit_breaker_dependency == "backend"
    assert meta.allowed_roles == ("OWNER", "ADMIN", "EDITOR")


def test_internal_only_skills_are_flagged(registry):
    internal = [s for s in registry.skill_ids if registry.is_internal_only(s)]
    assert internal == ["SKL-OIA-13", "SKL-OIA-15", "SKL-OIA-16"]


def test_unknown_id_raises_skill_not_found(registry):
    """PG-02's tool allowlist: an unknown id is refused, not guessed at."""
    with pytest.raises(SkillNotFound) as exc:
        registry.get("SKL-OIA-99")
    assert exc.value.code is ErrorCode.SKILL_NOT_IN_ALLOWLIST
    assert exc.value.http_status == 404


def test_a_missing_implementing_class_fails_at_startup(tmp_path):
    """AC-1: named, at load time — not at first invocation."""
    declaration = {
        "version": 1,
        "service": "onboarding-intelligence-agent",
        "skills": [
            {
                "skill_id": "SKL-OIA-97",
                "name": "no_such_skill_module",
                "description": "deliberately unresolvable",
                "input_schema": [],
                "timeout_ms": 1000,
                "max_retries": 1,
                "allowed_roles": ["OWNER"],
            }
        ],
    }
    path = tmp_path / "skills.yaml"
    path.write_text(yaml.safe_dump(declaration))

    with pytest.raises(SkillRegistryError) as exc:
        SkillRegistry().load(path)

    message = str(exc.value)
    assert "SKL-OIA-97" in message
    assert "no_such_skill_module" in message


def test_startup_reports_every_missing_skill_at_once(tmp_path):
    """One failed deploy, not one per missing skill."""
    declaration = {
        "version": 1,
        "service": "onboarding-intelligence-agent",
        "skills": [
            {
                "skill_id": f"SKL-OIA-9{n}",
                "name": f"missing_module_{n}",
                "input_schema": [],
                "timeout_ms": 1000,
                "max_retries": 1,
                "allowed_roles": ["OWNER"],
            }
            for n in (5, 6, 7)
        ],
    }
    path = tmp_path / "skills.yaml"
    path.write_text(yaml.safe_dump(declaration))

    with pytest.raises(SkillRegistryError) as exc:
        SkillRegistry().load(path)

    for n in (5, 6, 7):
        assert f"SKL-OIA-9{n}" in str(exc.value)


def test_metadata_can_be_loaded_without_resolving_implementations():
    """The contract test validates the YAML, not the code behind it."""
    registry = SkillRegistry()
    registry.load(resolve=False)
    assert len(registry.skill_ids) == 16
    with pytest.raises(SkillNotFound):
        registry.get("SKL-OIA-01")


async def test_executing_a_streaming_skill_through_execute_is_refused(registry):
    """The two entry points are not interchangeable."""
    from app.skills.models import SkillContext, TenantContext

    context = SkillContext(
        input_prompt="p",
        tenant_context=TenantContext(tenant_id="t-1", role="ADMIN"),
    )
    with pytest.raises((SkillNotFound, NotImplementedError)):
        await registry.execute("SKL-OIA-04", context)


# ── Regression cover for PR #533 review findings ──────────────────────────


async def test_internal_only_skills_reject_an_external_caller(registry):
    """Review finding: internal_only was tracked but never enforced.

    §15 marks SKL-OIA-13 SYSTEM. The platform has no SYSTEM role, so §8
    expresses it as the full role set — which means RBAC alone lets every role
    through. Origin is what actually gates it.
    """
    from app.core.errors import AuthorizationError, ErrorCode
    from app.skills.models import Origin, SkillContext, TenantContext

    for skill_id in ("SKL-OIA-13", "SKL-OIA-15", "SKL-OIA-16"):
        ctx = SkillContext(
            input_prompt="p",
            tenant_context=TenantContext(tenant_id="t-1", role="OWNER"),
            origin=Origin.EXTERNAL,
        )
        with pytest.raises(AuthorizationError) as exc:
            await registry.execute(skill_id, ctx)
        assert exc.value.code is ErrorCode.ROLE_DENIED
        assert "internal-only" in str(exc.value)


async def test_origin_defaults_to_external(registry):
    """A caller who forgets to say gets the stricter treatment."""
    from app.core.errors import AuthorizationError
    from app.skills.models import Origin, SkillContext, TenantContext

    ctx = SkillContext(
        input_prompt="p",
        tenant_context=TenantContext(tenant_id="t-1", role="OWNER"),
    )
    assert ctx.origin is Origin.EXTERNAL
    with pytest.raises(AuthorizationError):
        await registry.execute("SKL-OIA-13", ctx)


async def test_internal_callers_pass_the_origin_gate(registry):
    """The service's own pipelines may invoke them — reaching the deferred body."""
    from app.skills.models import Origin, SkillContext, TenantContext

    ctx = SkillContext(
        input_prompt="p",
        tenant_context=TenantContext(tenant_id="t-1", role="OWNER"),
        origin=Origin.INTERNAL,
    )
    # Past the gate, into the body A-06 leaves deferred.
    with pytest.raises(NotImplementedError):
        await registry.execute("SKL-OIA-13", ctx)


def _first_deferred_skill(registry) -> str:
    """A skill id whose body still raises NotImplementedError.

    Internal-only skills are excluded: they are gated by origin before the
    body runs, which is the very thing the caller is trying to distinguish.
    """
    import inspect

    for skill_id in sorted(registry.ids()):
        if registry.is_internal_only(skill_id):
            continue
        source = inspect.getsource(type(registry.get(skill_id)))
        if "NotImplementedError" in source:
            return skill_id
    raise AssertionError("every skill has a body — this test needs rewriting")


async def test_a_normal_skill_is_unaffected_by_origin(registry):
    """Only the three internal_only skills are gated."""
    from app.skills.models import Origin, SkillContext, TenantContext

    ctx = SkillContext(
        input_prompt="p",
        tenant_context=TenantContext(tenant_id="t-1", role="ADMIN"),
        origin=Origin.EXTERNAL,
    )
    # Any still-deferred, non-internal skill will do: the NotImplementedError
    # is the proof the call reached the body rather than being stopped by the
    # origin gate.
    #
    # Chosen at runtime rather than named. C-02 gave SKL-OIA-01 a body and
    # this test moved to 02; C-03 gave 02 a body and it would have moved
    # again. A hardcoded id makes every skill story edit an unrelated test,
    # which trains people to change the expectation without reading it.
    deferred = _first_deferred_skill(registry)

    with pytest.raises(NotImplementedError):
        await registry.execute(deferred, ctx)
