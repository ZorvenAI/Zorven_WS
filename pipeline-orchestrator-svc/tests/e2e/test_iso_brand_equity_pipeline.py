"""E2E test: iso-brand-equity pipeline flow.

Pipeline: RouterNode -> web_research (discovery)
-> valuation_logic (intelligence, stubbed) -> manager

This manifest uses ManagerNode as terminal, which aggregates findings and
recommendations from all node outputs into result_data. The intelligence
service is not wired, so ExternalWrapper returns stub data for valuation_logic.
"""

from unittest.mock import AsyncMock, patch

from app.services.job_executor import JobExecutor

from tests.e2e.conftest import make_dispatch_request


class TestIsoBrandEquityPipeline:
    """E2E tests for the iso-brand-equity seed manifest."""

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_pipeline_with_mixed_external_nodes(
        self, mock_get_redis, iso_brand_equity_manifest, mock_discovery_service
    ):
        """One external (discovery) is real, one (intelligence) falls back to stub."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        request = make_dispatch_request(iso_brand_equity_manifest)
        await executor.execute(request)

        # Pipeline completed despite intelligence service being unavailable
        executor.callback.send_completed.assert_called_once()
        executor.callback.send_failed.assert_not_called()

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_stub_fallback_for_unavailable_service(
        self, mock_get_redis, iso_brand_equity_manifest, mock_discovery_service
    ):
        """Intelligence service unavailable → ExternalWrapper returns stub data."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        request = make_dispatch_request(iso_brand_equity_manifest)
        await executor.execute(request)

        # Discovery was called (intercepted by mock)
        assert len(mock_discovery_service) == 1
        # Intelligence was NOT intercepted — ExternalWrapper stub handles it
        executor.callback.send_completed.assert_called_once()

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_manager_aggregates_from_all_nodes(
        self, mock_get_redis, iso_brand_equity_manifest, mock_discovery_service
    ):
        """ManagerNode aggregates findings from discovery + intelligence stub."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        request = make_dispatch_request(iso_brand_equity_manifest)
        await executor.execute(request)

        call_kwargs = executor.callback.send_completed.call_args.kwargs
        result_data = call_kwargs["result_data"]

        # ManagerNode sets result_data with aggregated findings
        assert "findings" in result_data
        assert isinstance(result_data["findings"], list)
        assert len(result_data["findings"]) > 0

        # Should include findings from discovery response
        assert any(
            "brand equity" in f.lower() or "market" in f.lower()
            for f in result_data["findings"]
        )

        # Should include findings from intelligence stub
        assert any("stub" in f.lower() for f in result_data["findings"])

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_iso_focus_config(
        self, mock_get_redis, iso_brand_equity_manifest, mock_discovery_service
    ):
        """Discovery receives focus=royalty_rates,market_trends,brand_rankings."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        request = make_dispatch_request(iso_brand_equity_manifest)
        await executor.execute(request)

        payload = mock_discovery_service[0]["payload"]
        assert (
            payload["config"]["focus"] == "royalty_rates,market_trends,brand_rankings"
        )

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_progress_has_all_four_nodes_done(
        self, mock_get_redis, iso_brand_equity_manifest, mock_discovery_service
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

        request = make_dispatch_request(iso_brand_equity_manifest)
        await executor.execute(request)

        call_kwargs = executor.callback.send_completed.call_args.kwargs
        progress = call_kwargs["progress"]

        for node_id in ["intent_router", "web_research", "valuation_logic", "manager"]:
            assert node_id in progress, f"Missing progress for {node_id}"
            assert progress[node_id]["status"] == "done"

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_result_data_has_score(
        self, mock_get_redis, iso_brand_equity_manifest, mock_discovery_service
    ):
        """ManagerNode includes a score in result_data."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        request = make_dispatch_request(iso_brand_equity_manifest)
        await executor.execute(request)

        call_kwargs = executor.callback.send_completed.call_args.kwargs
        result_data = call_kwargs["result_data"]

        assert "score" in result_data
        assert isinstance(result_data["score"], (int, float))
