"""Event type enum and emitter.

Design §12 · implemented by story A-03.

Scaffolded by A-05. The body raises NotImplementedError deliberately: a
stub that silently returns None would let a later story ship a no-op
that passes its tests.
"""

from __future__ import annotations

_NOT_YET = "app.events.catalog — implemented by A-03"


class EventType:
    """Not yet implemented."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError(_NOT_YET)
