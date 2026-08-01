"""Prompt loader — POI registry, then Redis DB 2 cache, then fallback.

Design §17.2 · implemented by story C-01.

Scaffolded by A-05. The body raises NotImplementedError deliberately: a
stub that silently returns None would let a later story ship a no-op
that passes its tests.
"""

from __future__ import annotations

_NOT_YET = "app.prompts.loader — implemented by C-01"


class PromptLoader:
    """Not yet implemented.

    The cache is read-only and lives under the poi: prefix in the same database
    OIA writes to. This service never writes there.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError(_NOT_YET)
