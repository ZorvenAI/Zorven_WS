"""Tests for FileResolver."""

from __future__ import annotations

from typing import Any

from app.logic.file_resolver import FileResolver


class TestFileResolver:
    """Tests for file resolution from pipeline context."""

    def _make_resolver(self) -> FileResolver:
        return FileResolver()

    def test_resolves_attachments(self, sample_attachments: list[dict[str, Any]]):
        resolver = self._make_resolver()
        files = resolver.resolve(
            input_context={"attachments": sample_attachments},
            previous_outputs={},
            tenant_context={"tenant_id": "test"},
        )
        assert len(files) == 2
        assert files[0].source == "attachment"
        assert files[0].file_name == "report.pdf"
        assert files[0].gcs_uri == "gs://brand-automator/_landing/1/abc_report.pdf"
        assert files[1].file_name == "upload.pdf"

    def test_resolves_blog_author_gcs_uri(
        self, sample_previous_outputs: dict[str, Any]
    ):
        resolver = self._make_resolver()
        files = resolver.resolve(
            input_context={},
            previous_outputs=sample_previous_outputs,
            tenant_context={"tenant_id": "test"},
        )
        assert len(files) == 1
        assert files[0].source == "blog_author"
        assert files[0].file_name == "my-blog.md"
        assert files[0].file_type == "text/markdown"

    def test_deduplicates_by_uri(self):
        resolver = self._make_resolver()
        # Same URI appears in both attachments and previous_outputs
        files = resolver.resolve(
            input_context={
                "attachments": [
                    {
                        "gcs_bucket": "bucket",
                        "gcs_path": "path/file.pdf",
                        "file_name": "file.pdf",
                    }
                ]
            },
            previous_outputs={
                "some_node": {
                    "uri": "gs://bucket/path/file.pdf",
                }
            },
            tenant_context={},
        )
        assert len(files) == 1

    def test_empty_context_returns_empty(self):
        resolver = self._make_resolver()
        files = resolver.resolve(
            input_context={},
            previous_outputs={},
            tenant_context={},
        )
        assert len(files) == 0

    def test_attachment_missing_fields_skipped(self):
        resolver = self._make_resolver()
        files = resolver.resolve(
            input_context={
                "attachments": [
                    {"file_name": "no_bucket.pdf"},  # Missing gcs_bucket
                    {
                        "gcs_bucket": "b",
                        "gcs_path": "p/f.pdf",
                        "file_name": "f.pdf",
                    },
                ]
            },
            previous_outputs={},
            tenant_context={},
        )
        assert len(files) == 1
        assert files[0].file_name == "f.pdf"

    def test_combined_attachments_and_previous_outputs(
        self,
        sample_attachments: list[dict[str, Any]],
        sample_previous_outputs: dict[str, Any],
    ):
        resolver = self._make_resolver()
        files = resolver.resolve(
            input_context={"attachments": sample_attachments},
            previous_outputs=sample_previous_outputs,
            tenant_context={"tenant_id": "test"},
        )
        # 2 attachments + 1 blog GCS URI = 3
        assert len(files) == 3
        sources = {f.source for f in files}
        assert "attachment" in sources
        assert "blog_author" in sources


class TestContentPayloadExtraction:
    """Tests for extracting content payloads from upstream nodes."""

    def _make_resolver(self) -> FileResolver:
        return FileResolver()

    def test_extracts_blog_content_with_stub_uri(
        self, sample_stub_previous_outputs: dict[str, Any]
    ):
        resolver = self._make_resolver()
        files = resolver.resolve(
            input_context={},
            previous_outputs=sample_stub_previous_outputs,
            tenant_context={"tenant_id": "test"},
        )
        assert len(files) == 1
        assert files[0].source == "blog_author"
        assert files[0].needs_upload is True
        assert files[0].raw_content == "# My Blog Post\n\nContent here..."
        assert files[0].file_name == "my-blog-post.md"
        assert files[0].file_type == "text/markdown"

    def test_extracts_blog_content_with_empty_uri(self):
        resolver = self._make_resolver()
        files = resolver.resolve(
            input_context={},
            previous_outputs={
                "blog_author": {
                    "blog_content": "# Hello World",
                    "gcs_uri": "",
                    "seo_meta": {"slug": "hello-world"},
                }
            },
            tenant_context={},
        )
        assert len(files) == 1
        assert files[0].needs_upload is True
        assert files[0].file_name == "hello-world.md"

    def test_prefers_real_gcs_uri_over_content_payload(self):
        resolver = self._make_resolver()
        files = resolver.resolve(
            input_context={},
            previous_outputs={
                "blog_author": {
                    "blog_content": "# Real blog",
                    "gcs_uri": "gs://bucket/path/blog.md",
                }
            },
            tenant_context={},
        )
        assert len(files) == 1
        assert files[0].needs_upload is False
        assert files[0].gcs_uri == "gs://bucket/path/blog.md"

    def test_no_content_no_uri_returns_empty(self):
        resolver = self._make_resolver()
        files = resolver.resolve(
            input_context={},
            previous_outputs={
                "blog_author": {
                    "findings": ["Blog written"],
                    "gcs_uri": "stub://no-gcs/blog.md",
                    # No blog_content field
                }
            },
            tenant_context={},
        )
        assert len(files) == 0

    def test_content_payload_uses_default_filename_when_no_slug(self):
        resolver = self._make_resolver()
        files = resolver.resolve(
            input_context={},
            previous_outputs={
                "blog_author": {
                    "blog_content": "# Content",
                    "gcs_uri": "stub://no-gcs/blog.md",
                }
            },
            tenant_context={},
        )
        assert len(files) == 1
        assert files[0].file_name == "blog-content.md"

    def test_content_payload_calculates_size(self):
        resolver = self._make_resolver()
        content = "Hello World"
        files = resolver.resolve(
            input_context={},
            previous_outputs={
                "blog_author": {
                    "blog_content": content,
                    "gcs_uri": "",
                }
            },
            tenant_context={},
        )
        assert len(files) == 1
        assert files[0].file_size_bytes == len(content.encode("utf-8"))
