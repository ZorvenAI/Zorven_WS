"""Tests for the job executor — end-to-end pipeline execution."""

from unittest.mock import AsyncMock, patch

from app.core.config import settings
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


def _stub_handler_factory(return_value=None):
    """Return a mock resolve_handler that returns async stub handlers."""
    async_handler = AsyncMock(return_value=return_value or {"node_outputs": {}})
    return lambda name: (lambda config=None: async_handler)


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

        with patch(
            "app.services.job_executor.resolve_handler",
            side_effect=_stub_handler_factory(),
        ):
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

        with patch(
            "app.services.job_executor.resolve_handler",
            side_effect=_stub_handler_factory(),
        ):
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
        """Invalid manifest (unknown handler) → resolution error → failed callback
        with per-node progress preserved."""
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
        executor.callback.send_progress.return_value = True
        executor.callback.send_failed.return_value = True

        request = _make_request(manifest=bad_manifest)
        await executor.execute(request)

        # Verify "failed" was sent with progress (not empty dict)
        executor.callback.send_failed.assert_called()
        call_kwargs = executor.callback.send_failed.call_args.kwargs
        progress = call_kwargs.get("progress", {})
        assert "bad" in progress, "progress should contain the node from the manifest"

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_empty_manifest_nodes_sends_failed(self, mock_get_redis):
        """Manifest with zero nodes → send_failed (not false-success)."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        empty_manifest = ManifestData(nodes=[], edges=[])

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_failed.return_value = True

        request = _make_request(manifest=empty_manifest)
        await executor.execute(request)

        executor.callback.send_failed.assert_called()
        call_kwargs = executor.callback.send_failed.call_args.kwargs
        assert "no nodes" in call_kwargs.get("error_message", "").lower()

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_external_node_missing_url_sends_failed(self, mock_get_redis):
        """External node without a url → resolution error → failed with progress."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        bad_manifest = ManifestData(
            nodes=[
                ManifestNode(id="ext", type="external", url=""),
            ],
            edges=[],
        )

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_failed.return_value = True

        request = _make_request(manifest=bad_manifest)
        await executor.execute(request)

        executor.callback.send_failed.assert_called()
        call_kwargs = executor.callback.send_failed.call_args.kwargs
        assert "url" in call_kwargs.get("error_message", "").lower()

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_malformed_edge_raises_error(self, mock_get_redis):
        """Manifest with a malformed edge (not 2-element) → failed."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        bad_manifest = ManifestData(
            nodes=[
                ManifestNode(id="a", type="internal", handler="StrategyNode"),
            ],
            edges=[["a"]],  # malformed
        )

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_failed.return_value = True

        request = _make_request(manifest=bad_manifest)
        await executor.execute(request)

        executor.callback.send_failed.assert_called()
        call_kwargs = executor.callback.send_failed.call_args.kwargs
        assert "malformed" in call_kwargs.get("error_message", "").lower()

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_edge_unknown_node_raises_error(self, mock_get_redis):
        """Manifest with an edge referencing an unknown node → failed."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        bad_manifest = ManifestData(
            nodes=[
                ManifestNode(id="a", type="internal", handler="StrategyNode"),
            ],
            edges=[["a", "nonexistent"]],
        )

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_failed.return_value = True

        request = _make_request(manifest=bad_manifest)
        await executor.execute(request)

        executor.callback.send_failed.assert_called()
        call_kwargs = executor.callback.send_failed.call_args.kwargs
        assert "unknown" in call_kwargs.get("error_message", "").lower()

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

        with patch(
            "app.services.job_executor.resolve_handler",
            side_effect=_stub_handler_factory(),
        ):
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
        """Inline fallback manifest for general-chat
        when no Django manifest available."""
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

        with patch(
            "app.services.job_executor.resolve_handler",
            side_effect=_stub_handler_factory(),
        ):
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

        with (
            patch(
                "app.nodes.internal.pipeline_composer.PipelineComposer.compose",
                new_callable=AsyncMock,
                return_value={"_composed_manifest": composed_manifest},
            ),
            patch(
                "app.services.job_executor.resolve_handler",
                side_effect=_stub_handler_factory(),
            ),
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

        with (
            patch(
                "app.nodes.internal.pipeline_composer.PipelineComposer.compose",
                new_callable=AsyncMock,
                return_value={"_composed_manifest": composed_manifest},
            ),
            patch(
                "app.services.job_executor.resolve_handler",
                side_effect=_stub_handler_factory(),
            ),
        ):
            request = _make_request(manifest=None)
            await executor.execute(request)

        # send_progress should be called multiple times:
        # 1. composer running, 2. composer done, 3. pending nodes,
        # 4. first node running, 5+ per-node done callbacks
        progress_calls = executor.callback.send_progress.call_args_list
        # Find the call that includes pending nodes (after composer done)
        found_pending = False
        for progress_call in progress_calls:
            progress = (
                progress_call.args[1]
                if len(progress_call.args) > 1
                else progress_call.kwargs.get("progress", {})
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

        with (
            patch(
                "app.nodes.internal.pipeline_composer.PipelineComposer.compose",
                new_callable=AsyncMock,
                return_value={"resolved_manifest_id": "blog-authoring"},
            ),
            patch(
                "app.services.job_executor.resolve_handler",
                side_effect=_stub_handler_factory(),
            ),
        ):
            request = _make_request(manifest=None, available_manifests=available)
            await executor.execute(request)

        executor.callback.send_completed.assert_called_once()
        executor.callback.send_resolved_manifest.assert_called_once()

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_sequential_sends_per_node_progress(self, mock_get_redis):
        """Direct sequential execution sends a progress callback after
        each node completes, with the completed node marked 'done'
        and the next node marked 'running'."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None  # not cancelled
        mock_get_redis.return_value = mock_redis

        # Stub handlers that return quickly
        mock_strategy = AsyncMock(
            return_value={"node_outputs": {"strategy": {"ok": True}}}
        )
        mock_report = AsyncMock(return_value={"node_outputs": {"report": {"ok": True}}})

        def _mock_resolve(name):
            handler_map = {
                "StrategyNode": lambda config=None: mock_strategy,
                "ReportNode": lambda config=None: mock_report,
            }
            factory = handler_map.get(name)
            if factory:
                return factory
            raise ValueError(f"Unknown handler: {name}")

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        with patch(
            "app.services.job_executor.resolve_handler",
            side_effect=_mock_resolve,
        ):
            request = _make_request()
            await executor.execute(request)

        # Verify progress callbacks include per-node done statuses.
        progress_calls = executor.callback.send_progress.call_args_list
        found_strategy_done = False
        found_report_done = False
        for c in progress_calls:
            progress = c.args[1] if len(c.args) > 1 else c.kwargs.get("progress", {})
            if isinstance(progress, dict):
                if progress.get("strategy", {}).get("status") == "done":
                    found_strategy_done = True
                if progress.get("report", {}).get("status") == "done":
                    found_report_done = True
        assert found_strategy_done, "strategy node should be marked done"
        assert found_report_done, "report node should be marked done"

        # Verify completed was sent
        executor.callback.send_completed.assert_called_once()

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_sequential_marks_first_node_running(self, mock_get_redis):
        """Before executing each node, the executor marks it 'running'
        so the UI shows immediate activity."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        mock_strategy = AsyncMock(
            return_value={"node_outputs": {"strategy": {"ok": True}}}
        )
        mock_report = AsyncMock(return_value={"node_outputs": {"report": {"ok": True}}})

        def _mock_resolve(name):
            return {
                "StrategyNode": lambda config=None: mock_strategy,
                "ReportNode": lambda config=None: mock_report,
            }[name]

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        with patch(
            "app.services.job_executor.resolve_handler",
            side_effect=_mock_resolve,
        ):
            request = _make_request()
            await executor.execute(request)

        # Find a progress call where strategy=running before it's done
        progress_calls = executor.callback.send_progress.call_args_list
        found_first_running = False
        for c in progress_calls:
            progress = c.args[1] if len(c.args) > 1 else c.kwargs.get("progress", {})
            if isinstance(progress, dict):
                strategy_status = progress.get("strategy", {}).get("status")
                report_status = progress.get("report", {}).get("status")
                if strategy_status == "running" and report_status == "pending":
                    found_first_running = True
                    break
        assert (
            found_first_running
        ), "First node should be marked running before execution"

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_no_langgraph_build_used(self, mock_get_redis):
        """The executor resolves handlers directly and does NOT call
        GraphBuilder.build — execution is fully sequential."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        mock_handler = AsyncMock(return_value={"node_outputs": {}})

        def _mock_resolve(name):
            return lambda config=None: mock_handler

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        with (
            patch(
                "app.services.job_executor.resolve_handler",
                side_effect=_mock_resolve,
            ),
            patch(
                "app.services.job_executor.GraphBuilder.build",
            ) as mock_build,
        ):
            request = _make_request()
            await executor.execute(request)

        # GraphBuilder.build should NOT be called
        mock_build.assert_not_called()

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_done_preserves_started_at(self, mock_get_redis):
        """When a node transitions from running → done, the started_at
        timestamp set during the running phase is preserved."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        mock_handler = AsyncMock(return_value={"node_outputs": {}})

        def _mock_resolve(name):
            return lambda config=None: mock_handler

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        with patch(
            "app.services.job_executor.resolve_handler",
            side_effect=_mock_resolve,
        ):
            request = _make_request()
            await executor.execute(request)

        # Completed callback's progress should have started_at for strategy
        call_kwargs = executor.callback.send_completed.call_args.kwargs
        progress = call_kwargs.get("progress", {})
        assert (
            "started_at" in progress["strategy"]
        ), "strategy should preserve started_at from running phase"
        assert progress["strategy"]["status"] == "done"

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_cancel_before_marking_next_running(self, mock_get_redis):
        """Cancel flag between nodes should NOT mark the next node as
        running — the job should stop immediately after the done callback."""
        mock_redis = AsyncMock()
        # 1st call: pre-execution cancel check → not cancelled
        # 2nd call: after strategy node completes → cancelled
        mock_redis.get.side_effect = [None, "1"]
        mock_get_redis.return_value = mock_redis

        mock_strategy = AsyncMock(
            return_value={"node_outputs": {"strategy": {"ok": True}}}
        )
        mock_report = AsyncMock(return_value={"node_outputs": {"report": {"ok": True}}})

        def _mock_resolve(name):
            return {
                "StrategyNode": lambda config=None: mock_strategy,
                "ReportNode": lambda config=None: mock_report,
            }[name]

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_failed.return_value = True

        with patch(
            "app.services.job_executor.resolve_handler",
            side_effect=_mock_resolve,
        ):
            request = _make_request()
            await executor.execute(request)

        # Should have ended with a failed/cancelled callback
        executor.callback.send_failed.assert_called()
        cancel_call = executor.callback.send_failed.call_args
        error_msg = cancel_call.kwargs.get("error_message", "")
        assert "cancel" in error_msg.lower()

        # report should NOT have been marked as running in any progress call
        for c in executor.callback.send_progress.call_args_list:
            progress = c.args[1] if len(c.args) > 1 else c.kwargs.get("progress", {})
            if isinstance(progress, dict):
                report_status = progress.get("report", {}).get("status")
                assert (
                    report_status != "running"
                ), "report should not be marked running after cancel"


class TestResolveCallbackUrl:
    """Tests for the CALLBACK_BASE_URL override mechanism."""

    def test_uses_dispatch_url_when_no_override(self):
        """Without CALLBACK_BASE_URL, uses the URL from the dispatch."""
        request = _make_request()
        original_val = settings.CALLBACK_BASE_URL
        try:
            settings.CALLBACK_BASE_URL = ""
            url = JobExecutor._resolve_callback_url(request)
            assert url == request.callback_url
        finally:
            settings.CALLBACK_BASE_URL = original_val

    def test_overrides_when_callback_base_url_set(self):
        """With CALLBACK_BASE_URL, constructs URL from base + job_id."""
        request = _make_request(job_id="job-abc-123")
        original_val = settings.CALLBACK_BASE_URL
        try:
            settings.CALLBACK_BASE_URL = "http://previsionws.railway.internal:8000"
            url = JobExecutor._resolve_callback_url(request)
            assert url == (
                "http://previsionws.railway.internal:8000"
                "/api/v1/orchestration/jobs/job-abc-123/callback/"
            )
            assert request.callback_url not in url
        finally:
            settings.CALLBACK_BASE_URL = original_val

    def test_strips_trailing_slash_from_base(self):
        """Trailing slash on CALLBACK_BASE_URL should not cause double slash."""
        request = _make_request(job_id="job-456")
        original_val = settings.CALLBACK_BASE_URL
        try:
            settings.CALLBACK_BASE_URL = "http://backend:8000/"
            url = JobExecutor._resolve_callback_url(request)
            assert "//api" not in url
            assert "/api/v1/orchestration/jobs/job-456/callback/" in url
        finally:
            settings.CALLBACK_BASE_URL = original_val


class TestTopologicalSort:
    """Unit tests for JobExecutor._topological_sort validation."""

    def test_valid_linear_graph(self):
        nodes = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        edges = [["a", "b"], ["b", "c"]]
        result = JobExecutor._topological_sort(nodes, edges)
        assert result == ["a", "b", "c"]

    def test_no_edges_preserves_order(self):
        nodes = [{"id": "x"}, {"id": "y"}]
        result = JobExecutor._topological_sort(nodes, [])
        assert result == ["x", "y"]

    def test_cycle_raises_value_error(self):
        import pytest

        nodes = [{"id": "a"}, {"id": "b"}]
        edges = [["a", "b"], ["b", "a"]]
        with pytest.raises(ValueError, match="cycle"):
            JobExecutor._topological_sort(nodes, edges)

    def test_malformed_edge_raises_value_error(self):
        import pytest

        nodes = [{"id": "a"}, {"id": "b"}]
        edges = [["a"]]  # only 1 element
        with pytest.raises(ValueError, match="malformed"):
            JobExecutor._topological_sort(nodes, edges)

    def test_unknown_node_in_edge_raises_value_error(self):
        import pytest

        nodes = [{"id": "a"}]
        edges = [["a", "ghost"]]
        with pytest.raises(ValueError, match="unknown"):
            JobExecutor._topological_sort(nodes, edges)
