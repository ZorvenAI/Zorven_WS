"""M-02 · Registry completeness and store-order validation tests."""

from __future__ import annotations

import pytest

from apps.onboarding.erasure.registry import (
    REQUIRED_ARTIFACT_TYPES,
    ErasureManifest,
    ErasureStore,
    RegistryIncomplete,
    StoreRegistry,
    StoreResult,
)
from apps.onboarding.erasure.stores.django_brand_assets import (
    DjangoBrandAssetStore,
)
from apps.onboarding.erasure.stores.django_sessions import DjangoSessionStore
from apps.onboarding.erasure.stores.gcs_blobs import GCSBlobStore
from apps.onboarding.erasure.stores.oia_redis import OIARedisStore
from apps.onboarding.erasure.stores.poi_golden_datasets import POIGoldenStore
from apps.onboarding.erasure.stores.rag_index_store import RAGIndexStore

ALL_STORE_CLASSES = [
    DjangoBrandAssetStore,
    DjangoSessionStore,
    GCSBlobStore,
    OIARedisStore,
    POIGoldenStore,
    RAGIndexStore,
]


@pytest.fixture(autouse=True)
def _reset_registry():
    StoreRegistry.reset()
    yield
    StoreRegistry.reset()


def _register_all_stores():
    for cls in ALL_STORE_CLASSES:
        StoreRegistry.register(cls)


class TestRegistryCompleteness:
    def test_all_stores_cover_all_artifact_types(self):
        _register_all_stores()
        covered = set()
        for store_cls in StoreRegistry.all_stores():
            covered.update(store_cls.artifact_types)
        assert covered == REQUIRED_ARTIFACT_TYPES

    def test_validate_completeness_passes_when_all_registered(self):
        _register_all_stores()
        StoreRegistry.validate_completeness()

    def test_validate_completeness_raises_when_incomplete(self):
        with pytest.raises(RegistryIncomplete):
            StoreRegistry.validate_completeness()

    def test_store_names_match_order(self):
        from apps.onboarding.erasure.cascade import STORE_ORDER

        _register_all_stores()
        assert StoreRegistry.store_names() == frozenset(STORE_ORDER)

    def test_register_returns_class_unchanged(self):
        @StoreRegistry.register
        class DummyStore(ErasureStore):
            store_name = "dummy_test"
            artifact_types = ()

            def collect(self, tenant_id, session_ids, subject_name):
                return ErasureManifest(store_name=self.store_name)

            def erase(self, manifest):
                return StoreResult(store_name=self.store_name)

        assert DummyStore.store_name == "dummy_test"
        assert "dummy_test" in StoreRegistry.store_names()


class TestDataClasses:
    def test_erasure_manifest_defaults(self):
        m = ErasureManifest(store_name="test")
        assert m.item_count == 0
        assert m.details == {}

    def test_store_result_ok_when_no_errors(self):
        r = StoreResult(store_name="test", items_erased=3)
        assert r.ok is True

    def test_store_result_not_ok_when_errors(self):
        r = StoreResult(store_name="test", errors=["boom"])
        assert r.ok is False
