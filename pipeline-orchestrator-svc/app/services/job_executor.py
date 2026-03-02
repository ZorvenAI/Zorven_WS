"""
Job executor — central orchestration service.

Ties together graph building, node execution, progress callbacks,
cancel checking, and result reporting. This is the core runtime
engine of the pipeline orchestrator.

Uses **direct sequential execution** instead of LangGraph's ainvoke /
astream.  This ensures per-node progress callbacks fire reliably across
all deployment targets (local Docker, Railway, etc.) by giving the
executor full control over the call → callback loop.
"""

import copy
import logging
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

from app.api.schemas import DispatchRequest
from app.core.config import settings
from app.core.redis_client import get_redis
from app.factory.graph_builder import GraphBuilder
from app.factory.node_registry import resolve_handler
from app.nodes.external_wrapper import ExternalWrapper
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
        3. If no manifest → run intent routing (PipelineComposer)
        4. Resolve node handlers (internal / external)
        5. Execute nodes sequentially with per-node progress callbacks
        6. Check cancel flag between nodes
        7. Send completed / failed callback at the end

        Uses **direct sequential execution** — the executor calls each
        node handler in topological order and sends progress callbacks
        between every step.  This bypasses LangGraph's ``ainvoke`` /
        ``astream`` execution engine entirely, ensuring per-node
        progress is visible on all deployment targets (local Docker,
        Railway, etc.).
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

                # Check for dynamically composed manifest first
                composed = state.get("_composed_manifest")
                if composed:
                    manifest_data = composed
                else:
                    resolved_id = state.get("resolved_manifest_id")
                    # Look up the full manifest_data from available_manifests
                    manifest_data = self._find_resolved_manifest(request, resolved_id)
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
                node_ids_added = []
                for node in manifest_data.get("nodes", []):
                    nid = node["id"]
                    if nid not in state["progress"]:
                        state["progress"][nid] = {"status": "pending"}
                        node_ids_added.append(nid)

                logger.info(
                    "Job %s: added %d pending nodes: %s",
                    job_id,
                    len(node_ids_added),
                    ", ".join(node_ids_added),
                )

                # Send progress with all pending nodes visible to the UI
                await self.callback.send_progress(
                    callback_url, copy.deepcopy(state["progress"])
                )

            # ── Resolve node handlers ──
            # Build handlers directly without using LangGraph's execution
            # engine.  This gives the executor full control over the
            # call → callback → cancel loop so per-node progress fires
            # reliably on every deployment target.
            nodes = manifest_data.get("nodes", [])
            global_config = manifest_data.get("global_config", {})

            node_ids: list[str] = []
            handlers: dict[str, Any] = {}

            # Topological sort to honour edges
            sorted_ids = self._topological_sort(
                manifest_data.get("nodes", []),
                manifest_data.get("edges", []),
            )

            for node_def in nodes:
                nid = node_def["id"]
                node_ids.append(nid)
                node_type = node_def.get("type", "internal")
                merged_config = {**global_config, **node_def.get("config", {})}

                if node_type == "internal":
                    handler_name = node_def.get("handler")
                    if not handler_name:
                        raise ValueError(f"Internal node '{nid}' missing 'handler'")
                    handler_cls = resolve_handler(handler_name)
                    handlers[nid] = handler_cls(config=merged_config)
                elif node_type == "external":
                    url = node_def.get("url", "")
                    url = GraphBuilder._translate_url(url)
                    handlers[nid] = ExternalWrapper(
                        url=url, node_id=nid, config=merged_config
                    )
                else:
                    raise ValueError(f"Unknown node type '{node_type}' for '{nid}'")

            logger.info(
                "Job %s: executing %d nodes sequentially: %s " "(callback_url=%s)",
                job_id,
                len(sorted_ids),
                " → ".join(sorted_ids),
                callback_url[:80] if callback_url else "<empty>",
            )

            # ── Check cancel before starting ──
            if await self._is_cancelled(job_id):
                logger.info("Job %s cancelled before execution", job_id)
                await self.callback.send_failed(
                    callback_url,
                    error_message="Job cancelled by user",
                    progress=state["progress"],
                )
                return

            # ── Sequential execution loop ──
            result_data = None

            try:
                for idx, nid in enumerate(sorted_ids):
                    handler = handlers.get(nid)
                    if handler is None:
                        logger.error("Job %s: no handler for node %s", job_id, nid)
                        continue

                    # Mark node as running
                    started_at = self._now_iso()
                    state["progress"][nid] = {
                        "status": "running",
                        "started_at": started_at,
                    }
                    await self.callback.send_progress(
                        callback_url, copy.deepcopy(state["progress"])
                    )

                    logger.info(
                        "Job %s: node %s starting (%d/%d)",
                        job_id,
                        nid,
                        idx + 1,
                        len(sorted_ids),
                    )

                    # Execute the handler
                    try:
                        node_result = await handler(state)
                    except Exception as exc:
                        logger.error(
                            "Job %s: node %s failed: %s",
                            job_id,
                            nid,
                            exc,
                            exc_info=True,
                        )
                        # Mark this node as failed
                        state["progress"][nid] = {
                            "status": "failed",
                            "started_at": started_at,
                            "completed_at": self._now_iso(),
                        }
                        # Mark remaining pending nodes as failed
                        for remaining_id in sorted_ids[idx + 1 :]:
                            if (
                                state["progress"].get(remaining_id, {}).get("status")
                                == "pending"
                            ):
                                state["progress"][remaining_id] = {
                                    "status": "failed",
                                    "completed_at": self._now_iso(),
                                }
                        await self.callback.send_failed(
                            callback_url,
                            error_message=f"Node {nid} failed: {exc}",
                            progress=state["progress"],
                        )
                        return

                    # Merge node result into state
                    if isinstance(node_result, dict):
                        if "node_outputs" in node_result:
                            state["node_outputs"].update(node_result["node_outputs"])
                        if "result_data" in node_result:
                            result_data = node_result["result_data"]

                    # Mark node as done
                    state["progress"][nid] = {
                        "status": "done",
                        "started_at": started_at,
                        "completed_at": self._now_iso(),
                    }

                    logger.info(
                        "Job %s: node %s completed (%d/%d)",
                        job_id,
                        nid,
                        idx + 1,
                        len(sorted_ids),
                    )

                    # Check cancel before the next node
                    if await self._is_cancelled(job_id):
                        logger.info(
                            "Job %s cancelled after node %s",
                            job_id,
                            nid,
                        )
                        # Mark remaining pending nodes
                        for remaining_id in sorted_ids[idx + 1 :]:
                            if (
                                state["progress"].get(remaining_id, {}).get("status")
                                == "pending"
                            ):
                                state["progress"][remaining_id] = {
                                    "status": "failed",
                                    "completed_at": self._now_iso(),
                                }
                        await self.callback.send_progress(
                            callback_url,
                            copy.deepcopy(state["progress"]),
                        )
                        await self.callback.send_failed(
                            callback_url,
                            error_message="Job cancelled by user",
                            progress=state["progress"],
                        )
                        return

                    # Send per-node progress callback
                    await self.callback.send_progress(
                        callback_url,
                        copy.deepcopy(state["progress"]),
                    )

            except Exception as exc:
                logger.error(
                    "Execution loop failed for job %s: %s",
                    job_id,
                    exc,
                    exc_info=True,
                )
                await self.callback.send_failed(
                    callback_url,
                    error_message=str(exc)[:10000],
                    progress=state["progress"],
                )
                return

            # Ensure all nodes are marked done in final progress
            final_progress = state["progress"]
            for nid in sorted_ids:
                if final_progress.get(nid, {}).get("status") not in (
                    "done",
                    "failed",
                ):
                    final_progress[nid] = {
                        "status": "done",
                        "completed_at": self._now_iso(),
                    }

            # Use accumulated result_data or fall back to default
            if result_data is None:
                result_data = {
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
        """Run PipelineComposer to dynamically compose or resolve a manifest."""
        from app.nodes.internal.pipeline_composer import PipelineComposer

        logger.info(
            "Auto-detect mode for job %s — running pipeline composer",
            request.job_id,
        )

        # Add composer to progress
        state["progress"]["pipeline_composer"] = {
            "status": "running",
            "started_at": self._now_iso(),
        }
        await self.callback.send_progress(
            request.callback_url, copy.deepcopy(state["progress"])
        )

        composer = PipelineComposer()
        result = await composer.compose(state)

        # Check if composer returned a dynamically built manifest
        composed = "_composed_manifest" in result
        if composed:
            state["_composed_manifest"] = result["_composed_manifest"]
            node_ids = [n["id"] for n in result["_composed_manifest"].get("nodes", [])]
            state["progress"]["pipeline_composer"] = {
                "status": "done",
                "output": {
                    "composed": True,
                    "pipeline": " → ".join(node_ids),
                },
                "started_at": state["progress"]["pipeline_composer"].get("started_at"),
                "completed_at": self._now_iso(),
            }
            # Send progress update (no manifest_id to resolve in DB)
            await self.callback.send_progress(
                request.callback_url, copy.deepcopy(state["progress"])
            )
        else:
            state["resolved_manifest_id"] = result.get("resolved_manifest_id")
            state["progress"]["pipeline_composer"] = {
                "status": "done",
                "output": {"resolved_manifest_id": state["resolved_manifest_id"]},
                "started_at": state["progress"]["pipeline_composer"].get("started_at"),
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
        if not resolved_id:
            return None
        if request.available_manifests:
            for manifest in request.available_manifests:
                if manifest.pipeline_id == resolved_id and manifest.manifest_data:
                    return manifest.manifest_data

        # Inline fallback for general-chat (single-node RAG pipeline)
        if resolved_id == "general-chat":
            return {
                "nodes": [
                    {
                        "id": "default_agent",
                        "type": "internal",
                        "handler": "DefaultAgentNode",
                    }
                ],
                "edges": [],
                "global_config": {},
            }

        return None

    @staticmethod
    def _topological_sort(
        nodes: list[dict[str, Any]],
        edges: list[list[str]],
    ) -> list[str]:
        """Return node IDs in topological (execution) order.

        Uses Kahn's algorithm.  Falls back to the original node list
        order if the graph has no edges (single-node or edge-free).

        Raises ValueError if the graph contains a cycle.
        """
        node_ids = [n["id"] for n in nodes]
        if not edges:
            return node_ids

        in_degree: dict[str, int] = {nid: 0 for nid in node_ids}
        adjacency: dict[str, list[str]] = defaultdict(list)

        for edge in edges:
            if len(edge) != 2:
                continue
            src, dst = edge[0], edge[1]
            if src in in_degree and dst in in_degree:
                adjacency[src].append(dst)
                in_degree[dst] += 1

        queue: deque[str] = deque(nid for nid in node_ids if in_degree[nid] == 0)
        sorted_ids: list[str] = []

        while queue:
            nid = queue.popleft()
            sorted_ids.append(nid)
            for neighbour in adjacency.get(nid, []):
                in_degree[neighbour] -= 1
                if in_degree[neighbour] == 0:
                    queue.append(neighbour)

        if len(sorted_ids) != len(node_ids):
            visited = set(sorted_ids)
            cyclic = [n for n in node_ids if n not in visited]
            raise ValueError(f"Manifest contains a cycle involving: {cyclic}")

        return sorted_ids

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
