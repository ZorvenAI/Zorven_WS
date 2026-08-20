"""H-01 — photo capture with usage tagging (AC-1 … AC-4).

The consent gate, the tag requirement and the GCS landing path are the parts
that matter. This follows the same pattern as test_recording_api.py:
force-authenticate, real Postgres, GCS mocked.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from unittest.mock import patch, MagicMock

from apps.onboarding.tests.factories import (
    make_company,
    make_consent,
    make_session,
)
from onboarding.models import BrandAsset
from tenants.models import Membership, Tenant

pytestmark = pytest.mark.django_db

SESSIONS = "/api/v1/onboarding/sessions/"


def client_for(user, tenant) -> APIClient:
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    client.force_authenticate(user=user)
    client.defaults["HTTP_X_TENANT_ID"] = str(tenant.id)
    return client


def member(tenant, role, username) -> User:
    user = User.objects.create_user(
        username=username, email=f"{username}@test.com", password="TestPass123!"
    )
    Membership.objects.create(user=user, tenant=tenant, role=role)
    return user


def make_photo(name="storefront.jpg", size=2048):
    return SimpleUploadedFile(
        name, b"\xff\xd8" + b"\x00" * size, content_type="image/jpeg"
    )


def make_video(name="snippet.webm", size=4096, content_type="video/webm"):
    return SimpleUploadedFile(
        name, b"\x1a\x45\xdf\xa3" + b"\x00" * size, content_type=content_type
    )


@pytest.fixture
def editor(public_tenant):
    return member(public_tenant, Membership.Role.EDITOR, "h01_editor")


@pytest.fixture
def viewer(public_tenant):
    return member(public_tenant, Membership.Role.VIEWER, "h01_viewer")


@pytest.fixture
def consented_session(public_tenant):
    company = make_company(tenant=public_tenant)
    session = make_session(company=company, tenant=public_tenant)
    make_consent(session=session, tenant=public_tenant)
    return session


def media_url(session_id):
    return f"{SESSIONS}{session_id}/media/"


# ── AC-3 · happy path ───────────────────────────────────────────────


@patch("apps.onboarding.views.gcs_service")
@patch("apps.onboarding.views.get_pipeline_service")
def test_capture_returns_201(
    mock_pipeline, mock_gcs, public_tenant, editor, consented_session
):
    mock_gcs.get_bucket.return_value = MagicMock()
    mock_gcs.bucket_name = "test-bucket"
    client = client_for(editor, public_tenant)

    resp = client.post(
        media_url(consented_session.pk),
        {"file": make_photo(), "usage_tag": "business_photo"},
        format="multipart",
    )
    assert resp.status_code == 201, resp.data
    assert resp.data["usage_tag"] == "business_photo"
    assert resp.data["file_name"] == "storefront.jpg"


# ── AC-1 · consent gate ─────────────────────────────────────────────


def test_capture_without_consent_403(public_tenant, editor):
    company = make_company(tenant=public_tenant, name="No Consent Co")
    session = make_session(company=company, tenant=public_tenant)
    client = client_for(editor, public_tenant)

    resp = client.post(
        media_url(session.pk),
        {"file": make_photo(), "usage_tag": "business_photo"},
        format="multipart",
    )
    assert resp.status_code == 403
    assert resp.data["code"] == "ERR-03"


# ── AC-3 · role gate ────────────────────────────────────────────────


def test_capture_as_viewer_403(public_tenant, viewer, consented_session):
    client = client_for(viewer, public_tenant)

    resp = client.post(
        media_url(consented_session.pk),
        {"file": make_photo(), "usage_tag": "business_photo"},
        format="multipart",
    )
    assert resp.status_code == 403


# ── AC-2 · tag validation ───────────────────────────────────────────


def test_capture_without_tag_400(public_tenant, editor, consented_session):
    client = client_for(editor, public_tenant)

    resp = client.post(
        media_url(consented_session.pk),
        {"file": make_photo()},
        format="multipart",
    )
    assert resp.status_code == 400
    assert "usage_tag" in resp.data


def test_capture_with_invalid_tag_400(public_tenant, editor, consented_session):
    client = client_for(editor, public_tenant)

    resp = client.post(
        media_url(consented_session.pk),
        {"file": make_photo(), "usage_tag": "selfie"},
        format="multipart",
    )
    assert resp.status_code == 400
    assert "usage_tag" in resp.data


VALID_TAGS = [
    "business_photo",
    "previous_ad",
    "brand_asset",
    "identity_document",
    "other",
]


@pytest.mark.parametrize("tag", VALID_TAGS)
@patch("apps.onboarding.views.gcs_service")
@patch("apps.onboarding.views.get_pipeline_service")
def test_each_valid_tag_accepted(mock_pipeline, mock_gcs, tag, public_tenant, editor):
    mock_gcs.get_bucket.return_value = MagicMock()
    mock_gcs.bucket_name = "test-bucket"
    company = make_company(tenant=public_tenant, name=f"Co-{tag}")
    session = make_session(company=company, tenant=public_tenant)
    make_consent(session=session, tenant=public_tenant)
    client = client_for(editor, public_tenant)

    resp = client.post(
        media_url(session.pk),
        {"file": make_photo(name=f"{tag}.jpg"), "usage_tag": tag},
        format="multipart",
    )
    assert resp.status_code == 201, resp.data
    assert resp.data["usage_tag"] == tag


# ── AC-3 · asset registration ───────────────────────────────────────


@patch("apps.onboarding.views.gcs_service")
@patch("apps.onboarding.views.get_pipeline_service")
def test_asset_registered_with_session_and_tag(
    mock_pipeline, mock_gcs, public_tenant, editor, consented_session
):
    mock_gcs.get_bucket.return_value = MagicMock()
    mock_gcs.bucket_name = "test-bucket"
    client = client_for(editor, public_tenant)

    resp = client.post(
        media_url(consented_session.pk),
        {"file": make_photo(name="logo.png"), "usage_tag": "brand_asset"},
        format="multipart",
    )
    assert resp.status_code == 201
    asset = BrandAsset.objects.get(pk=resp.data["id"])
    assert asset.usage_tag == "brand_asset"
    assert asset.onboarding_session_id == consented_session.pk


@patch("apps.onboarding.views.gcs_service")
@patch("apps.onboarding.views.get_pipeline_service")
def test_gcs_path_matches_landing_convention(
    mock_pipeline, mock_gcs, public_tenant, editor, consented_session
):
    mock_gcs.get_bucket.return_value = MagicMock()
    mock_gcs.bucket_name = "test-bucket"
    client = client_for(editor, public_tenant)

    resp = client.post(
        media_url(consented_session.pk),
        {"file": make_photo(name="receipt.jpg"), "usage_tag": "other"},
        format="multipart",
    )
    assert resp.status_code == 201
    asset = BrandAsset.objects.get(pk=resp.data["id"])
    assert asset.gcs_path.startswith(f"_landing/{public_tenant.id}/")
    assert asset.gcs_path.endswith("_receipt.jpg")


@patch("apps.onboarding.views.gcs_service")
@patch("apps.onboarding.views.get_pipeline_service")
def test_pipeline_event_published(
    mock_pipeline, mock_gcs, public_tenant, editor, consented_session
):
    mock_gcs.get_bucket.return_value = MagicMock()
    mock_gcs.bucket_name = "test-bucket"
    pipeline_svc = MagicMock()
    mock_pipeline.return_value = pipeline_svc
    client = client_for(editor, public_tenant)

    resp = client.post(
        media_url(consented_session.pk),
        {"file": make_photo(name="ad.jpg"), "usage_tag": "previous_ad"},
        format="multipart",
    )
    assert resp.status_code == 201
    pipeline_svc.publish_asset_event.assert_called_once()


# ── AC-3 · idempotency ──────────────────────────────────────────────


@patch("apps.onboarding.views.gcs_service")
@patch("apps.onboarding.views.get_pipeline_service")
def test_duplicate_upload_idempotent(
    mock_pipeline, mock_gcs, public_tenant, editor, consented_session
):
    mock_gcs.get_bucket.return_value = MagicMock()
    mock_gcs.bucket_name = "test-bucket"
    client = client_for(editor, public_tenant)

    first = client.post(
        media_url(consented_session.pk),
        {"file": make_photo(name="dup.jpg"), "usage_tag": "business_photo"},
        format="multipart",
    )
    assert first.status_code == 201

    second = client.post(
        media_url(consented_session.pk),
        {"file": make_photo(name="dup.jpg"), "usage_tag": "business_photo"},
        format="multipart",
    )
    assert second.status_code == 200
    assert BrandAsset.objects.filter(file_name="dup.jpg").count() == 1


# ── AC-3 · cross-tenant ─────────────────────────────────────────────


def test_cross_tenant_returns_404(public_tenant, editor, consented_session):
    other_tenant = Tenant.objects.create(name="Other Org", schema_name="other_org")
    other_user = member(other_tenant, Membership.Role.EDITOR, "h01_other_ed")
    client = client_for(other_user, other_tenant)

    resp = client.post(
        media_url(consented_session.pk),
        {"file": make_photo(), "usage_tag": "business_photo"},
        format="multipart",
    )
    assert resp.status_code == 404


# ── Content-type validation ──────────────────────────────────────────


def test_non_image_content_type_rejected(public_tenant, editor, consented_session):
    client = client_for(editor, public_tenant)
    bad_file = SimpleUploadedFile(
        "malware.exe", b"\x00" * 100, content_type="application/x-msdownload"
    )
    resp = client.post(
        media_url(consented_session.pk),
        {"file": bad_file, "usage_tag": "other"},
        format="multipart",
    )
    assert resp.status_code == 400
    assert "file" in resp.data


# ── Race condition (IntegrityError) ──────────────────────────────────


@patch("apps.onboarding.views.gcs_service")
@patch("apps.onboarding.views.get_pipeline_service")
def test_concurrent_duplicate_returns_200_not_500(
    mock_pipeline, mock_gcs, public_tenant, editor, consented_session
):
    """Two concurrent uploads of the same filename should not 500."""
    from django.db.utils import IntegrityError

    mock_gcs.get_bucket.return_value = MagicMock()
    mock_gcs.bucket_name = "test-bucket"
    client = client_for(editor, public_tenant)

    # Pre-create the asset so the recovery filter inside the except block
    # can find it after IntegrityError.
    BrandAsset.objects.create(
        tenant=public_tenant,
        company=consented_session.company,
        file_name="race.jpg",
        file_type="image",
        file_size=100,
        gcs_path="_landing/x/race.jpg",
    )

    # Simulate the TOCTOU window: the first filter (dedup check) misses,
    # create() hits the unique constraint, the second filter (recovery)
    # finds the existing row.
    original_filter = BrandAsset.objects.filter
    call_count = {"n": 0}

    def race_filter(*args, **kwargs):
        qs = original_filter(*args, **kwargs)
        if kwargs.get("file_name") == "race.jpg":
            call_count["n"] += 1
            if call_count["n"] == 1:
                return qs.none()
        return qs

    original_create = BrandAsset.objects.create

    def race_create(**kwargs):
        if kwargs.get("file_name") == "race.jpg":
            raise IntegrityError("duplicate key")
        return original_create(**kwargs)

    with (
        patch.object(BrandAsset.objects, "filter", side_effect=race_filter),
        patch.object(BrandAsset.objects, "create", side_effect=race_create),
    ):
        resp = client.post(
            media_url(consented_session.pk),
            {"file": make_photo(name="race.jpg"), "usage_tag": "business_photo"},
            format="multipart",
        )

    assert resp.status_code == 200


# ── H-02 · video snippet capture ───────────────────────────────────


@patch("apps.onboarding.views.gcs_service")
@patch("apps.onboarding.views.get_pipeline_service")
def test_video_webm_accepted_201(
    mock_pipeline, mock_gcs, public_tenant, editor, consented_session
):
    mock_gcs.get_bucket.return_value = MagicMock()
    mock_gcs.bucket_name = "test-bucket"
    client = client_for(editor, public_tenant)

    resp = client.post(
        media_url(consented_session.pk),
        {"file": make_video(), "usage_tag": "business_photo"},
        format="multipart",
    )
    assert resp.status_code == 201, resp.data
    assert resp.data["file_name"] == "snippet.webm"


@patch("apps.onboarding.views.gcs_service")
@patch("apps.onboarding.views.get_pipeline_service")
def test_video_mp4_accepted_201(
    mock_pipeline, mock_gcs, public_tenant, editor, consented_session
):
    mock_gcs.get_bucket.return_value = MagicMock()
    mock_gcs.bucket_name = "test-bucket"
    client = client_for(editor, public_tenant)

    resp = client.post(
        media_url(consented_session.pk),
        {
            "file": make_video(name="clip.mp4", content_type="video/mp4"),
            "usage_tag": "brand_asset",
        },
        format="multipart",
    )
    assert resp.status_code == 201, resp.data


@patch("apps.onboarding.views.gcs_service")
@patch("apps.onboarding.views.get_pipeline_service")
def test_video_asset_has_file_type_video(
    mock_pipeline, mock_gcs, public_tenant, editor, consented_session
):
    mock_gcs.get_bucket.return_value = MagicMock()
    mock_gcs.bucket_name = "test-bucket"
    client = client_for(editor, public_tenant)

    resp = client.post(
        media_url(consented_session.pk),
        {"file": make_video(name="demo.webm"), "usage_tag": "other"},
        format="multipart",
    )
    assert resp.status_code == 201
    asset = BrandAsset.objects.get(pk=resp.data["id"])
    assert asset.file_type == "video"


@patch("apps.onboarding.views.gcs_service")
@patch("apps.onboarding.views.get_pipeline_service")
def test_video_asset_registered_with_session(
    mock_pipeline, mock_gcs, public_tenant, editor, consented_session
):
    mock_gcs.get_bucket.return_value = MagicMock()
    mock_gcs.bucket_name = "test-bucket"
    client = client_for(editor, public_tenant)

    resp = client.post(
        media_url(consented_session.pk),
        {"file": make_video(name="session-vid.webm"), "usage_tag": "brand_asset"},
        format="multipart",
    )
    assert resp.status_code == 201
    asset = BrandAsset.objects.get(pk=resp.data["id"])
    assert asset.onboarding_session_id == consented_session.pk


@patch("apps.onboarding.views.gcs_service")
@patch("apps.onboarding.views.get_pipeline_service")
def test_video_duplicate_idempotent(
    mock_pipeline, mock_gcs, public_tenant, editor, consented_session
):
    mock_gcs.get_bucket.return_value = MagicMock()
    mock_gcs.bucket_name = "test-bucket"
    client = client_for(editor, public_tenant)

    first = client.post(
        media_url(consented_session.pk),
        {"file": make_video(name="dup.webm"), "usage_tag": "business_photo"},
        format="multipart",
    )
    assert first.status_code == 201

    second = client.post(
        media_url(consented_session.pk),
        {"file": make_video(name="dup.webm"), "usage_tag": "business_photo"},
        format="multipart",
    )
    assert second.status_code == 200
    assert BrandAsset.objects.filter(file_name="dup.webm").count() == 1


@patch("apps.onboarding.views.gcs_service")
@patch("apps.onboarding.views.get_pipeline_service")
def test_image_still_accepted_after_video_support(
    mock_pipeline, mock_gcs, public_tenant, editor, consented_session
):
    """Regression: image/jpeg still works after widening to accept video."""
    mock_gcs.get_bucket.return_value = MagicMock()
    mock_gcs.bucket_name = "test-bucket"
    client = client_for(editor, public_tenant)

    resp = client.post(
        media_url(consented_session.pk),
        {"file": make_photo(name="regression.jpg"), "usage_tag": "business_photo"},
        format="multipart",
    )
    assert resp.status_code == 201
    asset = BrandAsset.objects.get(pk=resp.data["id"])
    assert asset.file_type == "image"


def test_unsupported_type_still_rejected(public_tenant, editor, consented_session):
    """application/x-msdownload still rejected after widening."""
    client = client_for(editor, public_tenant)
    bad_file = SimpleUploadedFile(
        "payload.exe", b"\x00" * 100, content_type="application/x-msdownload"
    )
    resp = client.post(
        media_url(consented_session.pk),
        {"file": bad_file, "usage_tag": "other"},
        format="multipart",
    )
    assert resp.status_code == 400
    assert "file" in resp.data
