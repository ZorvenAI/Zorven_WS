"""Request and response models for the HTTP and WebSocket surfaces.

Design §10.2 · implemented by story A-06.

Scaffolded by A-05. The body raises NotImplementedError deliberately: a
stub that silently returns None would let a later story ship a no-op
that passes its tests.
"""

from __future__ import annotations

_NOT_YET = "app.api.schemas — implemented by A-06"


class ExecuteRequest:
    """Not yet implemented."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError(_NOT_YET)
