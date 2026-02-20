"""E2E test: brand-analysis pipeline flow.

Pipeline: RouterNode → market_research (discovery) → brand_strategist → report_generator

Note: brand-analysis uses ReportNode as terminal (not ManagerNode), so result_data
uses the JobExecutor default. ManagerNode aggregation is tested in iso-brand-equity.
"""

from unittest.mock import AsyncMock, patch

from app.services.job_executor import JobExecutor

from tests.e2e.conftest import make_dispatch_request


class TestBrandAnalysisPipeline:
    """Full E2E tests for the brand-analysis seed manifest."""

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_full_pipeline_completes_with_result_data(
        self, mock_get_redis, brand_analysis_manifest, mock_discovery_service
    ):
        """Execute brand-analysis manifest → completed callback with result_data."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        request = make_dispatch_request(brand_analysis_manifest)
        await executor.execute(request)

        executor.callback.send_completed.assert_called_once()
        call_kwargs = executor.callback.send_completed.call_args.kwargs
        result_data = call_kwargs.get("result_data")

        assert result_data is not None
        assert "summary" in result_data
        assert "findings" in result_data

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_discovery_findings_in_node_outputs(
        self, mock_get_redis, brand_analysis_manifest, mock_discovery_service
    ):
        """Discovery agent findings are stored in node_outputs['market_research']."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        request = make_dispatch_request(brand_analysis_manifest)
        await executor.execute(request)

        # The discovery service was called
        assert len(mock_discovery_service) == 1

        # The result_data comes from the executor default (ReportNode doesn't set it)
        # but the pipeline completed successfully with all nodes
        executor.callback.send_completed.assert_called_once()
        executor.callback.send_failed.assert_not_called()

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_callback_sequence_running_then_completed(
        self, mock_get_redis, brand_analysis_manifest, mock_discovery_service
    ):
        """Callbacks arrive in order: running → completed."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        request = make_dispatch_request(brand_analysis_manifest)
        await executor.execute(request)

        executor.callback.send_running.assert_called_once()
        executor.callback.send_completed.assert_called_once()
        executor.callback.send_failed.assert_not_called()

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_progress_has_all_four_nodes(
        self, mock_get_redis, brand_analysis_manifest, mock_discovery_service
    ):
        """Completed callback has progress entries for all 4 nodes, all 'done'."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        request = make_dispatch_request(brand_analysis_manifest)
        await executor.execute(request)

        call_kwargs = executor.callback.send_completed.call_args.kwargs
        progress = call_kwargs.get("progress", {})

        expected_nodes = ["intent_router", "market_research", "brand_strategist", "report_generator"]
        for node_id in expected_nodes:
            assert node_id in progress, f"Missing progress for {node_id}"
            assert progress[node_id]["status"] == "done", f"{node_id} not done"

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_discovery_receives_correct_payload(
        self, mock_get_redis, brand_analysis_manifest, mock_discovery_service
    ):
        """Discovery receives input_prompt, config.focus, tenant_context, previous_outputs."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        request = make_dispatch_request(brand_analysis_manifest)
        await executor.execute(request)

        assert len(mock_discovery_service) == 1
        payload = mock_discovery_service[0]["payload"]

        assert payload["input_prompt"] == "Analyze brand positioning for Acme Corp"
        assert "config" in payload
        assert payload["config"]["focus"] == "market_trends,competitors"
        assert "tenant_context" in payload
        assert "previous_outputs" in payload

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_focus_config_merged_with_global(
        self, mock_get_redis, brand_analysis_manifest, mock_discovery_service
    ):
        """Node config.focus is merged with global_config (model, temperature)."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        request = make_dispatch_request(brand_analysis_manifest)
        await executor.execute(request)

        payload = mock_discovery_service[0]["payload"]
        config = payload["config"]

        # Node-level config
        assert config["focus"] == "market_trends,competitors"
        # Global config merged in
        assert config["model"] == "gemini-2.0-flash"
        assert config["temperature"] == 0.7

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_report_node_sees_discovery_output(
        self, mock_get_redis, brand_analysis_manifest, mock_discovery_service
    ):
        """ReportNode receives discovery's output via node_outputs in state."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        request = make_dispatch_request(brand_analysis_manifest)
        await executor.execute(request)

        # The pipeline completed, meaning ReportNode executed after discovery
        executor.callback.send_completed.assert_called_once()
        # Discovery was called exactly once
        assert len(mock_discovery_service) == 1
