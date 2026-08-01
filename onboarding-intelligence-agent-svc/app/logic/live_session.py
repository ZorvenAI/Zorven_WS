"""LiveSessionManager — socket lifecycle, speaker-turn batcher, WS protocol.

Design §4.3, §9.2 · implemented by story F-04.

Scaffolded by A-05. The body raises NotImplementedError deliberately: a
stub that silently returns None would let a later story ship a no-op
that passes its tests.
"""

from __future__ import annotations

_NOT_YET = "app.logic.live_session — implemented by F-04"


class LiveSessionManager:
    """Not yet implemented.

    Analysis batches on a speaker change or a 4 s silence, not a fixed timer:
    a 400 ms window mid-sentence produces a fragment no sufficiency prompt can
    score.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError(_NOT_YET)
