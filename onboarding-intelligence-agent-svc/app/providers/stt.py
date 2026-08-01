"""Speech-to-text provider — ABC plus the Google STT v2 implementation.

Design §8.4 · implemented by story F-05.

Scaffolded by A-05. The body raises NotImplementedError deliberately: a
stub that silently returns None would let a later story ship a no-op
that passes its tests.
"""

from __future__ import annotations

_NOT_YET = "app.providers.stt — implemented by F-05"


class STTProvider:
    """Not yet implemented.

    Spike A-01 measured streaming latency at p95 410 ms against a 2 s budget,
    and established that STT v2 StreamingRecognize does NOT support speaker
    diarization — speaker attribution needs another mechanism. See
    docs/spikes/A-01-stt-v2-measurement-note.md.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError(_NOT_YET)
