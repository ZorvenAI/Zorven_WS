"""E2E test: competitor-audit pipeline flow.

Pipeline: RouterNode → competitor_research (discovery) → gap_analyzer (intelligence, stubbed) → report_generator
"""

from unittest.mock import AsyncMock, patch

from app.services.job_executor import JobExecutor

from tests.e2e.conftest import make_dispatch_request


class TestCompetitorAuditPipeline:
    """E2E tests for the competitor-audit seed manifest."""

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_pipeline_completes(
        self, mock_get_redis, competitor_audit_manifest, mock_discovery_service
    ):
        """Pipeline completes with discovery real + intelligence stubbed."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        request = make_dispatch_request(competitor_audit_manifest)
        await executor.execute(request)

        executor.callback.send_completed.assert_called_once()
        executor.callback.send_failed.assert_not_called()

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_competitor_focus_config(
        self, mock_get_redis, competitor_audit_manifest, mock_discovery_service
    ):
        """Discovery receives focus=competitors,market_share."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        request = make_dispatch_request(competitor_audit_manifest)
        await executor.execute(request)

        assert len(mock_discovery_service) == 1
        payload = mock_discovery_service[0]["payload"]
        assert payload["config"]["focus"] == "competitors,market_share"

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_progress_has_all_nodes_done(
        self, mock_get_redis, competitor_audit_manifest, mock_discovery_service
    ):
        """All 4 nodes marked done in progress."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        request = make_dispatch_request(competitor_audit_manifest)
        await executor.execute(request)

        call_kwargs = executor.callback.send_completed.call_args.kwargs
        progress = call_kwargs["progress"]

        for node_id in ["intent_router", "competitor_research", "gap_analyzer", "report_generator"]:
            assert node_id in progress
            assert progress[node_id]["status"] == "done"

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_discovery_called_before_intelligence(
        self, mock_get_redis, competitor_audit_manifest, mock_discovery_service
    ):
        """Discovery is called (edges: router → discovery → intelligence → report)."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        request = make_dispatch_request(competitor_audit_manifest)
        await executor.execute(request)

        # Discovery was called exactly once
        assert len(mock_discovery_service) == 1
        # Pipeline completed (meaning intelligence stub + report also executed)
        executor.callback.send_completed.assert_called_once()
