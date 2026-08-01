"""Error taxonomy — ERR-01 … ERR-nn with recoverability flags.

Design §18.4 · implemented by story A-06.

Scaffolded by A-05. The body raises NotImplementedError deliberately: a
stub that silently returns None would let a later story ship a no-op
that passes its tests.
"""

from __future__ import annotations

_NOT_YET = (
    "Error taxonomy — ERR-01 … ERR-nn with recoverability flags. — implemented by A-06"
)


class OIAError:
    """Not yet implemented."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError(_NOT_YET)
