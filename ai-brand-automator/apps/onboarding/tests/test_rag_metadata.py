"""B-02 AC-4 — usage_tag reaches RAG document metadata.

The card's technical note warns that usage_tag and ocr_text are "orphaned
until someone notices in WF3" if the payload builder is not extended. There
was no builder carrying BrandAsset columns at all: ``to_rag_document`` built
its metadata from ``struct_data``, which comes from media *content* (Video
Intelligence labels, speech transcriptions), and the ``DocumentMetadata``
object populated with original_filename never reached the payload. So this
file tests a path that B-02 created rather than one it modified.

ocr_text is deliberately absent, and that absence is asserted rather than
merely unimplemented — see ``test_ocr_text_is_not_carried_yet``.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from media_curation.domain.models import CuratedDocument

pytestmark = pytest.mark.unit


def make_document(**kwargs) -> CuratedDocument:
    defaults = {
        "trace_id": uuid4(),
        "tenant_id": "t-1",
        "file_id": uuid4(),
        "source_gcs_uri": "gs://zorven-raw-assets/_raw/t-1/ad.jpg",
        "mime_type": "image/jpeg",
        "extracted_text": "Half price espresso this week",
    }
    defaults.update(kwargs)
    return CuratedDocument(**defaults)


def test_usage_tag_in_rag_payload():
    """The named case from the card: the tag reaches RAG metadata."""
    payload = make_document(usage_tag="previous_ad").to_rag_document()
    assert payload["metadata"]["usage_tag"] == "previous_ad"


def test_usage_tag_survives_alongside_struct_data():
    """struct_data is spread into the same dict, so it could shadow the tag."""
    document = make_document(
        usage_tag="previous_ad",
        struct_data={"labels": ["coffee"], "has_speech": False},
    )
    metadata = document.to_rag_document()["metadata"]

    assert metadata["usage_tag"] == "previous_ad"
    assert metadata["labels"] == ["coffee"]
    assert metadata["file_id"] and metadata["trace_id"]


def test_an_untagged_asset_is_unchanged():
    """Every asset uploaded before B-02 has no tag; none may gain a null key.

    A null usage_tag in the payload would be indexed by Vertex AI as a real
    value, so an absent tag has to stay absent rather than become None.
    """
    metadata = make_document().to_rag_document()["metadata"]
    assert "usage_tag" not in metadata


def test_the_rest_of_the_payload_is_untouched():
    """AC-4's compatibility half, at the payload level."""
    payload = make_document(usage_tag="brand_asset").to_rag_document()
    for key in (
        "id",
        "tenant_id",
        "content",
        "source_path",
        "file_type",
        "content_type",
        "created_at",
        "metadata",
    ):
        assert key in payload, key
    assert payload["content"] == "Half price espresso this week"


# ── The H-03 seam ────────────────────────────────────────────────────


def test_ocr_text_is_not_carried_yet():
    """ocr_text is H-03's, and its absence here is deliberate.

    OCR runs after upload, so at ingestion-event time the column is always
    null; carrying it now would ship null on every document while looking
    wired up. H-03 must re-sync the document once redaction has run and then
    change this test — which is the point of asserting it. A silently missing
    field would be rediscovered in WF3 instead.

    H-03 also has to settle a conflict B-02 left open: Design §10.1 says carry
    ocr_text into RAG metadata, while NFR-PRIV-02 says no event payload
    carries media content, and the transport is a Kafka topic.
    """
    document = make_document(usage_tag="identity_document")
    assert not hasattr(document, "ocr_text"), (
        "CuratedDocument grew an ocr_text field — if this is H-03, resolve "
        "the §10.1 vs NFR-PRIV-02 conflict before carrying it."
    )
    assert "ocr_text" not in document.to_rag_document()["metadata"]


# ── AC-4 · the existing serializer contract is unchanged ─────────────


