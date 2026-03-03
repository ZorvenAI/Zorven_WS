"""Central orchestrator for the RAG uploader agent.

Coordinates file resolution, smart titling, deduplication,
GCS content upload (when needed), and ingestion event emission.
"""

import logging
from typing import Optional

from app.api.schemas import (
    ExecuteRequest,
    ExecuteResponse,
    UploadedFileInfo,
)
from app.cache.redis_manager import RedisManager
from app.core.config import settings
from app.logic.context_parser import parse_gcs_uri
from app.logic.file_resolver import FileResolver, ResolvedFile
from app.logic.ingestion_bridge import IngestionBridge
from app.logic.metadata_generator import generate as generate_metadata
from app.logic.smart_titler import SmartTitler
from app.messaging.kafka_producer import TraceProducer
from app.services.core_api_client import CoreApiClient
from app.services.gcs_client import GCSClient
from app.utils.prompt_sanitizer import sanitize_ai_prompt

logger = logging.getLogger(__name__)


class UploaderExecutor:
    """Executes the RAG upload workflow."""

    def __init__(
        self,
        file_resolver: FileResolver,
        smart_titler: SmartTitler,
        ingestion_bridge: IngestionBridge,
        redis_manager: RedisManager,
        trace_producer: TraceProducer,
        gcs_client: Optional[GCSClient] = None,
        core_api_client: Optional[CoreApiClient] = None,
    ) -> None:
        self._file_resolver = file_resolver
        self._smart_titler = smart_titler
        self._ingestion_bridge = ingestion_bridge
        self._redis = redis_manager
        self._trace = trace_producer
        self._gcs = gcs_client
        self._core_api = core_api_client

    async def execute(self, request: ExecuteRequest, tenant_id: str) -> ExecuteResponse:
        """Execute the RAG upload workflow.

        1. Rate-limit check
        2. Resolve files from pipeline context
        3. For files needing upload: upload content to GCS first
        4. For each file: dedup check -> smart title -> emit IngestionEvent
        5. Return results
        """
        job_id = request.input_context.get("job_id", "")

        # Sanitize user input to mitigate prompt injection
        request.input_prompt = sanitize_ai_prompt(request.input_prompt)

        logger.info(
            "Execute called — tenant=%s, input_context keys=%s, "
            "previous_outputs keys=%s",
            tenant_id,
            list(request.input_context.keys()),
            list(request.previous_outputs.keys()),
        )

        # Rate limit
        within_limit = await self._redis.check_rate_limit(
            tenant_id, settings.RATE_LIMIT_PER_MINUTE
        )
        if not within_limit:
            return ExecuteResponse(
                findings=["Rate limit exceeded. Please try again later."],
            )

        # Extract skill context from orchestrator config (if present)
        skill_context = request.config.get("skill_context", "")

        # Resolve tenant context
        tc = request.tenant_context
        if isinstance(tc, dict):
            tenant_id = tc.get("tenant_id", tenant_id) or tenant_id

        # Resolve files
        await self._emit_trace(job_id, "Resolving files from session context...")
        files = self._file_resolver.resolve(
            request.input_context,
            request.previous_outputs,
            tc if isinstance(tc, dict) else tc.model_dump(),
        )

        if not files:
            await self._emit_trace(
                job_id,
                "No files found to archive.",
                status="COMPLETED",
            )
            return ExecuteResponse(
                findings=["No files found in the pipeline context to archive."],
                recommendations=[
                    "Attach files to your message or run a content pipeline "
                    "first to generate documents for archival."
                ],
            )

        # Upload content to GCS for files that need it
        await self._upload_pending_content(files, tenant_id, job_id)

        # Separate files into uploadable (have real GCS URI) and skipped
        uploadable: list[ResolvedFile] = []
        skipped_no_gcs: list[ResolvedFile] = []
        for f in files:
            if f.gcs_uri and f.gcs_uri.startswith("gs://"):
                uploadable.append(f)
            else:
                skipped_no_gcs.append(f)
                logger.warning(
                    "Skipping file '%s' — no valid GCS URI available",
                    f.file_name,
                )

        await self._emit_trace(
            job_id,
            f"Found {len(uploadable)} file(s) to archive. Processing...",
        )

        uploaded: list[UploadedFileInfo] = []
        skipped_dedup = 0
        emitted = 0

        for resolved in uploadable:
            file_hash = RedisManager.hash_uri(resolved.gcs_uri)

            # Dedup check
            is_duplicate = await self._redis.check_dedup(tenant_id, file_hash)
            if is_duplicate:
                logger.info(
                    "Skipping duplicate: %s (tenant=%s)",
                    resolved.gcs_uri,
                    tenant_id,
                )
                uploaded.append(
                    UploadedFileInfo(
                        file_path=resolved.gcs_uri,
                        file_name=resolved.file_name,
                        file_type=resolved.file_type,
                        was_deduplicated=True,
                    )
                )
                skipped_dedup += 1
                continue

            # Smart title
            await self._emit_trace(
                job_id,
                f"Analyzing '{resolved.file_name}' to generate a descriptive title...",
            )
            custom_title = await self._smart_titler.title(
                resolved.file_name, skill_context=skill_context
            )
            was_renamed = custom_title != resolved.file_name

            if was_renamed:
                await self._emit_trace(
                    job_id,
                    f"Renamed '{resolved.file_name}' -> '{custom_title}'",
                )

            # Register BrandAsset in Django backend (so file appears in UI)
            asset_info = await self._register_asset(
                tenant_id=tenant_id,
                file_name=custom_title,
                file_type=resolved.file_type,
                file_size=resolved.file_size_bytes,
                gcs_uri=resolved.gcs_uri,
            )

            # Generate metadata (include asset_id if registration succeeded)
            additional_meta = {}
            if asset_info:
                additional_meta["asset_id"] = asset_info.get("asset_id")
                additional_meta["company_id"] = asset_info.get("company_id")

            metadata = generate_metadata(
                file_name=resolved.file_name,
                custom_title=custom_title,
                source=resolved.source,
                job_id=job_id,
                tenant_id=tenant_id,
                additional=additional_meta if additional_meta else None,
            )

            # Emit ingestion event
            await self._emit_trace(
                job_id,
                f"Submitting '{custom_title}' to the permanent data pipeline...",
            )
            success = await self._ingestion_bridge.emit(
                file_path=resolved.gcs_uri,
                file_type=resolved.file_type,
                file_size_bytes=resolved.file_size_bytes,
                tenant_id=tenant_id,
                metadata=metadata,
            )

            if success:
                # Mark as ingested for dedup
                await self._redis.mark_ingested(tenant_id, file_hash)
                emitted += 1

            uploaded.append(
                UploadedFileInfo(
                    file_path=resolved.gcs_uri,
                    file_name=resolved.file_name,
                    file_type=resolved.file_type,
                    custom_title=custom_title,
                    was_renamed=was_renamed,
                    was_deduplicated=False,
                )
            )

        # Final trace
        await self._emit_trace(
            job_id,
            f"Archival complete. {emitted} file(s) submitted for permanent "
            f"RAG indexing. {skipped_dedup} duplicate(s) skipped.",
            status="COMPLETED",
        )

        # Build findings
        findings: list[str] = []
        for info in uploaded:
            if info.was_deduplicated:
                findings.append(
                    f"Skipped '{info.file_name}' — already in knowledge base."
                )
            else:
                label = info.custom_title or info.file_name
                findings.append(f"Submitted '{label}' to the data ingestion pipeline.")

        # Report files that couldn't be archived due to missing GCS
        for f in skipped_no_gcs:
            findings.append(
                f"Could not archive '{f.file_name}' — GCS storage is not "
                f"configured. Configure GCS_PROJECT_ID and GCS_BUCKET_NAME "
                f"to enable content archival."
            )

        recommendations: list[str] = []
        if emitted > 0:
            recommendations.append(
                "Documents will be searchable in your knowledge base "
                "after the ingestion pipeline completes processing."
            )
        if skipped_no_gcs:
            recommendations.append(
                "Set UPLOADER_GCS_PROJECT_ID and UPLOADER_GCS_BUCKET_NAME "
                "environment variables to enable direct content archival."
            )

        return ExecuteResponse(
            findings=findings,
            recommendations=recommendations,
            uploaded_files=uploaded,
            files_skipped_dedup=skipped_dedup,
            ingestion_events_emitted=emitted,
        )

    async def _upload_pending_content(
        self,
        files: list[ResolvedFile],
        tenant_id: str,
        job_id: str,
    ) -> None:
        """Upload raw content to GCS for files that need it.

        Mutates files in-place: sets gcs_uri, bucket, path after upload.
        """
        for f in files:
            if not f.needs_upload or not f.raw_content:
                continue

            if not self._gcs or not self._gcs.is_available:
                logger.warning(
                    "File '%s' needs GCS upload but GCS client is not configured",
                    f.file_name,
                )
                continue

            await self._emit_trace(
                job_id,
                f"Uploading '{f.file_name}' to cloud storage...",
            )
            gcs_uri = await self._gcs.upload_content(
                tenant_id=tenant_id,
                filename=f.file_name,
                content=f.raw_content,
                content_type=f.file_type,
            )

            if gcs_uri:
                f.gcs_uri = gcs_uri
                try:
                    f.bucket, f.path = parse_gcs_uri(gcs_uri)
                except ValueError:
                    pass
                f.needs_upload = False
                logger.info("Uploaded '%s' to %s", f.file_name, gcs_uri)
            else:
                logger.warning("Failed to upload '%s' to GCS", f.file_name)

    async def _register_asset(
        self,
        tenant_id: str,
        file_name: str,
        file_type: str,
        file_size: int,
        gcs_uri: str,
    ) -> Optional[dict]:
        """Register a BrandAsset in the Django backend.

        Returns asset info dict on success, None on failure.
        Failure is non-fatal — the file will still be ingested but won't
        appear in the file uploader UI until manually re-synced.
        """
        if not self._core_api:
            logger.info("CoreApiClient not configured — skipping asset registration")
            return None

        return await self._core_api.register_asset(
            tenant_id=tenant_id,
            file_name=file_name,
            file_type=file_type,
            file_size=file_size,
            gcs_uri=gcs_uri,
        )

    async def _emit_trace(
        self, job_id: str, message: str, status: str = "PROCESSING"
    ) -> None:
        """Emit a trace event for ThoughtTrace UI."""
        await self._trace.send_step(job_id=job_id, message=message, status=status)

    async def close(self) -> None:
        """Release resources."""
        await self._redis.close()
        await self._trace.stop()
        if self._gcs:
            await self._gcs.close()
        if self._core_api:
            await self._core_api.close()
