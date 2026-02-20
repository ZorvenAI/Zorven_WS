"""Tests for Pydantic v2 request/response schemas and Kafka event schemas."""

import pytest
from pydantic import ValidationError

from app.api.schemas import (
    ExecuteRequest,
    ExecuteResponse,
    HealthResponse,
    SourceItem,
    TenantContext,
)
from app.messaging.schemas import AuditEvent, TraceEvent


class TestExecuteRequest:
    """ExecuteRequest schema validation."""

    def test_accepts_valid_external_wrapper_payload(self) -> None:
        req = ExecuteRequest(
            input_prompt="Analyze brand positioning for Acme Corp",
            input_context={"company_id": 42},
            tenant_context={
                "tenant_id": "1",
                "gcs_raw_bucket": "brand-automator/1/",
                "gcs_processed_bucket": "brand-automator-curated/1/",
                "rag_data_store_id": "ds-123",
            },
            config={"focus": "market_trends,competitors"},
            previous_outputs={},
        )
        assert req.input_prompt == "Analyze brand positioning for Acme Corp"
        assert req.config["focus"] == "market_trends,competitors"

    def test_accepts_payload_with_optional_fields_omitted(self) -> None:
        req = ExecuteRequest(input_prompt="Search for competitors")
        assert req.input_context == {}
        assert req.config == {}
        assert req.previous_outputs == {}

    def test_rejects_missing_input_prompt(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            ExecuteRequest()
        assert "input_prompt" in str(exc_info.value)

    def test_accepts_tenant_context_as_dict(self) -> None:
        req = ExecuteRequest(
            input_prompt="test",
            tenant_context={"tenant_id": "t1", "gcs_raw_bucket": "bucket/"},
        )
        # Pydantic coerces dict to TenantContext when fields match
        assert req.tenant_context.tenant_id == "t1"

    def test_accepts_tenant_context_as_model(self) -> None:
        ctx = TenantContext(tenant_id="t1", gcs_raw_bucket="bucket/")
        req = ExecuteRequest(input_prompt="test", tenant_context=ctx)
        assert isinstance(req.tenant_context, TenantContext)
        assert req.tenant_context.tenant_id == "t1"

    def test_accepts_all_seed_manifest_focus_configs(self) -> None:
        focuses = [
            "royalty_rates,market_trends,brand_rankings",
            "market_trends,competitors",
            "competitors,market_share",
        ]
        for focus in focuses:
            req = ExecuteRequest(
                input_prompt="Analyze brand",
                config={"focus": focus},
            )
            assert req.config["focus"] == focus


class TestTenantContext:
    """TenantContext schema validation."""

    def test_parses_all_fields(self) -> None:
        ctx = TenantContext(
            tenant_id="1",
            gcs_raw_bucket="brand-automator/1/",
            gcs_processed_bucket="brand-automator-curated/1/",
            rag_data_store_id="ds-123",
        )
        assert ctx.tenant_id == "1"
        assert ctx.gcs_raw_bucket == "brand-automator/1/"
        assert ctx.gcs_processed_bucket == "brand-automator-curated/1/"
        assert ctx.rag_data_store_id == "ds-123"

    def test_defaults_to_empty_strings(self) -> None:
        ctx = TenantContext()
        assert ctx.tenant_id == ""
        assert ctx.gcs_raw_bucket == ""
        assert ctx.gcs_processed_bucket == ""
        assert ctx.rag_data_store_id == ""


class TestSourceItem:
    """SourceItem schema validation."""

    def test_web_source(self) -> None:
        item = SourceItem(type="web", title="Article", url="https://example.com")
        assert item.type == "web"
        assert item.title == "Article"
        assert item.url == "https://example.com"

    def test_document_source(self) -> None:
        item = SourceItem(
            type="document",
            title="Report.pdf",
            url="gs://bucket/_landing/report.pdf",
        )
        assert item.type == "document"

    def test_financial_source(self) -> None:
        item = SourceItem(type="financial", title="10-K Filing", url="https://sec.gov/...")
        assert item.type == "financial"

    def test_defaults(self) -> None:
        item = SourceItem()
        assert item.type == "web"
        assert item.title == ""
        assert item.url == ""


class TestExecuteResponse:
    """ExecuteResponse schema validation."""

    def test_serializes_with_all_fields(self) -> None:
        resp = ExecuteResponse(
            query="brand positioning Acme Corp",
            sources=[
                SourceItem(type="web", title="Article", url="https://example.com"),
                SourceItem(type="document", title="Report", url="gs://bucket/r.pdf"),
            ],
            findings=["Market trend: growing", "Competitor: weak"],
            recommendations=["Focus on differentiation"],
            raw_context="Full text from all pages...",
        )
        data = resp.model_dump()
        assert data["query"] == "brand positioning Acme Corp"
        assert len(data["sources"]) == 2
        assert len(data["findings"]) == 2
        assert len(data["recommendations"]) == 1
        assert data["raw_context"] == "Full text from all pages..."

    def test_serializes_with_empty_lists(self) -> None:
        resp = ExecuteResponse(query="test query")
        data = resp.model_dump()
        assert data["sources"] == []
        assert data["findings"] == []
        assert data["recommendations"] == []
        assert data["raw_context"] == ""

    def test_default_values(self) -> None:
        resp = ExecuteResponse()
        assert resp.query == ""
        assert resp.sources == []
        assert resp.findings == []
        assert resp.recommendations == []
        assert resp.raw_context == ""

    def test_json_serializable(self) -> None:
        resp = ExecuteResponse(
            query="test",
            sources=[SourceItem(type="web", title="T", url="https://x.com")],
            findings=["finding 1"],
            recommendations=["rec 1"],
        )
        json_str = resp.model_dump_json()
        assert "test" in json_str
        assert "finding 1" in json_str


class TestHealthResponse:
    """HealthResponse schema validation."""

    def test_default_values(self) -> None:
        resp = HealthResponse()
        assert resp.status == "ok"
        assert resp.version == "0.1.0"

    def test_custom_values(self) -> None:
        resp = HealthResponse(status="degraded", version="1.2.3")
        assert resp.status == "degraded"
        assert resp.version == "1.2.3"


class TestTraceEvent:
    """TraceEvent Kafka schema validation."""

    def test_includes_all_required_fields(self) -> None:
        event = TraceEvent(job_id="job-1", message="Searching...")
        assert event.job_id == "job-1"
        assert event.message == "Searching..."
        assert event.node_id == "discovery_worker"
        assert event.status == "PROCESSING"
        assert event.timestamp  # auto-generated

    def test_timestamp_is_iso_format(self) -> None:
        event = TraceEvent(job_id="job-1", message="test")
        # ISO 8601 format contains 'T' separator and '+' or 'Z' for timezone
        assert "T" in event.timestamp

    def test_custom_node_id_and_status(self) -> None:
        event = TraceEvent(
            job_id="job-1",
            message="Done",
            node_id="custom_node",
            status="COMPLETE",
        )
        assert event.node_id == "custom_node"
        assert event.status == "COMPLETE"

    def test_metadata_defaults_to_empty_dict(self) -> None:
        event = TraceEvent(job_id="job-1", message="test")
        assert event.metadata == {}

    def test_metadata_preserved(self) -> None:
        event = TraceEvent(
            job_id="job-1",
            message="Scraping",
            metadata={"url": "https://example.com", "attempt": 1},
        )
        assert event.metadata["url"] == "https://example.com"
        assert event.metadata["attempt"] == 1

    def test_rejects_missing_job_id(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            TraceEvent(message="test")
        assert "job_id" in str(exc_info.value)

    def test_rejects_missing_message(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            TraceEvent(job_id="job-1")
        assert "message" in str(exc_info.value)

    def test_model_dump_has_all_keys(self) -> None:
        event = TraceEvent(job_id="j1", message="m1")
        data = event.model_dump()
        assert set(data.keys()) == {
            "job_id", "node_id", "status", "message", "metadata", "timestamp"
        }


class TestAuditEvent:
    """AuditEvent Kafka schema validation."""

    def test_includes_all_required_fields(self) -> None:
        event = AuditEvent(
            job_id="job-1",
            tenant_id="t-1",
            url="https://example.com",
            raw_html="<h1>Raw</h1>",
            cleaned_markdown="# Raw",
        )
        assert event.job_id == "job-1"
        assert event.tenant_id == "t-1"
        assert event.url == "https://example.com"
        assert event.raw_html == "<h1>Raw</h1>"
        assert event.cleaned_markdown == "# Raw"
        assert event.timestamp

    def test_timestamp_auto_generated(self) -> None:
        event = AuditEvent(
            job_id="j1", tenant_id="t1", url="u", raw_html="h", cleaned_markdown="m"
        )
        assert "T" in event.timestamp

    def test_rejects_missing_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            AuditEvent(job_id="j1")

    def test_rejects_missing_url(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            AuditEvent(
                job_id="j1",
                tenant_id="t1",
                raw_html="h",
                cleaned_markdown="m",
            )
        assert "url" in str(exc_info.value)

    def test_model_dump_has_all_keys(self) -> None:
        event = AuditEvent(
            job_id="j1", tenant_id="t1", url="u", raw_html="h", cleaned_markdown="m"
        )
        data = event.model_dump()
        assert set(data.keys()) == {
            "job_id", "tenant_id", "url", "raw_html", "cleaned_markdown", "timestamp"
        }
