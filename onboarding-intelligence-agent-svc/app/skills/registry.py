"""SkillRegistry — the only way a skill runs (Design §8, §4.5).

Three properties AC-1 and AC-2 turn on:

**Skills load from configuration, not from imports.** ``config/skills.yaml``
is the source of truth; the registry resolves each declaration to its
implementing class. A declaration whose class is missing fails **at startup**
with a message naming the skill, not on first invocation six weeks later.

**Lookup is by both id and name.** ``SKL-OIA-04`` and
``analyze_transcript_stream`` reach the same skill.

**Guardrails cannot be skipped.** :meth:`execute` is the public entry point;
``BaseSkill`` defines ``run`` and is not callable, so there is no convenient
way to invoke a skill without passing IG → PG → OG and the §15 matrix.
"""

from __future__ import annotations

import importlib
import time
from pathlib import Path
from typing import Any, AsyncIterator

import yaml

from app.core.errors import AuthorizationError, SkillNotFound
from app.core.logging import get_logger
from app.logic.guardrails import GuardrailChain, Layer
from app.rbac.engine import RBACEngine, Role, Verdict
from app.skills.base import BaseSkill, Skill, StreamingSkill
from app.skills.models import Origin, SkillContext, SkillMeta, SkillResult

logger = get_logger(__name__)

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "skills.yaml"

#: Declaration name → module under app.skills. The module is the name; the
#: class is its PascalCase form, matching what A-05 scaffolded.
MODULE_TEMPLATE = "app.skills.{name}"


class SkillRegistryError(RuntimeError):
    """Startup failure: a declaration could not be resolved."""


