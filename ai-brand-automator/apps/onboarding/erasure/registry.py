"""M-02 · GDPR erasure store registry.

Design §20, FR-GDPR-04. Registry-driven so a store added later cannot
be forgotten — the completeness test catches it.
"""

from __future__ import annotations

import dataclasses
import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)

REQUIRED_ARTIFACT_TYPES = frozenset(
    {
        "recordings",
        "transcripts",
        "captured_media",
        "summaries",
        "provenance",
        "rag_entries",
        "golden_candidates",
    }
)


@dataclasses.dataclass
class ErasureManifest:
    """What a store found and plans to erase."""

    store_name: str
    item_count: int = 0
    details: dict[str, Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class StoreResult:
    """Outcome of one store's erase() call."""

    store_name: str
    items_erased: int = 0
    errors: list[str] = dataclasses.field(default_factory=list)
    caveats: list[str] = dataclasses.field(default_factory=list)
    details: dict[str, Any] = dataclasses.field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclasses.dataclass
class CompletionReport:
    """Aggregate result of the full cascade."""

    tenant_id: str
    subject_name: str
    requested_by: str
    reason: str
    store_results: list[StoreResult] = dataclasses.field(default_factory=list)
    completeness_verified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "subject_name": self.subject_name,
            "requested_by": self.requested_by,
            "reason": self.reason,
            "completeness_verified": self.completeness_verified,
            "stores": {
                r.store_name: {
                    "items_erased": r.items_erased,
                    "errors": r.errors,
                    "caveats": r.caveats,
                    "details": r.details,
                }
                for r in self.store_results
            },
        }


class ErasureStore(ABC):
    """One physical data store that holds subject data."""

    store_name: str = ""
    artifact_types: tuple[str, ...] = ()

    @abstractmethod
    def collect(
        self,
        tenant_id: str,
        session_ids: list[int],
        subject_name: str,
    ) -> ErasureManifest:
        """Identify what will be erased. Runs BEFORE any deletion."""

    @abstractmethod
    def erase(self, manifest: ErasureManifest) -> StoreResult:
        """Delete everything identified in the manifest."""


class RegistryIncomplete(RuntimeError):
    """Raised when the registry does not cover all required artifact types."""


class StoreRegistry:
    """Auto-registration registry for erasure stores.

    AC-2: a store not registered fails the cascade's completeness test.
    """

    _stores: dict[str, type[ErasureStore]] = {}

    @classmethod
    def register(cls, store_cls: type[ErasureStore]) -> type[ErasureStore]:
        cls._stores[store_cls.store_name] = store_cls
        return store_cls

    @classmethod
    def all_stores(cls) -> list[type[ErasureStore]]:
        return list(cls._stores.values())

    @classmethod
    def store_names(cls) -> frozenset[str]:
        return frozenset(cls._stores.keys())

    @classmethod
    def validate_completeness(cls) -> None:
        covered: set[str] = set()
        for store_cls in cls._stores.values():
            covered.update(store_cls.artifact_types)
        missing = REQUIRED_ARTIFACT_TYPES - covered
        if missing:
            raise RegistryIncomplete(
                f"artifact types not covered by any store: {sorted(missing)}"
            )

    @classmethod
    def reset(cls) -> None:
        """Test helper — clear the registry."""
        cls._stores = {}
