"""Tests for the job executor — end-to-end pipeline execution."""

from unittest.mock import AsyncMock, patch

from app.api.schemas import (
    AvailableManifest,
    DispatchRequest,
    ManifestData,
    ManifestNode,
    TenantContext,
)
from app.services.job_executor import JobExecutor

# Use a sentinel to distinguish "no manifest" from "explicit None"
_UNSET = object()


def _make_request(manifest=_UNSET, available_manifests=None, job_id="test-job-123"):
    """Build a DispatchRequest for testing."""
    if manifest is _UNSET:
        manifest = ManifestData(
            nodes=[
                ManifestNode(id="strategy", type="internal", handler="StrategyNode"),
                ManifestNode(id="report", type="internal", handler="ReportNode"),
            ],
            edges=[["strategy", "report"]],
            global_config={"model": "gemini-2.0-flash"},
        )

    return DispatchRequest(
        job_id=job_id,
        manifest=manifest,
        input_prompt="Analyze brand positioning for Acme Corp",
        input_context={"company_id": 42},
        tenant_context=TenantContext(
            tenant_id="1",
            gcs_raw_bucket="bucket/",
            gcs_processed_bucket="curated/",
            rag_data_store_id="ds-1",
        ),
        callback_url=(
            "http://backend:8001/api/v1/orchestration" "/jobs/test-job-123/callback/"
        ),
        available_manifests=available_manifests,
    )