class SkillRegistry:
    """Loads, resolves and executes the sixteen declared skills."""

    def __init__(
        self,
        chain: GuardrailChain | None = None,
        rbac: RBACEngine | None = None,
    ) -> None:
        self._by_id: dict[str, Skill] = {}
        self._by_name: dict[str, Skill] = {}
        self._meta: dict[str, SkillMeta] = {}
        self._internal_only: set[str] = set()
        self.chain = chain or GuardrailChain()
        self.rbac = rbac or RBACEngine()

    # ── Loading ──────────────────────────────────────────────
    def load(self, config_path: Path | None = None, *, resolve: bool = True) -> None:
        """Read the YAML and resolve every declaration.

        ``resolve=False`` loads metadata without importing implementations —
        used by the contract test, which validates the YAML rather than the
        code behind it.
        """
        path = config_path or DEFAULT_CONFIG
        document = yaml.safe_load(path.read_text())
        declarations = document.get("skills") or []

        missing: list[str] = []
        for declaration in declarations:
            meta = self._meta_from(declaration)
            self._meta[meta.skill_id] = meta
            if declaration.get("internal_only"):
                self._internal_only.add(meta.skill_id)

            if not resolve:
                continue
            try:
                skill = self._resolve(meta)
            except SkillRegistryError as exc:
                missing.append(str(exc))
                continue
            self._by_id[meta.skill_id] = skill
            self._by_name[meta.name] = skill

        if missing:
            # Named, and all of them — reporting one at a time would mean one
            # failed deploy per missing skill.
            raise SkillRegistryError(
                "skill declarations could not be resolved:\n  " + "\n  ".join(missing)
            )

        logger.info(
            "skill_registry_loaded",
            declared=len(self._meta),
            resolved=len(self._by_id),
            internal_only=sorted(self._internal_only),
        )

    @staticmethod
    def _meta_from(declaration: dict[str, Any]) -> SkillMeta:
        return SkillMeta(
            skill_id=declaration["skill_id"],
            name=declaration["name"],
            description=(declaration.get("description") or "").strip(),
            allowed_roles=tuple(declaration.get("allowed_roles") or ()),
            idempotent=bool(declaration.get("idempotent", True)),
            max_retries=int(declaration.get("max_retries", 1)),
            timeout_ms=int(declaration.get("timeout_ms", 30000)),
            circuit_breaker_dependency=declaration.get("circuit_breaker_dependency", "")
            or "",
        )

    @staticmethod
    def _resolve(meta: SkillMeta) -> Skill:
        """Import the module and instantiate the class named by the skill."""
        module_path = MODULE_TEMPLATE.format(name=meta.name)
        class_name = "".join(part.title() for part in meta.name.split("_"))
        try:
            module = importlib.import_module(module_path)
        except ImportError as exc:
            raise SkillRegistryError(
                f"{meta.skill_id} ({meta.name}): module {module_path} "
                f"not importable — {exc}"
            ) from exc

        implementation = getattr(module, class_name, None)
        if implementation is None:
            raise SkillRegistryError(
                f"{meta.skill_id} ({meta.name}): {module_path} has no class "
                f"{class_name}"
            )
        if not isinstance(implementation, type) or not issubclass(
            implementation, (BaseSkill, StreamingSkill)
        ):
            raise SkillRegistryError(
                f"{meta.skill_id} ({meta.name}): {class_name} is not a BaseSkill "
                "or StreamingSkill"
            )
        return implementation(meta)

    # ── Lookup ───────────────────────────────────────────────
    def get(self, key: str) -> Skill:
        """Look up by skill id or by name. PG-02's allowlist in one method."""
        skill = self._by_id.get(key) or self._by_name.get(key)
        if skill is None:
            raise SkillNotFound(f"no skill registered as {key!r}", skill_id=key)
        return skill

    def meta(self, key: str) -> SkillMeta:
        meta = self._meta.get(key)
        if meta is None:
            for candidate in self._meta.values():
                if candidate.name == key:
                    return candidate
            raise SkillNotFound(f"no skill declared as {key!r}", skill_id=key)
        return meta

    def is_internal_only(self, skill_id: str) -> bool:
        return skill_id in self._internal_only

    @property
    def skill_ids(self) -> list[str]:
        return sorted(self._meta)

    # ── Execution ────────────────────────────────────────────
    async def execute(self, key: str, context: SkillContext) -> SkillResult:
        """Run a non-streaming skill through the full chain.

        Order is IG → RBAC (PG-03) → PG → skill → OG, and none of it is
        optional. A caller who wants to skip a layer has to edit this method,
        which is the point.
        """
        skill = self.get(key)
        meta = skill.meta

        # The evaluated payload is assigned back: IG-04 redacts and IG-06
        # truncates, and a transform the skill never sees is not a guardrail.
        context.input_context = self.chain.evaluate(
            Layer.INPUT, context.input_context, context
        )
        self._authorize(meta, context)
        self.chain.evaluate(Layer.PROCESS, meta, context)

        started = time.perf_counter()
        if not isinstance(skill, BaseSkill):
            raise SkillNotFound(
                f"{meta.skill_id} is a streaming skill — use execute_stream",
                skill_id=meta.skill_id,
            )
        result = await skill.run(context)
        result.duration_ms = int((time.perf_counter() - started) * 1000)

        return self.chain.evaluate_result(result, context)

    async def execute_stream(
        self, key: str, context: SkillContext
    ) -> AsyncIterator[dict[str, Any]]:
        """Run a streaming skill, evaluating OG on every chunk."""
        skill = self.get(key)
        meta = skill.meta

        context.input_context = self.chain.evaluate(
            Layer.INPUT, context.input_context, context
        )
        self._authorize(meta, context)
        self.chain.evaluate(Layer.PROCESS, meta, context)

        if not isinstance(skill, StreamingSkill):
            raise SkillNotFound(
                f"{meta.skill_id} is not a streaming skill — use execute",
                skill_id=meta.skill_id,
            )
        async for chunk in self.chain.wrap_stream(skill.stream(context), context):
            yield chunk

    def _authorize(self, meta: SkillMeta, context: SkillContext) -> Verdict:
        """PG-03. Raises ERR-04 on a denial; ESCALATE and VIEW_RESULT pass through.

        The role is taken from the tenant context, which is populated from the
        verified JWT claim — §15 forbids reading it from a body or a header.

        ``internal_only`` is checked **before** the matrix, because the matrix
        cannot express it: those skills carry the full role set precisely
        because the platform has no SYSTEM role, so every role would pass.
        Origin is the gate.
        """
        if (
            self.is_internal_only(meta.skill_id)
            and context.origin is not Origin.INTERNAL
        ):
            raise AuthorizationError(
                f"{meta.skill_id} is internal-only and cannot be invoked externally",
                skill_id=meta.skill_id,
                origin=context.origin.value,
            )
        role = Role(context.tenant_context.role)
        return self.rbac.enforce(role, meta.skill_id)
