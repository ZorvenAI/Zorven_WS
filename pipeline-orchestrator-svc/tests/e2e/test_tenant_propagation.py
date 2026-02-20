"""E2E test: multi-tenant context propagation through the pipeline.

Verifies that tenant_id and tenant_context are correctly propagated
from the dispatch request through to external service calls.
"""

from unittest.mock import AsyncMock, patch

from app.services.job_executor import JobExecutor

from tests.e2e.conftest import make_dispatch_request


class TestTenantPropagation:
    """Tenant context propagation through the full pipeline."""

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_tenant_id_in_discovery_header(
        self, mock_get_redis, brand_analysis_manifest, mock_discovery_service
    ):
        """X-Tenant-ID header sent to discovery matches dispatch request."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        request = make_dispatch_request(
            brand_analysis_manifest, tenant_id="tenant-42"
        )
        await executor.execute(request)

        assert len(mock_discovery_service) == 1
        headers = mock_discovery_service[0]["headers"]
        assert headers.get("x-tenant-id") == "tenant-42"

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_tenant_context_in_discovery_payload(
        self, mock_get_redis, brand_analysis_manifest, mock_discovery_service
    ):
        """Discovery receives tenant_context with GCS buckets and RAG store."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        request = make_dispatch_request(
            brand_analysis_manifest, tenant_id="tenant-99"
        )
        await executor.execute(request)

        payload = mock_discovery_service[0]["payload"]
        tenant_ctx = payload["tenant_context"]

        assert tenant_ctx["tenant_id"] == "tenant-99"
        assert "gcs_raw_bucket" in tenant_ctx
        assert "gcs_processed_bucket" in tenant_ctx
        assert "rag_data_store_id" in tenant_ctx

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_different_tenants_both_complete(
        self, mock_get_redis, brand_analysis_manifest, mock_discovery_service
    ):
        """Two dispatches with different tenant IDs both complete successfully."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        # Dispatch for tenant-A
        request_a = make_dispatch_request(
            brand_analysis_manifest,
            tenant_id="tenant-A",
            job_id="job-tenant-a",
        )
        await executor.execute(request_a)

        # Dispatch for tenant-B
        request_b = make_dispatch_request(
            brand_analysis_manifest,
            tenant_id="tenant-B",
            job_id="job-tenant-b",
        )
        await executor.execute(request_b)

        # Both should have completed (2 calls total)
        assert executor.callback.send_completed.call_count == 2

        # Both discovery calls have different tenant IDs
        assert len(mock_discovery_service) == 2
        assert mock_discovery_service[0]["headers"]["x-tenant-id"] == "tenant-A"
        assert mock_discovery_service[1]["headers"]["x-tenant-id"] == "tenant-B"

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_gcs_bucket_includes_tenant_id(
        self, mock_get_redis, brand_analysis_manifest, mock_discovery_service
    ):
        """GCS bucket paths include the tenant ID for isolation."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        request = make_dispatch_request(
            brand_analysis_manifest, tenant_id="tenant-77"
        )
        await executor.execute(request)

        payload = mock_discovery_service[0]["payload"]
        assert "tenant-77" in payload["tenant_context"]["gcs_raw_bucket"]
        assert "tenant-77" in payload["tenant_context"]["gcs_processed_bucket"]
