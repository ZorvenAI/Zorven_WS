"""Live session hash and list accessors.

Design §14 · implemented by story F-04.

Scaffolded by A-05. The body raises NotImplementedError deliberately: a
stub that silently returns None would let a later story ship a no-op
that passes its tests.
"""

from __future__ import annotations

_NOT_YET = "app.cache.session_store — implemented by F-04"


class SessionStore:
    """Not yet implemented.

    Keys come from app.cache.redis_manager so the oia:v1: prefix and the TTL
    policy are enforced in one place.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError(_NOT_YET)
