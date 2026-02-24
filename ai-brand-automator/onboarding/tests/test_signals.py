"""
Tests for onboarding signals — specifically the BrandAsset → SessionAttachment
pipeline_status sync signal.
"""

import uuid

import pytest

from ai_services.models import ChatMessage, ChatSession, SessionAttachment
from onboarding.models import BrandAsset, Company


@pytest.fixture
def company(db, public_tenant):
    Company.objects.filter(tenant=public_tenant).delete()
    return Company.objects.create(
        tenant=public_tenant,
        name="Signal Test Company",
        description="Company for signal tests",
    )


@pytest.fixture
def brand_asset(public_tenant, company):
    return BrandAsset.objects.create(
        tenant=public_tenant,
        company=company,
        file_name=f"signal_test_{uuid.uuid4().hex[:6]}.pdf",
        file_type="document",
        file_size=2048,
        gcs_path="_landing/1/signal_test.pdf",
        gcs_bucket="test-bucket",
        pipeline_status="pending",
    )


@pytest.fixture
def session_attachment(public_tenant, brand_asset):
    session = ChatSession.objects.create(
        tenant=public_tenant,
        session_id=str(uuid.uuid4()),
        title="Signal test session",
    )
    message = ChatMessage.objects.create(
        session=session, role="user", content="Attached a file"
    )
    return SessionAttachment.objects.create(
        message=message,
        asset=brand_asset,
        file_name=brand_asset.file_name,
        file_type="document",
        file_size=2048,
        pipeline_status="pending",
    )


class TestSyncSessionAttachmentStatus:
    """Tests for sync_session_attachment_status signal."""

    @pytest.mark.django_db
    def test_ingested_maps_to_processing(self, brand_asset, session_attachment):
        """BrandAsset 'ingested' should cascade to SessionAttachment 'processing'."""
        brand_asset.pipeline_status = "ingested"
        brand_asset.save(update_fields=["pipeline_status"])

        session_attachment.refresh_from_db()
        assert session_attachment.pipeline_status == "processing"

    @pytest.mark.django_db
    def test_curated_maps_to_processing(self, brand_asset, session_attachment):
        """BrandAsset 'curated' should also map to SessionAttachment 'processing'."""
        brand_asset.pipeline_status = "curated"
        brand_asset.save(update_fields=["pipeline_status"])

        session_attachment.refresh_from_db()
        assert session_attachment.pipeline_status == "processing"

    @pytest.mark.django_db
    def test_indexed_maps_to_indexed(self, brand_asset, session_attachment):
        """BrandAsset 'indexed' should cascade to SessionAttachment 'indexed'."""
        brand_asset.pipeline_status = "indexed"
        brand_asset.save(update_fields=["pipeline_status"])

        session_attachment.refresh_from_db()
        assert session_attachment.pipeline_status == "indexed"

    @pytest.mark.django_db
    def test_failed_maps_to_failed(self, brand_asset, session_attachment):
        """BrandAsset 'failed' should cascade to SessionAttachment 'failed'."""
        brand_asset.pipeline_status = "failed"
        brand_asset.save(update_fields=["pipeline_status"])

        session_attachment.refresh_from_db()
        assert session_attachment.pipeline_status == "failed"

    @pytest.mark.django_db
    def test_no_update_when_status_unchanged(self, brand_asset, session_attachment):
        """Signal should skip update when attachment already has correct status."""
        assert session_attachment.pipeline_status == "pending"

        brand_asset.pipeline_status = "pending"
        brand_asset.save(update_fields=["pipeline_status"])

        session_attachment.refresh_from_db()
        assert session_attachment.pipeline_status == "pending"

    @pytest.mark.django_db
    def test_signal_skips_non_status_updates(self, brand_asset, session_attachment):
        """Signal should not fire when update_fields excludes pipeline_status."""
        brand_asset.gcs_path = "raw/1/new_path.pdf"
        brand_asset.save(update_fields=["gcs_path"])

        session_attachment.refresh_from_db()
        assert session_attachment.pipeline_status == "pending"

    @pytest.mark.django_db
    def test_no_attachments_linked(self, brand_asset):
        """Signal should not error when no SessionAttachments are linked."""
        brand_asset.pipeline_status = "indexed"
        brand_asset.save(update_fields=["pipeline_status"])
        # No assertion needed — just verifying no exception is raised

    @pytest.mark.django_db
    def test_multiple_attachments_updated(self, public_tenant, brand_asset):
        """All SessionAttachments linked to the same BrandAsset should update."""
        attachments = []
        for i in range(3):
            session = ChatSession.objects.create(
                tenant=public_tenant,
                session_id=str(uuid.uuid4()),
                title=f"Session {i}",
            )
            msg = ChatMessage.objects.create(
                session=session, role="user", content=f"Msg {i}"
            )
            attachments.append(
                SessionAttachment.objects.create(
                    message=msg,
                    asset=brand_asset,
                    file_name=brand_asset.file_name,
                    file_type="document",
                    file_size=2048,
                    pipeline_status="pending",
                )
            )

        brand_asset.pipeline_status = "indexed"
        brand_asset.save(update_fields=["pipeline_status"])

        for att in attachments:
            att.refresh_from_db()
            assert att.pipeline_status == "indexed"

    @pytest.mark.django_db
    def test_full_pipeline_progression(self, brand_asset, session_attachment):
        """Simulate the full pipeline: pending → ingested → curated → indexed."""
        for asset_status, expected_attachment_status in [
            ("ingested", "processing"),
            ("curated", "processing"),
            ("indexed", "indexed"),
        ]:
            brand_asset.pipeline_status = asset_status
            brand_asset.save(update_fields=["pipeline_status"])
            session_attachment.refresh_from_db()
            assert session_attachment.pipeline_status == expected_attachment_status
