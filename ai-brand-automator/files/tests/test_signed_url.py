"""
Tests for GCSService.generate_signed_url() signed-URL generation logic.

Covers:
- Browser-viewable files (PDF, images) served inline when for_download=False
- Non-browser-viewable files (.docx, .xlsx, .pptx) force attachment even when
  for_download=False
- Explicit download requests always set attachment disposition
- response_type is set to the correct MIME type
"""

from unittest import mock

import pytest

from files.services import (
    GCSService,
    _BROWSER_VIEWABLE_TYPES,
    _EXTENSION_CONTENT_TYPE,
)


@pytest.fixture
def gcs_service():
    """GCSService with a mocked bucket and blob."""
    with (
        mock.patch("files.services.settings") as mock_settings,
        mock.patch("files.services.storage.Client"),
    ):
        mock_settings.GS_BUCKET_NAME = "test-bucket"
        mock_settings.GS_PROJECT_ID = "test-project"
        mock_settings.GS_CREDENTIALS_PATH = ""
        service = GCSService()
        # Replace bucket with a mock that returns a mock blob
        service.bucket = mock.MagicMock()
        yield service


class TestSignedUrlForceDownload:
    """Non-browser-viewable types must force Content-Disposition: attachment."""

    @pytest.mark.parametrize(
        "file_path,expected_content_type",
        [
            (
                "uploads/report.docx",
                "application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document",
            ),
            (
                "uploads/data.xlsx",
                "application/vnd.openxmlformats-officedocument" ".spreadsheetml.sheet",
            ),
            (
                "uploads/slides.pptx",
                "application/vnd.openxmlformats-officedocument"
                ".presentationml.presentation",
            ),
            ("uploads/legacy.doc", "application/msword"),
            ("uploads/legacy.xls", "application/vnd.ms-excel"),
            ("uploads/legacy.ppt", "application/vnd.ms-powerpoint"),
        ],
    )
    def test_view_url_forces_attachment_for_office_files(
        self, gcs_service, file_path, expected_content_type
    ):
        """A 'view' URL (for_download=False) for Office files should still
        pass response_disposition=attachment and set response_type."""
        mock_blob = gcs_service.bucket.blob.return_value
        mock_blob.generate_signed_url.return_value = "https://signed.url/test"

        result = gcs_service.generate_signed_url(file_path, for_download=False)

        assert "url" in result
        call_kwargs = mock_blob.generate_signed_url.call_args[1]
        # Must have attachment disposition even though for_download=False
        assert "response_disposition" in call_kwargs
        assert "attachment" in call_kwargs["response_disposition"]
        # Must set response_type to the correct MIME type
        assert call_kwargs["response_type"] == expected_content_type

    @pytest.mark.parametrize(
        "file_path,expected_content_type",
        [
            ("uploads/report.docx", _EXTENSION_CONTENT_TYPE[".docx"]),
            ("uploads/data.xlsx", _EXTENSION_CONTENT_TYPE[".xlsx"]),
        ],
    )
    def test_download_url_also_sets_attachment_for_office_files(
        self, gcs_service, file_path, expected_content_type
    ):
        """Explicit download (for_download=True) for Office files should
        also set attachment disposition and response_type."""
        mock_blob = gcs_service.bucket.blob.return_value
        mock_blob.generate_signed_url.return_value = "https://signed.url/test"

        result = gcs_service.generate_signed_url(file_path, for_download=True)

        assert "url" in result
        call_kwargs = mock_blob.generate_signed_url.call_args[1]
        assert "attachment" in call_kwargs["response_disposition"]
        assert call_kwargs["response_type"] == expected_content_type


class TestSignedUrlInlineViewable:
    """Browser-viewable types should NOT force attachment on view URLs."""

    @pytest.mark.parametrize(
        "file_path",
        [
            "uploads/doc.pdf",
            "uploads/photo.png",
            "uploads/photo.jpg",
            "uploads/animation.gif",
            "uploads/notes.txt",
            "uploads/video.mp4",
        ],
    )
    def test_view_url_no_attachment_for_viewable_files(self, gcs_service, file_path):
        """A 'view' URL for browser-viewable files should NOT set
        response_disposition (allows inline display)."""
        mock_blob = gcs_service.bucket.blob.return_value
        mock_blob.generate_signed_url.return_value = "https://signed.url/test"

        gcs_service.generate_signed_url(file_path, for_download=False)

        call_kwargs = mock_blob.generate_signed_url.call_args[1]
        assert "response_disposition" not in call_kwargs

    @pytest.mark.parametrize(
        "file_path",
        [
            "uploads/doc.pdf",
            "uploads/photo.png",
        ],
    )
    def test_download_url_sets_attachment_for_viewable_files(
        self, gcs_service, file_path
    ):
        """Explicit download (for_download=True) for viewable files should
        set response_disposition to attachment."""
        mock_blob = gcs_service.bucket.blob.return_value
        mock_blob.generate_signed_url.return_value = "https://signed.url/test"

        gcs_service.generate_signed_url(file_path, for_download=True)

        call_kwargs = mock_blob.generate_signed_url.call_args[1]
        assert "response_disposition" in call_kwargs
        assert "attachment" in call_kwargs["response_disposition"]


