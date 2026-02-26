"""Tests for context_parser utilities."""

from app.logic.context_parser import extract_gcs_uris, infer_mime_type, parse_gcs_uri

import pytest


class TestExtractGcsUris:
    """Tests for recursive GCS URI extraction."""

    def test_extract_from_string(self):
        data = "File is at gs://bucket/path/file.pdf"
        result = extract_gcs_uris(data)
        assert result == ["gs://bucket/path/file.pdf"]

    def test_extract_from_nested_dict(self):
        data = {
            "level1": {
                "level2": {
                    "uri": "gs://bucket/deep/file.pdf",
                }
            },
            "other": "gs://bucket/top/file.txt",
        }
        result = extract_gcs_uris(data)
        assert len(result) == 2
        assert "gs://bucket/deep/file.pdf" in result
        assert "gs://bucket/top/file.txt" in result

    def test_extract_from_list(self):
        data = ["gs://bucket/a.pdf", 42, "gs://bucket/b.pdf", None]
        result = extract_gcs_uris(data)
        assert result == ["gs://bucket/a.pdf", "gs://bucket/b.pdf"]

    def test_deduplicates(self):
        data = {
            "a": "gs://bucket/file.pdf",
            "b": "gs://bucket/file.pdf",
        }
        result = extract_gcs_uris(data)
        assert result == ["gs://bucket/file.pdf"]

    def test_empty_data_returns_empty(self):
        assert extract_gcs_uris({}) == []
        assert extract_gcs_uris("no uris here") == []
        assert extract_gcs_uris(None) == []


class TestParseGcsUri:
    """Tests for GCS URI parsing."""

    def test_valid_uri(self):
        bucket, path = parse_gcs_uri("gs://my-bucket/path/to/file.pdf")
        assert bucket == "my-bucket"
        assert path == "path/to/file.pdf"

    def test_uri_with_no_path(self):
        bucket, path = parse_gcs_uri("gs://my-bucket")
        assert bucket == "my-bucket"
        assert path == ""

    def test_invalid_uri_raises(self):
        with pytest.raises(ValueError, match="Not a GCS URI"):
            parse_gcs_uri("https://not-gcs.com/file.pdf")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            parse_gcs_uri("")


class TestInferMimeType:
    """Tests for MIME type inference."""

    def test_known_extensions(self):
        assert infer_mime_type("report.pdf") == "application/pdf"
        assert infer_mime_type("image.png") == "image/png"
        assert infer_mime_type("doc.md") == "text/markdown"
        assert infer_mime_type("data.csv") == "text/csv"
        assert infer_mime_type("video.mp4") == "video/mp4"

    def test_unknown_extension(self):
        assert infer_mime_type("file.xyz") == "application/octet-stream"

    def test_no_extension(self):
        assert infer_mime_type("README") == "application/octet-stream"

    def test_case_insensitive(self):
        assert infer_mime_type("FILE.PDF") == "application/pdf"
        assert infer_mime_type("image.PNG") == "image/png"
