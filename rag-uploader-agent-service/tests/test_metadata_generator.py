"""Tests for metadata_generator."""

from app.logic.metadata_generator import generate


class TestGenerate:
    """Tests for metadata generation."""

    def test_includes_required_fields(self):
        meta = generate(
            file_name="report.pdf",
            custom_title="Q4_Financial_Report",
            source="attachment",
            job_id="job-123",
            tenant_id="tenant-1",
        )
        assert meta["original_name"] == "report.pdf"
        assert meta["custom_title"] == "Q4_Financial_Report"
        assert meta["source_agent"] == "rag-uploader-agent-service"
        assert meta["source_node"] == "attachment"
        assert meta["job_id"] == "job-123"
        assert meta["tenant_id"] == "tenant-1"
        assert "archived_at" in meta

    def test_source_agent_is_rag_uploader(self):
        meta = generate(
            file_name="f.pdf",
            custom_title="f",
            source="blog_author",
            job_id="",
            tenant_id="t",
        )
        assert meta["source_agent"] == "rag-uploader-agent-service"

    def test_additional_metadata_merged(self):
        meta = generate(
            file_name="f.pdf",
            custom_title="f",
            source="attachment",
            job_id="j",
            tenant_id="t",
            additional={"asset_id": 42, "extra_key": "value"},
        )
        assert meta["asset_id"] == 42
        assert meta["extra_key"] == "value"
        # Original fields still present
        assert meta["original_name"] == "f.pdf"
