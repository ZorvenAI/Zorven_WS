"""Hardcoded production-equivalent prompts used when POI is unreachable.

Design §17.2 · implemented by story C-01.

Scaffolded by A-05. The body raises NotImplementedError deliberately: a
stub that silently returns None would let a later story ship a no-op
that passes its tests.
"""

from __future__ import annotations

_NOT_YET = "app.prompts.fallbacks — implemented by C-01"


def get_fallback_prompts() -> dict[str, str]:
    """Not yet implemented."""
    raise NotImplementedError(_NOT_YET)
