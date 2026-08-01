"""Shared request dependencies — service-token auth and tenant extraction.

Design §15, §16 · implemented by story A-06.

Scaffolded by A-05. The body raises NotImplementedError deliberately: a
stub that silently returns None would let a later story ship a no-op
that passes its tests.
"""

from __future__ import annotations

_NOT_YET = "app.api.deps — implemented by A-06"


async def verify_service_token(*args: object, **kwargs: object) -> None:
    """Not yet implemented."""
    raise NotImplementedError(_NOT_YET)
