"""BaseSkill and StreamingSkill (Design §8, §4.5).

Neither is the public entry point. AC-2 requires that "a skill invoked
directly, bypassing the registry, is impossible" — so ``run`` and ``stream``
are the implementation hooks, and :meth:`SkillRegistry.execute` is the only
caller. ``__call__`` is deliberately not defined on either class: a skill is
not callable, so no caller can casually invoke one and skip the guardrails.

``StreamingSkill`` is the one genuine extension over voc-agent-svc. It yields
rather than returning, which means output guardrails run **per yield** rather
than once — see :class:`app.logic.guardrails.GuardrailChain.wrap_stream`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

from app.skills.models import SkillContext, SkillMeta, SkillResult


class Skill(ABC):
    """Common surface: every skill knows its own declaration."""

    meta: SkillMeta

    def __init__(self, meta: SkillMeta) -> None:
        self.meta = meta


class BaseSkill(Skill):
    """A request/response skill."""

    @abstractmethod
    async def run(self, context: SkillContext) -> SkillResult:
        """Do the work. Called only by the registry."""


class StreamingSkill(Skill):
    """A skill that yields chunks as they become available.

    Used by SKL-OIA-04, 05 and 06, which are invoked from
    ``app/logic/live_session.py`` and must deliver partial results inside the
    live latency budget rather than after the whole batch.
    """

    @abstractmethod
    def stream(self, context: SkillContext) -> AsyncIterator[dict[str, Any]]:
        """Yield result chunks. Called only by the registry."""