@pytest.mark.django_db
def test_a_payload_without_any_new_field_still_validates():
    """The pre-B-02 client payload, verbatim."""
    from onboarding.serializers import BrandAssetSerializer

    from apps.onboarding.tests.factories import make_company

    company = make_company()
    serializer = BrandAssetSerializer(
        data={
            "company": company.pk,
            "file_name": "storefront.jpg",
            "file_type": "image",
            "file_size": 2048,
            "gcs_path": "_raw/t-1/storefront.jpg",
        }
    )
    assert serializer.is_valid(), serializer.errors
    asset = serializer.save()
    assert asset.usage_tag is None and asset.ocr_text is None


@pytest.mark.django_db
def test_ocr_fields_are_read_only_to_clients():
    """PG-08: only H-03 writes these, and it does not go through the API."""
    from onboarding.serializers import BrandAssetSerializer

    from apps.onboarding.tests.factories import make_company

    company = make_company()
    serializer = BrandAssetSerializer(
        data={
            "company": company.pk,
            "file_name": "id-card.jpg",
            "file_type": "image",
            "file_size": 1024,
            "gcs_path": "_raw/t-1/id-card.jpg",
            "usage_tag": "identity_document",
            "ocr_text": "Passport No. X1234567",
            "ocr_confidence": 0.99,
        }
    )
    assert serializer.is_valid(), serializer.errors
    asset = serializer.save()

    assert asset.usage_tag == "identity_document"
    assert asset.ocr_text is None, "a client wrote unredacted text into ocr_text"
    assert asset.ocr_confidence is None


# ── The traversal · event metadata → curated document → RAG payload ──


def test_curation_carries_usage_tag_off_the_event():
    """The hop that had no carrier before B-02.

    ``media_curation`` is a hexagonal app and must not import the Django ORM,
    so it cannot read BrandAsset.usage_tag itself — the value has to arrive on
    the event. This asserts the real ``_build_curated_document``, not a stand-in.
    """
    from media_curation.domain.models import CurationEvent, ProcessorResult
    from media_curation.domain.services import CurationService

    event = CurationEvent(
        tenant_id="t-1",
        file_id=uuid4(),
        raw_gcs_uri="gs://zorven-raw-assets/_raw/t-1/ad.jpg",
        mime_type="image/jpeg",
        metadata={"original_filename": "ad.jpg", "usage_tag": "previous_ad"},
    )

    document = CurationService._build_curated_document(
        None,
        event=event,
        extracted_text="Half price espresso",
        processor_result=ProcessorResult(
            source_gcs_uri=event.raw_gcs_uri, mime_type=event.mime_type
        ),
        pii_redacted=False,
    )

    assert document.usage_tag == "previous_ad"
    assert document.to_rag_document()["metadata"]["usage_tag"] == "previous_ad"


def test_curation_survives_an_event_with_no_metadata():
    """Every event produced before B-02 carries no usage_tag, and many carry
    no metadata at all — neither may raise."""
    from media_curation.domain.models import CurationEvent, ProcessorResult
    from media_curation.domain.services import CurationService

    event = CurationEvent(
        tenant_id="t-1",
        file_id=uuid4(),
        raw_gcs_uri="gs://zorven-raw-assets/_raw/t-1/old.jpg",
        mime_type="image/jpeg",
        metadata=None,
    )

    document = CurationService._build_curated_document(
        None,
        event=event,
        extracted_text="",
        processor_result=ProcessorResult(
            source_gcs_uri=event.raw_gcs_uri, mime_type=event.mime_type
        ),
        pii_redacted=False,
    )

    assert document.usage_tag is None
    assert "usage_tag" not in document.to_rag_document()["metadata"]


@pytest.mark.django_db
def test_the_ingestion_event_builder_includes_usage_tag():
    """The producing end: Django puts the tag on the event in the first place."""
    from onboarding.services import OnboardingPipelineService

    from apps.onboarding.tests.factories import make_brand_asset

    asset = make_brand_asset(usage_tag="business_photo")
    event = OnboardingPipelineService()._build_ingestion_event(asset, uuid4())

    assert event["metadata"]["usage_tag"] == "business_photo"