class TestSignedUrlResponseType:
    """response_type should always be set when extension is in the map."""

    def test_response_type_set_for_known_extensions(self, gcs_service):
        """Known file extensions should set response_type."""
        mock_blob = gcs_service.bucket.blob.return_value
        mock_blob.generate_signed_url.return_value = "https://signed.url/test"

        gcs_service.generate_signed_url("uploads/doc.pdf", for_download=False)

        call_kwargs = mock_blob.generate_signed_url.call_args[1]
        assert call_kwargs["response_type"] == "application/pdf"

    def test_response_type_not_set_for_unknown_extensions(self, gcs_service):
        """Unknown file extensions should NOT set response_type."""
        mock_blob = gcs_service.bucket.blob.return_value
        mock_blob.generate_signed_url.return_value = "https://signed.url/test"

        gcs_service.generate_signed_url("uploads/archive.xyz", for_download=False)

        call_kwargs = mock_blob.generate_signed_url.call_args[1]
        assert "response_type" not in call_kwargs

    def test_unknown_extension_no_forced_download(self, gcs_service):
        """Unknown extensions should NOT force download on view URLs."""
        mock_blob = gcs_service.bucket.blob.return_value
        mock_blob.generate_signed_url.return_value = "https://signed.url/test"

        gcs_service.generate_signed_url("uploads/archive.xyz", for_download=False)

        call_kwargs = mock_blob.generate_signed_url.call_args[1]
        assert "response_disposition" not in call_kwargs


class TestSignedUrlFilename:
    """The filename in Content-Disposition should be correct."""

    def test_custom_filename_in_disposition(self, gcs_service):
        """Custom filename should appear in Content-Disposition header."""
        mock_blob = gcs_service.bucket.blob.return_value
        mock_blob.generate_signed_url.return_value = "https://signed.url/test"

        gcs_service.generate_signed_url(
            "uploads/report.docx",
            for_download=False,
            filename="My Report.docx",
        )

        call_kwargs = mock_blob.generate_signed_url.call_args[1]
        assert "My Report.docx" in call_kwargs["response_disposition"]

    def test_basename_used_when_no_filename(self, gcs_service):
        """When no filename is provided, the file's basename should be used."""
        mock_blob = gcs_service.bucket.blob.return_value
        mock_blob.generate_signed_url.return_value = "https://signed.url/test"

        gcs_service.generate_signed_url("uploads/report.docx", for_download=True)

        call_kwargs = mock_blob.generate_signed_url.call_args[1]
        assert "report.docx" in call_kwargs["response_disposition"]


class TestModuleLevelConstants:
    """Verify that the module-level constants are properly defined."""

    def test_browser_viewable_types_contains_pdf(self):
        assert "application/pdf" in _BROWSER_VIEWABLE_TYPES

    def test_browser_viewable_types_excludes_office(self):
        docx_type = _EXTENSION_CONTENT_TYPE[".docx"]
        xlsx_type = _EXTENSION_CONTENT_TYPE[".xlsx"]
        pptx_type = _EXTENSION_CONTENT_TYPE[".pptx"]
        assert docx_type not in _BROWSER_VIEWABLE_TYPES
        assert xlsx_type not in _BROWSER_VIEWABLE_TYPES
        assert pptx_type not in _BROWSER_VIEWABLE_TYPES

    def test_extension_content_type_has_office_formats(self):
        assert ".docx" in _EXTENSION_CONTENT_TYPE
        assert ".xlsx" in _EXTENSION_CONTENT_TYPE
        assert ".pptx" in _EXTENSION_CONTENT_TYPE
        assert ".doc" in _EXTENSION_CONTENT_TYPE
        assert ".xls" in _EXTENSION_CONTENT_TYPE
        assert ".ppt" in _EXTENSION_CONTENT_TYPE
