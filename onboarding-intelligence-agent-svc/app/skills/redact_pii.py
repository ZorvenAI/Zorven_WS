"""SKL-OIA-16 — Redact PII from a transcript segment before it is buffered, prompted or
indexed (IG-04).

Design §8.1 · implemented by story F-05.

Registered by A-06: the class exists and the registry resolves and
instantiates it, so the declaration in config/skills.yaml is proven to point
at something real. The body is deferred — it raises NotImplementedError
rather than returning None, so a later story cannot ship a silent no-op.
"""

from __future__ import annotations

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillResult

_NOT_YET = "SKL-OIA-16 (redact_pii) — implemented by F-05"


class RedactPii(BaseSkill):
    """Redact PII from a transcript segment before it is buffered, prompted or indexed
    (IG-04)."""

    async def run(self, context: SkillContext) -> SkillResult:
        raise NotImplementedError(_NOT_YET)
