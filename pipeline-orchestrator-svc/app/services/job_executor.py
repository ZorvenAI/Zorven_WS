"""
Job executor — central orchestration service.

Ties together graph building, node execution, progress callbacks,
cancel checking, and result reporting. This is the core runtime
engine of the pipeline orchestrator.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from app.api.schemas import DispatchRequest
from app.core.config import settings
from app.core.redis_client import get_redis
from app.factory.graph_builder import GraphBuilder, GraphBuildError
from app.services.callback_client import CallbackClient
from app.state.schema import AgentState

logger = logging.getLogger(__name__)


class JobExecutor:
    """Executes a pipeline job from dispatch request to completion."""

    def __init__(self) -> None:
        self.callback = CallbackClient(
            callback_token=settings.CALLBACK_TOKEN,
        )

    async def close(self) -> None:
        """Close the underlying callback HTTP client."""
        await self.callback.close()

    async def execute(self, request: DispatchRequest) -> None:
        """
        Execute a pipeline job end-to-end.

        1. Build initial AgentState from the dispatch request
        2. Send "running" callback + initial progress
        3. If no manifest → run intent routing
        4. Build LangGraph from manifest
        5. Execute nodes sequentially via graph
        6. Check cancel flag between nodes
        7. Send progress callbacks after each node
        8. Send completed / failed callback at the end
        """
        job_id = request.job_id
        callback_url = request.callback_url

        logger.info("Starting execution for job %s", job_id)

        try:
            # Build the initial state
            state = self._build_initial_state(request)

            # Send running status
            await self.callback.send_running(callback_url, state["progress"])

            # If no manifest provided, run intent routing first
            manifest_data = self._extract_manifest_data(request)
            if manifest_data is None:
                state = await self._handle_intent_routing(state, request)
                resolved_id = state.get("resolved_manifest_id")

                # Look up the full manifest_data from available_manifests
                manifest_data = self._find_resolved_manifest(
                    request, resolved_id
                )
                if manifest_data is None:
                    # No manifest_data available — cannot execute
                    await self.callback.send_completed(
                        callback_url,
                        result_data={
                            "summary": (
                                "Intent routing completed. "
                                f"Resolved manifest: {resolved_id}"
                            ),
                            "resolved_manifest_id": resolved_id,
                            "findings": ["Auto-detect routing completed."],
                            "recommendations": [
                                "Re-run with the resolved manifest "
                                "for full analysis."
                            ],
                        },
                        progress=state["progress"],
                    )
                    return

                # Initialize progress for the resolved manifest's nodes
                for node in manifest_data.get("nodes", []):
                    nid = node["id"]
                    if nid not in state["progress"]:
                        state["progress"][nid] = {"status": "pending"}

            # Build the LangGraph
            try:
                compiled_graph = GraphBuilder.build(manifest_data)
            except (GraphBuildError, ValueError) as exc:
                logger.error("Graph build failed for job %s: %s", job_id, exc)
                await self.callback.send_failed(
                    callback_url,
                    error_message=f"Graph build error: {exc}",
                    progress=state["progress"],
                )
                return

            # Execute the graph node by node
            nodes = manifest_data.get("nodes", [])
            node_ids = [n["id"] for n in nodes]

            # Check cancel flag before starting execution
            if await self._is_cancelled(job_id):
                logger.info("Job %s cancelled before execution", job_id)
                await self.callback.send_failed(
                    callback_url,
                    error_message="Job cancelled by user",
                    progress=state["progress"],
                )
                return

            # Invoke the compiled graph
            # LangGraph executes nodes in dependency order.
            # Per-node progress is reported via the progress dict
            # updated as the graph transitions state.
            try:
                result_state = await compiled_graph.ainvoke(
                    state,
                    config={
                        "configurable": {
                            "thread_id": f"{state.get('tenant_id', 'default')}:{job_id}"
                        }
                    },
                )
            except Exception as exc:
                logger.error(
                    "Graph execution failed for job %s: %s",
                    job_id,
                    exc,
                    exc_info=True,
                )
                # Mark remaining running nodes as failed
                for nid in node_ids:
                    if state["progress"].get(nid, {}).get("status") == "running":
                        state["progress"][nid] = {
                            "status": "failed",
                            "completed_at": self._now_iso(),
                        }
                await self.callback.send_failed(
                    callback_url,
                    error_message=str(exc)[:10000],
                    progress=state["progress"],
                )
                return

            # Update progress with completed status for all nodes
            final_progress = result_state.get("progress", state["progress"])
            for nid in node_ids:
                if final_progress.get(nid, {}).get("status") not in ("done", "failed"):
                    final_progress[nid] = {
                        "status": "done",
                        "completed_at": self._now_iso(),
                    }

            # Extract result_data from the final state
            result_data = result_state.get("result_data") or {
                "summary": "Pipeline completed successfully.",
                "findings": ["Analysis completed."],
                "recommendations": [],
            }

            # Check for cancel one last time
            if await self._is_cancelled(job_id):
                await self.callback.send_failed(
                    callback_url,
                    error_message="Job cancelled by user",
                    progress=final_progress,
                )
                return

            # Send completion
            await self.callback.send_completed(
                callback_url,
                result_data=result_data,
                progress=final_progress,
            )
            logger.info("Job %s completed successfully", job_id)

        except Exception as exc:
            logger.error(
                "Unexpected error executing job %s: %s",
                job_id,
                exc,
                exc_info=True,
            )
            try:
                await self.callback.send_failed(
                    callback_url,
                    error_message=f"Internal executor error: {exc}",
                    progress={},
                )
            except Exception:
                logger.error("Failed to send error callback for job %s", job_id)

    def _build_initial_state(self, request: DispatchRequest) -> AgentState:
        """Build the initial AgentState from a DispatchRequest."""
        tenant_ctx = request.tenant_context
        nodes = []
        if request.manifest:
            nodes = request.manifest.nodes

        progress: dict[str, dict[str, Any]] = {}
        for node in nodes:
            progress[node.id] = {"status": "pending"}

        state: AgentState = {
            "job_id": request.job_id,
            "tenant_id": tenant_ctx.tenant_id if tenant_ctx else "",
            "input_prompt": request.input_prompt,
            "input_context": request.input_context,
            "tenant_context": (tenant_ctx.model_dump() if tenant_ctx else {}),
            "global_config": (
                request.manifest.global_config if request.manifest else {}
            ),
            "callback_url": request.callback_url,
            "available_manifests": (
                [m.model_dump() for m in request.available_manifests]
                if request.available_manifests
                else None
            ),
            "resolved_manifest_id": None,
            "node_outputs": {},
            "progress": progress,
            "result_data": None,
            "error": None,
            "cancelled": False,
        }
        return state

    def _extract_manifest_data(self, request: DispatchRequest) -> dict[str, Any] | None:
        """Extract manifest_data dict from the request, or None for auto-detect."""
        if request.manifest is None:
            return None
        return request.manifest.model_dump()

    async def _handle_intent_routing(
        self,
        state: AgentState,
        request: DispatchRequest,
    ) -> AgentState:
        """Run the RouterNode to resolve the best manifest."""
        from app.nodes.internal.router_node import RouterNode

        logger.info(
            "Auto-detect mode for job %s — running intent routing",
            request.job_id,
        )

        # Add router to progress
        state["progress"]["intent_router"] = {
            "status": "running",
            "started_at": self._now_iso(),
        }
        await self.callback.send_progress(request.callback_url, state["progress"])

        router = RouterNode()
        updates = await router(state)
        state["resolved_manifest_id"] = updates.get("resolved_manifest_id")

        state["progress"]["intent_router"] = {
            "status": "done",
            "output": {"resolved_manifest_id": state["resolved_manifest_id"]},
            "started_at": state["progress"]["intent_router"].get("started_at"),
            "completed_at": self._now_iso(),
        }

        # Notify the callback about the resolved manifest
        await self.callback.send_resolved_manifest(
            request.callback_url,
            manifest_id=state["resolved_manifest_id"] or "brand-analysis",
            progress=state["progress"],
        )

        return state

    @staticmethod
    def _find_resolved_manifest(
        request: DispatchRequest, resolved_id: str | None
    ) -> dict[str, Any] | None:
        """Find the full manifest_data for a resolved pipeline_id."""
        if not resolved_id or not request.available_manifests:
            return None
        for manifest in request.available_manifests:
            if manifest.pipeline_id == resolved_id and manifest.manifest_data:
                return manifest.manifest_data
        return None

    async def _is_cancelled(self, job_id: str) -> bool:
        """Check if a cancel flag is set in Redis for this job."""
        try:
            redis = await get_redis()
            cancel_flag = await redis.get(f"cancel:{job_id}")
            return cancel_flag is not None
        except Exception:
            # Redis failure shouldn't crash the executor
            return False

    @staticmethod
    def _now_iso() -> str:
        """Current UTC timestamp in ISO 8601 format."""
        return datetime.now(timezone.utc).isoformat()
