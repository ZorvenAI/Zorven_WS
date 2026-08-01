"""GCS resumable upload and signed URL issuance.

Design §8.4 · implemented by story F-02.

Scaffolded by A-05. The body raises NotImplementedError deliberately: a
stub that silently returns None would let a later story ship a no-op
that passes its tests.
"""

from __future__ import annotations

_NOT_YET = "app.providers.storage — implemented by F-02"


class StorageProvider:
    """Not yet implemented."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError(_NOT_YET)
