"""Tests for UploaderExecutor."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from app.api.schemas import ExecuteRequest
from app.cache.redis_manager import RedisManager
from app.logic.file_resolver import FileResolver, ResolvedFile
from app.logic.ingestion_bridge import IngestionBridge
from app.logic.smart_titler import SmartTitler
from app.services.core_api_client import CoreApiClient
from app.services.gcs_client import GCSClient
from app.services.uploader_executor import UploaderExecutor


def _make_executor(
    resolved_files: list[ResolvedFile] | None = None,
    dedup_returns: bool = False,
    rate_limit_ok: bool = True,
    emit_returns: bool = True,
    smart_title_result: str | None = None,
    gcs_client: GCSClient | AsyncMock | None = None,
    core_api_client: CoreApiClient | AsyncMock | None = None,
) -> tuple[UploaderExecutor, dict[str, AsyncMock]]:
    """Build an executor with mocked dependencies."""
    file_resolver = MagicMock(spec=FileResolver)
    file_resolver.resolve.return_value = resolved_files or []

    smart_titler = AsyncMock(spec=SmartTitler)
    if smart_title_result:
        smart_titler.title.return_value = smart_title_result
    else:
        # Return original filename
        smart_titler.title.side_effect = lambda fn, **kw: fn

    ingestion_bridge = AsyncMock(spec=IngestionBridge)
    ingestion_bridge.emit.return_value = emit_returns

    redis_manager = AsyncMock(spec=RedisManager)
    redis_manager.check_rate_limit.return_value = rate_limit_ok
    redis_manager.check_dedup.return_value = dedup_returns
    redis_manager.mark_ingested.return_value = None
    redis_manager.close.return_value = None
    redis_manager.hash_uri = RedisManager.hash_uri

    trace_producer = AsyncMock()
    trace_producer.send_step.return_value = None
    trace_producer.stop.return_value = None

    executor = UploaderExecutor(
        file_resolver=file_resolver,
        smart_titler=smart_titler,
        ingestion_bridge=ingestion_bridge,
        redis_manager=redis_manager,
        trace_producer=trace_producer,
        gcs_client=gcs_client,
        core_api_client=core_api_client,
    )

    mocks = {
        "file_resolver": file_resolver,
        "smart_titler": smart_titler,
        "ingestion_bridge": ingestion_bridge,
        "redis_manager": redis_manager,
        "trace_producer": trace_producer,
    }
    return executor, mocks


def _sample_request() -> ExecuteRequest:
    return ExecuteRequest(
        input_prompt="Save to knowledge base",
        input_context={"job_id": "job-1", "attachments": []},
        tenant_context={"tenant_id": "tenant-1"},
    )


def _sample_files() -> list[ResolvedFile]:
    return [
        ResolvedFile(
            gcs_uri="gs://bucket/path/report.pdf",
            bucket="bucket",
            path="path/report.pdf",
            file_name="report.pdf",
            file_type="application/pdf",
            file_size_bytes=1024,
            source="attachment",
        ),
        ResolvedFile(
            gcs_uri="gs://bucket/path/blog.md",
            bucket="bucket",
            path="path/blog.md",
            file_name="blog.md",
            file_type="text/markdown",
            file_size_bytes=512,
            source="blog_author",
        ),
    ]


class TestUploaderExecutor:
    """Tests for the main upload workflow."""

    async def test_full_flow(self):
        executor, mocks = _make_executor(resolved_files=_sample_files())
        response = await executor.execute(_sample_request(), "tenant-1")

        assert response.ingestion_events_emitted == 2
        assert response.files_skipped_dedup == 0
        assert len(response.uploaded_files) == 2
        assert len(response.findings) == 2
        assert mocks["ingestion_bridge"].emit.call_count == 2
        assert mocks["redis_manager"].mark_ingested.call_count == 2

    async def test_dedup_skips_existing_file(self):
        executor, mocks = _make_executor(
            resolved_files=_sample_files(),
            dedup_returns=True,  # All files are "duplicates"
        )
        response = await executor.execute(_sample_request(), "tenant-1")

        assert response.ingestion_events_emitted == 0
        assert response.files_skipped_dedup == 2
        assert all(f.was_deduplicated for f in response.uploaded_files)
        # Bridge should not be called for duplicates
        mocks["ingestion_bridge"].emit.assert_not_called()

    async def test_no_files_found(self):
        executor, mocks = _make_executor(resolved_files=[])
        response = await executor.execute(_sample_request(), "tenant-1")

        assert response.ingestion_events_emitted == 0
        assert "No files found" in response.findings[0]
        assert len(response.recommendations) > 0

    async def test_rate_limit_exceeded(self):
        executor, mocks = _make_executor(rate_limit_ok=False)
        response = await executor.execute(_sample_request(), "tenant-1")

        assert "Rate limit exceeded" in response.findings[0]
        mocks["file_resolver"].resolve.assert_not_called()

    async def test_generic_filename_renamed(self):
        files = [
            ResolvedFile(
                gcs_uri="gs://bucket/upload.pdf",
                bucket="bucket",
                path="upload.pdf",
                file_name="upload.pdf",
                file_type="application/pdf",
                file_size_bytes=0,
                source="attachment",
            ),
        ]
        executor, mocks = _make_executor(
            resolved_files=files,
            smart_title_result="Tesla_Q4_Report.pdf",
        )
        response = await executor.execute(_sample_request(), "tenant-1")

        assert response.uploaded_files[0].custom_title == "Tesla_Q4_Report.pdf"
        assert response.uploaded_files[0].was_renamed is True

    async def test_trace_events_emitted(self):
        executor, mocks = _make_executor(resolved_files=_sample_files())
        await executor.execute(_sample_request(), "tenant-1")

        # At minimum: resolve, per-file steps, completion
        assert mocks["trace_producer"].send_step.call_count >= 3

    async def test_close_cleans_up(self):
        executor, mocks = _make_executor()
        await executor.close()

        mocks["redis_manager"].close.assert_called_once()
        mocks["trace_producer"].stop.assert_called_once()


class TestContentUpload:
    """Tests for content upload flow (stub URI -> GCS upload -> ingest)."""

    async def test_content_upload_with_gcs_client(self):
        """Files needing upload get uploaded to GCS before ingestion."""
        files = [
            ResolvedFile(
                gcs_uri="",
                bucket="",
                path="",
                file_name="my-blog.md",
                file_type="text/markdown",
                file_size_bytes=100,
                source="blog_author",
                raw_content="# My Blog\n\nContent here...",
                needs_upload=True,
            ),
        ]
        mock_gcs = AsyncMock(spec=GCSClient)
        mock_gcs.is_available = True
        mock_gcs.upload_content.return_value = "gs://bucket/_landing/t1/my-blog.md"
        mock_gcs.close.return_value = None

        executor, mocks = _make_executor(resolved_files=files, gcs_client=mock_gcs)
        response = await executor.execute(_sample_request(), "tenant-1")

        mock_gcs.upload_content.assert_called_once()
        assert response.ingestion_events_emitted == 1
        assert len(response.uploaded_files) == 1
        assert (
            response.uploaded_files[0].file_path == "gs://bucket/_landing/t1/my-blog.md"
        )

    async def test_content_upload_no_gcs_client_reports_error(self):
        """Without GCS client, content files are skipped with clear feedback."""
        files = [
            ResolvedFile(
                gcs_uri="",
                bucket="",
                path="",
                file_name="my-blog.md",
                file_type="text/markdown",
                file_size_bytes=100,
                source="blog_author",
                raw_content="# My Blog",
                needs_upload=True,
            ),
        ]
        executor, mocks = _make_executor(resolved_files=files, gcs_client=None)
        response = await executor.execute(_sample_request(), "tenant-1")

        assert response.ingestion_events_emitted == 0
        assert any("GCS storage is not configured" in f for f in response.findings)
        assert any("GCS_PROJECT_ID" in r for r in response.recommendations)

    async def test_content_upload_gcs_unavailable(self):
        """When GCS client exists but is in stub mode, files are skipped."""
        files = [
            ResolvedFile(
                gcs_uri="",
                bucket="",
                path="",
                file_name="my-blog.md",
                file_type="text/markdown",
                file_size_bytes=100,
                source="blog_author",
                raw_content="# My Blog",
                needs_upload=True,
            ),
        ]
        mock_gcs = MagicMock(spec=GCSClient)
        mock_gcs.is_available = False
        mock_gcs.close = AsyncMock()

        executor, mocks = _make_executor(resolved_files=files, gcs_client=mock_gcs)
        response = await executor.execute(_sample_request(), "tenant-1")

        assert response.ingestion_events_emitted == 0
        assert any("GCS storage is not configured" in f for f in response.findings)

    async def test_mixed_gcs_and_content_files(self):
        """Mix of real GCS files and content-needing-upload files."""
        mock_gcs = AsyncMock(spec=GCSClient)
        mock_gcs.is_available = True
        mock_gcs.upload_content.return_value = "gs://bucket/_landing/t1/blog.md"
        mock_gcs.close.return_value = None

        files = [
            ResolvedFile(
                gcs_uri="gs://bucket/path/report.pdf",
                bucket="bucket",
                path="path/report.pdf",
                file_name="report.pdf",
                file_type="application/pdf",
                file_size_bytes=1024,
                source="attachment",
            ),
            ResolvedFile(
                gcs_uri="",
                bucket="",
                path="",
                file_name="blog.md",
                file_type="text/markdown",
                file_size_bytes=50,
                source="blog_author",
                raw_content="# Blog",
                needs_upload=True,
            ),
        ]
        executor, mocks = _make_executor(resolved_files=files, gcs_client=mock_gcs)
        response = await executor.execute(_sample_request(), "tenant-1")

        assert response.ingestion_events_emitted == 2
        assert len(response.uploaded_files) == 2

    async def test_close_with_gcs_client(self):
        mock_gcs = AsyncMock(spec=GCSClient)
        mock_gcs.close.return_value = None
        executor, mocks = _make_executor(gcs_client=mock_gcs)
        await executor.close()

        mock_gcs.close.assert_called_once()
        mocks["redis_manager"].close.assert_called_once()


class TestBrandAssetRegistration:
    """Tests for BrandAsset registration via CoreApiClient."""

    async def test_asset_registered_before_ingestion(self):
        """CoreApiClient is called for each file before emitting IngestionEvent."""
        mock_core = AsyncMock(spec=CoreApiClient)
        mock_core.register_asset.return_value = {
            "asset_id": 42,
            "company_id": 7,
            "file_name": "report.pdf",
            "pipeline_status": "pending",
        }
        mock_core.close.return_value = None

        executor, mocks = _make_executor(
            resolved_files=_sample_files(),
            core_api_client=mock_core,
        )
        response = await executor.execute(_sample_request(), "tenant-1")

        # CoreApiClient called once per file
        assert mock_core.register_asset.call_count == 2
        # IngestionBridge still called
        assert mocks["ingestion_bridge"].emit.call_count == 2
        assert response.ingestion_events_emitted == 2

    async def test_asset_id_included_in_metadata(self):
        """asset_id and company_id are included in the IngestionEvent metadata."""
        mock_core = AsyncMock(spec=CoreApiClient)
        mock_core.register_asset.return_value = {
            "asset_id": 99,
            "company_id": 5,
        }
        mock_core.close.return_value = None

        files = [
            ResolvedFile(
                gcs_uri="gs://bucket/path/report.pdf",
                bucket="bucket",
                path="path/report.pdf",
                file_name="report.pdf",
                file_type="application/pdf",
                file_size_bytes=1024,
                source="attachment",
            ),
        ]
        executor, mocks = _make_executor(
            resolved_files=files,
            core_api_client=mock_core,
        )
        await executor.execute(_sample_request(), "tenant-1")

        # Verify metadata passed to ingestion bridge contains asset_id
        call_args = mocks["ingestion_bridge"].emit.call_args
        metadata = call_args.kwargs.get("metadata") or call_args[1].get("metadata")
        assert metadata["asset_id"] == 99
        assert metadata["company_id"] == 5

    async def test_registration_failure_is_non_fatal(self):
        """If asset registration fails, ingestion still proceeds."""
        mock_core = AsyncMock(spec=CoreApiClient)
        mock_core.register_asset.return_value = None  # Failed
        mock_core.close.return_value = None

        executor, mocks = _make_executor(
            resolved_files=_sample_files(),
            core_api_client=mock_core,
        )
        response = await executor.execute(_sample_request(), "tenant-1")

        # Ingestion still happens even without asset registration
        assert response.ingestion_events_emitted == 2
        assert mocks["ingestion_bridge"].emit.call_count == 2

    async def test_no_core_api_client_skips_registration(self):
        """Without CoreApiClient, flow works but no asset_id in metadata."""
        executor, mocks = _make_executor(
            resolved_files=_sample_files(),
            core_api_client=None,
        )
        response = await executor.execute(_sample_request(), "tenant-1")

        assert response.ingestion_events_emitted == 2

    async def test_close_with_core_api_client(self):
        """close() also closes the CoreApiClient."""
        mock_core = AsyncMock(spec=CoreApiClient)
        mock_core.close.return_value = None
        executor, mocks = _make_executor(core_api_client=mock_core)
        await executor.close()

        mock_core.close.assert_called_once()
        mocks["redis_manager"].close.assert_called_once()
