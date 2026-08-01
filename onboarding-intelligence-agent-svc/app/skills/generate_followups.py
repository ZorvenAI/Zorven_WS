"""SKL-OIA-06 — Suggest follow-up questions for a partially answered question.

Design §8.1 · implemented by story G-04.

Registered by A-06: the class exists and the registry resolves and
instantiates it, so the declaration in config/skills.yaml is proven to point
at something real. The body is deferred — it raises NotImplementedError
rather than returning None, so a later story cannot ship a silent no-op.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

from app.skills.base import StreamingSkill
from app.skills.models import SkillContext

_NOT_YET = "SKL-OIA-06 (generate_followups) — implemented by G-04"


class GenerateFollowups(StreamingSkill):
    """Suggest follow-up questions for a partially answered question.

    Streaming: output guardrails run per yielded chunk, not once at the end.
    """

    def stream(self, context: SkillContext) -> AsyncIterator[dict[str, Any]]:
        raise NotImplementedError(_NOT_YET)