class TestJobExecutor:
    """Test executor with mocked callback client and Redis."""

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_execute_simple_manifest(self, mock_get_redis):
        """Execute a 2-node manifest → completed callback."""
        # Mock Redis cancel check
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None  # not cancelled
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        request = _make_request()
        await executor.execute(request)

        # Verify "running" was sent
        executor.callback.send_running.assert_called_once()

        # Verify "completed" was sent with result_data
        executor.callback.send_completed.assert_called_once()
        call_args = executor.callback.send_completed.call_args
        assert call_args.kwargs.get("result_data") is not None

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_execute_auto_detect_mode(self, mock_get_redis):
        """Execute without manifest → intent routing → completed."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True
        executor.callback.send_resolved_manifest.return_value = True

        request = _make_request(manifest=None)
        await executor.execute(request)

        # Verify resolved manifest was sent
        executor.callback.send_resolved_manifest.assert_called_once()

        # Verify completed was sent
        executor.callback.send_completed.assert_called_once()

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_cancel_flag_stops_execution(self, mock_get_redis):
        """Cancel flag in Redis → job fails with 'cancelled' message."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = "1"  # cancelled!
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_failed.return_value = True

        request = _make_request()
        await executor.execute(request)

        # Verify "failed" was sent with cancel message
        executor.callback.send_failed.assert_called()
        call_args = executor.callback.send_failed.call_args
        error_msg = call_args.kwargs.get("error_message", "")
        if not error_msg and len(call_args.args) > 1:
            error_msg = call_args.args[1]
        assert "cancel" in error_msg.lower()

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_invalid_manifest_sends_failed(self, mock_get_redis):
        """Invalid manifest (unknown handler) → graph build error → failed callback."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        bad_manifest = ManifestData(
            nodes=[
                ManifestNode(id="bad", type="internal", handler="UnknownNode"),
            ],
            edges=[],
        )

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_failed.return_value = True

        request = _make_request(manifest=bad_manifest)
        await executor.execute(request)

        # Verify "failed" was sent
        executor.callback.send_failed.assert_called()

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_completed_includes_progress_for_all_nodes(self, mock_get_redis):
        """Completed callback includes progress entries for every node."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        request = _make_request()
        await executor.execute(request)

        # Completed callback must include progress for all nodes
        executor.callback.send_completed.assert_called_once()
        call_kwargs = executor.callback.send_completed.call_args.kwargs
        progress = call_kwargs.get("progress", {})
        assert "strategy" in progress
        assert "report" in progress
        # All nodes should be marked done
        for node_id in ("strategy", "report"):
            assert progress[node_id]["status"] == "done"

    def test_general_chat_inline_manifest(self):
        """Inline fallback manifest for general-chat when no Django manifest available."""
        request = _make_request(manifest=None, available_manifests=[])
        result = JobExecutor._find_resolved_manifest(request, "general-chat")
        assert result is not None
        assert len(result["nodes"]) == 1
        assert result["nodes"][0]["handler"] == "DefaultAgentNode"
        assert result["edges"] == []

    def test_find_resolved_manifest_returns_none_for_unknown(self):
        """Unknown pipeline_id without inline fallback returns None."""
        request = _make_request(manifest=None, available_manifests=[])
        result = JobExecutor._find_resolved_manifest(request, "unknown-pipeline")
        assert result is None

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_redis_failure_doesnt_crash(self, mock_get_redis):
        """Redis unavailable for cancel check → execution continues."""
        mock_redis = AsyncMock()
        mock_redis.get.side_effect = Exception("Redis down")
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        request = _make_request()
        await executor.execute(request)

        # Should still complete (Redis failure is non-fatal for cancel check)
        executor.callback.send_completed.assert_called_once()

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_composed_manifest_used_directly(self, mock_get_redis):
        """PipelineComposer returns composed manifest → used directly."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        composed_manifest = {
            "nodes": [
                {
                    "id": "strategy",
                    "type": "internal",
                    "handler": "StrategyNode",
                },
                {
                    "id": "report",
                    "type": "internal",
                    "handler": "ReportNode",
                },
            ],
            "edges": [["strategy", "report"]],
            "global_config": {"model": "gemini-2.0-flash", "temperature": 0.7},
        }

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True
        executor.callback.send_resolved_manifest.return_value = True

        with patch(
            "app.nodes.internal.pipeline_composer.PipelineComposer.compose",
            new_callable=AsyncMock,
            return_value={"_composed_manifest": composed_manifest},
        ):
            request = _make_request(manifest=None)
            await executor.execute(request)

        # Completed should be called (not the "cannot execute" path)
        executor.callback.send_completed.assert_called_once()
        call_kwargs = executor.callback.send_completed.call_args.kwargs
        progress = call_kwargs.get("progress", {})
        # The composed manifest's nodes should be in progress
        assert "strategy" in progress
        assert "report" in progress

        # send_resolved_manifest should NOT be called for composed manifests
        # (no DB manifest to resolve — avoids the "_composed not found" warning)
        executor.callback.send_resolved_manifest.assert_not_called()
        # Instead, send_progress should be called for the composer update
        executor.callback.send_progress.assert_called()

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_composed_manifest_sends_pending_nodes_progress(self, mock_get_redis):
        """After intent routing resolves nodes, send_progress is called
        with all new nodes as 'pending' before streaming starts."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        composed_manifest = {
            "nodes": [
                {"id": "discovery", "type": "internal", "handler": "StrategyNode"},
                {"id": "intelligence", "type": "internal", "handler": "ReportNode"},
            ],
            "edges": [["discovery", "intelligence"]],
            "global_config": {},
        }

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        with patch(
            "app.nodes.internal.pipeline_composer.PipelineComposer.compose",
            new_callable=AsyncMock,
            return_value={"_composed_manifest": composed_manifest},
        ):
            request = _make_request(manifest=None)
            await executor.execute(request)

        # send_progress should be called multiple times:
        # 1. composer running, 2. composer done, 3. pending nodes before stream,
        # 4. first node running, 5+ per-node done callbacks
        progress_calls = executor.callback.send_progress.call_args_list
        # Find the call that includes pending nodes (after composer done)
        found_pending = False
        for call in progress_calls:
            progress = (
                call.args[1] if len(call.args) > 1 else call.kwargs.get("progress", {})
            )
            if isinstance(progress, dict):
                discovery_status = progress.get("discovery", {}).get("status")
                intelligence_status = progress.get("intelligence", {}).get("status")
                if discovery_status == "pending" and intelligence_status == "pending":
                    found_pending = True
                    break
        assert (
            found_pending
        ), "send_progress must be called with pending nodes before streaming"

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_composer_fallback_resolves_manifest_id(self, mock_get_redis):
        """PipelineComposer keyword fallback → resolves manifest_id."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True
        executor.callback.send_resolved_manifest.return_value = True

        # Provide available_manifests so the resolved ID can be looked up
        available = [
            AvailableManifest(
                pipeline_id="blog-authoring",
                name="Blog Authoring",
                description="Write a blog",
                manifest_data={
                    "nodes": [
                        {
                            "id": "strategy",
                            "type": "internal",
                            "handler": "StrategyNode",
                        },
                    ],
                    "edges": [],
                    "global_config": {},
                },
            )
        ]

        with patch(
            "app.nodes.internal.pipeline_composer.PipelineComposer.compose",
            new_callable=AsyncMock,
            return_value={"resolved_manifest_id": "blog-authoring"},
        ):
            request = _make_request(manifest=None, available_manifests=available)
            await executor.execute(request)

        executor.callback.send_completed.assert_called_once()
        executor.callback.send_resolved_manifest.assert_called_once()

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_streaming_sends_per_node_progress(self, mock_get_redis):
        """astream sends a progress callback after each node completes,
        with the completed node marked 'done' and next pending node
        marked 'running'."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None  # not cancelled
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        request = _make_request()
        await executor.execute(request)

        # Verify progress callbacks include per-node done statuses.
        # The manifest has nodes: strategy → report. We expect progress
        # calls that show strategy=done → report=running, then
        # report=done.
        progress_calls = executor.callback.send_progress.call_args_list
        found_strategy_done = False
        found_report_done = False
        for call in progress_calls:
            progress = (
                call.args[1] if len(call.args) > 1 else call.kwargs.get("progress", {})
            )
            if isinstance(progress, dict):
                if progress.get("strategy", {}).get("status") == "done":
                    found_strategy_done = True
                if progress.get("report", {}).get("status") == "done":
                    found_report_done = True
        assert found_strategy_done, "strategy node should be marked done via stream"
        assert found_report_done, "report node should be marked done via stream"

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_streaming_marks_first_node_running(self, mock_get_redis):
        """Before streaming starts, the first node is marked 'running'
        so the UI shows immediate activity."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        request = _make_request()
        await executor.execute(request)

        # Find a progress call where strategy=running before it's done
        progress_calls = executor.callback.send_progress.call_args_list
        found_first_running = False
        for call in progress_calls:
            progress = (
                call.args[1] if len(call.args) > 1 else call.kwargs.get("progress", {})
            )
            if isinstance(progress, dict):
                strategy_status = progress.get("strategy", {}).get("status")
                report_status = progress.get("report", {}).get("status")
                if strategy_status == "running" and report_status == "pending":
                    found_first_running = True
                    break
        assert (
            found_first_running
        ), "First node should be marked running before streaming"
