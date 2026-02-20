"""E2E test: content-strategy pipeline flow (all internal nodes).

Pipeline: RouterNode → audience_analyzer → content_planner → calendar_builder

No external service calls — this validates that purely internal pipelines
execute correctly end-to-end.
"""

from unittest.mock import AsyncMock, patch

from app.services.job_executor import JobExecutor

from tests.e2e.conftest import make_dispatch_request


class TestContentStrategyPipeline:
    """E2E tests for the content-strategy seed manifest."""

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_all_internal_pipeline_completes(
        self, mock_get_redis, content_strategy_manifest
    ):
        """All-internal pipeline completes without any external calls."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        request = make_dispatch_request(
            content_strategy_manifest,
            input_prompt="Create a content strategy for our tech blog",
        )
        await executor.execute(request)

        executor.callback.send_completed.assert_called_once()
        executor.callback.send_failed.assert_not_called()

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_no_external_http_calls(
        self, mock_get_redis, content_strategy_manifest, httpx_mock
    ):
        """No HTTP requests made to external services."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        request = make_dispatch_request(
            content_strategy_manifest,
            input_prompt="Create a content strategy",
        )
        await executor.execute(request)

        # No HTTP requests were intercepted by httpx_mock
        assert len(httpx_mock.get_requests()) == 0

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_progress_has_all_nodes_done(
        self, mock_get_redis, content_strategy_manifest
    ):
        """All 4 internal nodes marked done in progress."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        request = make_dispatch_request(
            content_strategy_manifest,
            input_prompt="Plan content for Q3",
        )
        await executor.execute(request)

        call_kwargs = executor.callback.send_completed.call_args.kwargs
        progress = call_kwargs["progress"]

        for node_id in ["intent_router", "audience_analyzer", "content_planner", "calendar_builder"]:
            assert node_id in progress
            assert progress[node_id]["status"] == "done"

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_result_data_has_summary(
        self, mock_get_redis, content_strategy_manifest
    ):
        """Result data includes a summary even without external data."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        request = make_dispatch_request(
            content_strategy_manifest,
            input_prompt="Build editorial calendar",
        )
        await executor.execute(request)

        call_kwargs = executor.callback.send_completed.call_args.kwargs
        result_data = call_kwargs["result_data"]

        assert result_data is not None
        assert "summary" in result_data
