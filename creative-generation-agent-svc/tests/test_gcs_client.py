"""Unit tests for GCSClient URL-generation branches."""

from unittest.mock import MagicMock

import pytest

from app.services.gcs_client import GCSClient


def _make_client_with_fake_bucket(blob_mock: MagicMock) -> GCSClient:
    client = GCSClient(
        project_id="proj",
        bucket_name="bkt",
        credentials_json="",
        credentials_path="",
    )
    # Bypass _ensure_client so we don't touch google-cloud-storage.
    client._client = MagicMock()
    bucket = MagicMock()
    bucket.blob.return_value = blob_mock
    client._bucket = bucket
    return client


async def test_upload_image_returns_signed_url_on_success():
    blob = MagicMock()
    blob.upload_from_string = MagicMock(return_value=None)
    blob.generate_signed_url = MagicMock(
        return_value="https://storage.googleapis.com/bkt/signed?sig=abc"
    )
    client = _make_client_with_fake_bucket(blob)

    url = await client.upload_image(
        tenant_id="11",
        job_id="job-1",
        image_data=b"\x89PNGfakebytes",
        filename="ad_v1_1x1.png",
    )

    assert url == "https://storage.googleapis.com/bkt/signed?sig=abc"
    blob.generate_signed_url.assert_called_once()
    kwargs = blob.generate_signed_url.call_args.kwargs
    assert kwargs["version"] == "v4"
    assert kwargs["method"] == "GET"


async def test_upload_image_falls_back_to_public_url_when_signing_fails():
    blob = MagicMock()
    blob.upload_from_string = MagicMock(return_value=None)
    blob.generate_signed_url = MagicMock(
        side_effect=AttributeError("you need a private key to sign credentials")
    )
    # blob.public_url already handles URL-encoding of reserved characters.
    blob.public_url = (
        "https://storage.googleapis.com/bkt/cga/11/job-1/" "images/ad%20v1_1x1.png"
    )
    client = _make_client_with_fake_bucket(blob)

    url = await client.upload_image(
        tenant_id="11",
        job_id="job-1",
        image_data=b"\x89PNGfakebytes",
        filename="ad v1_1x1.png",
    )

    assert url == blob.public_url
    assert "%20" in url  # encoded space survived the fallback
    blob.generate_signed_url.assert_called_once()


async def test_upload_image_returns_data_uri_when_gcs_not_configured():
    client = GCSClient(bucket_name="")  # _ensure_client() will return False
    url = await client.upload_image(
        tenant_id="11",
        job_id="job-1",
        image_data=b"somebytes-longer-than-8",
        filename="ad.png",
        content_type="image/png",
    )
    assert url.startswith("data:image/png;base64,")
