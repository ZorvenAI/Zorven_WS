"""Write deduplication for retried dispatches.

Design §18.1 · implemented by story B-06.

Scaffolded by A-05. The body raises NotImplementedError deliberately: a
stub that silently returns None would let a later story ship a no-op
that passes its tests.
"""

from __future__ import annotations

_NOT_YET = "app.cache.idempotency — implemented by B-06"


class IdempotencyGuard:
    """Not yet implemented.

    The PROCESS key is sha256(session_id + evidence_manifest_hash): re-running
    over unchanged evidence returns the original job_id and writes nothing
    twice, while genuinely changed evidence produces a new hash and a real
    re-run.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError(_NOT_YET)
