"""
Tests for GCSService._resolve_credentials() credential resolution logic.

Covers all 3 priority paths:
1. GCS_CREDENTIALS_JSON env var (inline JSON)
2. GS_CREDENTIALS_PATH file on disk
3. Application Default Credentials (ADC)
"""

import json
import os
from unittest import mock

import pytest
from google.oauth2 import service_account

from files.services import GCS_SCOPES, GCSService

# Minimal valid service account JSON structure
FAKE_SA_INFO = {
    "type": "service_account",
    "project_id": "test-project",
    "private_key_id": "key123",
    "private_key": (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEowIBAAKCAQEA2a2rwplBQLF29amygykEMmYz0+Kcj3bKBp29DiB/MFJi4EZ\n"
        "qF5IbGFiMFMCDRBEXlS9d3ZgWKMydnkJMk0mT3Y3gRlKP7mPMpT1GMOeQUo6YNh\n"
        "YFBPUKViBhGP7advz4WZYC2DrLpK+HN3t6WbFB6LzbhS3bFIb6qBOJq5elI1PFn9\n"
        "bAUjt0FhTQCyLOJj2KG7vM9HLPMxx0leodBlJ+sY32K2BVgwfRDz9rMWd2KmDHzy\n"
        "T3DPaXCDRCL+bMCq/PoFfFDu2eLLSWqFrjBmCx+e3P3IKfNFJPavqyLOR5jeobk/\n"
        "s0R7DQoKzxq2RZLPFqmRwIDAQABAoIBADJTKEEwPvQ8b/dl6wd5k0lFH3+lRDrUU\n"
        "-----END RSA PRIVATE KEY-----\n"
    ),
    "client_email": "test@test-project.iam.gserviceaccount.com",
    "client_id": "123456789",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
}


@pytest.fixture
def _disable_gcs_init():
    """Patch settings and storage.Client so GCSService.__init__ doesn't hit GCP."""
    with (
        mock.patch("files.services.settings") as mock_settings,
        mock.patch("files.services.storage.Client"),
    ):
        mock_settings.GS_BUCKET_NAME = "test-bucket"
        mock_settings.GS_PROJECT_ID = "test-project"
        mock_settings.GS_CREDENTIALS_PATH = ""
        yield mock_settings


@pytest.mark.django_db
class TestResolveCredentialsEnvVar:
    """Priority 1: GCS_CREDENTIALS_JSON env var."""

    def test_valid_json_env_var(self, _disable_gcs_init):
        """Valid JSON env var returns scoped service account credentials."""
        env = {"GCS_CREDENTIALS_JSON": json.dumps(FAKE_SA_INFO)}
        with mock.patch.dict(os.environ, env, clear=False):
            with mock.patch.object(
                service_account.Credentials,
                "from_service_account_info",
                return_value=mock.sentinel.creds,
            ) as mock_from_info:
                GCSService()  # noqa: F841 - triggers __init__
                # _resolve_credentials was called by __init__
                mock_from_info.assert_called_once_with(FAKE_SA_INFO, scopes=GCS_SCOPES)

    def test_invalid_json_falls_through(self, _disable_gcs_init):
        """Malformed JSON env var logs a warning and falls through to ADC."""
        env = {"GCS_CREDENTIALS_JSON": "NOT-VALID-JSON"}
        with mock.patch.dict(os.environ, env, clear=False):
            with mock.patch("google.auth.default") as mock_adc:
                mock_adc.return_value = (mock.sentinel.creds, "project")
                GCSService()  # triggers __init__ → _resolve_credentials
                # Should have fallen through to ADC
                mock_adc.assert_called_once_with(scopes=GCS_SCOPES)

    def test_empty_env_var_skipped(self, _disable_gcs_init):
        """Empty or whitespace-only GCS_CREDENTIALS_JSON is treated as absent."""
        env = {"GCS_CREDENTIALS_JSON": "   "}
        with mock.patch.dict(os.environ, env, clear=False):
            with mock.patch("google.auth.default") as mock_adc:
                mock_adc.return_value = (mock.sentinel.creds, "project")
                GCSService()  # triggers __init__ → _resolve_credentials
                mock_adc.assert_called_once_with(scopes=GCS_SCOPES)


@pytest.mark.django_db
class TestResolveCredentialsFile:
    """Priority 2: GS_CREDENTIALS_PATH file on disk."""

    def test_existing_file_path(self, _disable_gcs_init, tmp_path):
        """Existing credentials file is loaded with scopes."""
        cred_file = tmp_path / "sa.json"
        cred_file.write_text(json.dumps(FAKE_SA_INFO))

        _disable_gcs_init.GS_CREDENTIALS_PATH = str(cred_file)
        env = {"GCS_CREDENTIALS_JSON": ""}  # Ensure env var path is skipped
        with mock.patch.dict(os.environ, env, clear=False):
            with mock.patch.object(
                service_account.Credentials,
                "from_service_account_file",
                return_value=mock.sentinel.creds,
            ) as mock_from_file:
                GCSService()  # triggers __init__ → _resolve_credentials
                mock_from_file.assert_called_once_with(
                    str(cred_file), scopes=GCS_SCOPES
                )

    def test_nonexistent_file_falls_through(self, _disable_gcs_init):
        """Missing credentials file falls through to ADC."""
        _disable_gcs_init.GS_CREDENTIALS_PATH = "/nonexistent/path.json"
        env = {"GCS_CREDENTIALS_JSON": ""}
        with mock.patch.dict(os.environ, env, clear=False):
            with mock.patch("google.auth.default") as mock_adc:
                mock_adc.return_value = (mock.sentinel.creds, "project")
                GCSService()  # triggers __init__ → _resolve_credentials
                mock_adc.assert_called_once_with(scopes=GCS_SCOPES)


@pytest.mark.django_db
class TestResolveCredentialsADC:
    """Priority 3: Application Default Credentials."""

    def test_adc_called_with_scopes(self, _disable_gcs_init):
        """When no env var or file, ADC is used with explicit GCS scopes."""
        _disable_gcs_init.GS_CREDENTIALS_PATH = ""
        env = {"GCS_CREDENTIALS_JSON": ""}
        with mock.patch.dict(os.environ, env, clear=False):
            with mock.patch("google.auth.default") as mock_adc:
                mock_adc.return_value = (mock.sentinel.creds, "project")
                GCSService()  # triggers __init__ → _resolve_credentials
                mock_adc.assert_called_once_with(scopes=GCS_SCOPES)
