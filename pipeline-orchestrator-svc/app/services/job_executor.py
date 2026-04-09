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

import asyncio
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

    @staticmethod
    def _merge_result_data(existing: Any, incoming: Any) -> Any:
        """
        Merge ``incoming`` result_data into ``existing`` result_data.

        Dicts are deep-merged one level (``node_payloads`` dicts are
        merged key-by-key so multiple external agents can contribute
        without overwriting each other). Non-dict ``incoming`` values
        replace ``existing`` entirely, matching the previous behavior.
        """
        if not isinstance(incoming, dict):
            return incoming
        if not isinstance(existing, dict):
            return dict(incoming)

        for key, value in incoming.items():
            if (
                key == "node_payloads"
                and isinstance(value, dict)
                and isinstance(existing.get(key), dict)
            ):
                existing[key].update(value)
            else:
                existing[key] = value
        return existing

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
        callback_url = self._resolve_callback_url(request)

        logger.info("Starting execution for job %s", job_id)

        try:
            # Build the initial state
            state = self._build_initial_state(request)

            # Send running status
            await self.callback.send_running(callback_url, state["progress"])

            # If no manifest provided, run intent routing first
            manifest_data = self._extract_manifest_data(request)
            if manifest_data is None:
                state = await self._handle_intent_routing(state, request, callback_url)

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

            if not nodes:
                logger.error("Job %s: manifest contains no nodes", job_id)
                await self.callback.send_failed(
                    callback_url,
                    error_message="Manifest contains no nodes",
                    progress=state["progress"],
                )
                return

            handlers: dict[str, Any] = {}

            # Topological sort + handler resolution.  If this fails
            # (e.g. unknown handler, invalid node type, cycle in edges)
            # we fail fast but still return the already-initialised
            # per-node progress so the UI can show pending nodes.
            try:
                sorted_ids = self._topological_sort(
                    manifest_data.get("nodes", []),
                    manifest_data.get("edges", []),
                )

                # Resolve skill router once (avoids per-node import)
                from app.api import routes as api_routes

                _skill_router = api_routes.skill_router

                for node_def in nodes:
                    nid = node_def["id"]
                    node_type = node_def.get("type", "internal")
                    merged_config = {
                        **global_config,
                        **node_def.get("config", {}),
                    }

                    # Inject matched skills into node configs (internal + external)
                    if _skill_router:
                        skill_additions = _skill_router.resolve_skills_for_node(
                            nid, state.get("input_prompt", "")
                        )
                        if skill_additions:
                            merged_config.update(skill_additions)

                    if node_type == "internal":
                        handler_name = node_def.get("handler")
                        if not handler_name:
                            raise ValueError(f"Internal node '{nid}' missing 'handler'")
                        handler_cls = resolve_handler(handler_name)
                        handlers[nid] = handler_cls(config=merged_config)
                    elif node_type == "external":
                        url = node_def.get("url", "")
                        if not url:
                            raise ValueError(f"External node '{nid}' missing 'url'")
                        url = GraphBuilder._translate_url(url)
                        handlers[nid] = ExternalWrapper(
                            url=url, node_id=nid, config=merged_config
                        )
                    else:
                        raise ValueError(f"Unknown node type '{node_type}' for '{nid}'")
            except Exception as exc:
                logger.exception(
                    "Job %s: manifest/handler resolution failed: %s",
                    job_id,
                    exc,
                )
                await self.callback.send_failed(
                    callback_url,
                    error_message=(f"Manifest or handler resolution error: {exc}"),
                    progress=state["progress"],
                )
                return

            levels = self._compute_execution_levels(
                nodes, manifest_data.get("edges", [])
            )
            flat_sorted = [nid for level in levels for nid in level]

            level_desc = " | ".join(",".join(lvl) for lvl in levels)
            logger.info(
                "Job %s: executing %d nodes in %d levels: [%s] " "(callback_url=%s)",
                job_id,
                len(flat_sorted),
                len(levels),
                level_desc,
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

            # ── Validate handler coverage ──
            missing_handlers = [nid for nid in flat_sorted if handlers.get(nid) is None]
            if missing_handlers:
                logger.error(
                    "Job %s: missing handlers for node(s): %s",
                    job_id,
                    ", ".join(missing_handlers),
                )
                now_iso = self._now_iso()
                for missing_id in missing_handlers:
                    state["progress"][missing_id] = {
                        "status": "failed",
                        "completed_at": now_iso,
                    }
                await self.callback.send_failed(
                    callback_url,
                    error_message=(
                        "Execution aborted due to missing handlers "
                        "for node(s): " + ", ".join(missing_handlers)
                    ),
                    progress=state["progress"],
                )
                return

            # ── Level-based execution loop ──
            # Nodes within the same level are independent and run in
            # parallel via asyncio.gather().  Levels execute sequentially.
            result_data = None
            executed_node_count = 0

            try:
                for level_idx, level_nodes in enumerate(levels):
                    # Cancel check before each level
                    if await self._is_cancelled(job_id):
                        logger.info(
                            "Job %s cancelled before level %d",
                            job_id,
                            level_idx,
                        )
                        for remaining_id in flat_sorted[executed_node_count:]:
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

                    # Mark all nodes in this level as running
                    started_at = self._now_iso()
                    for nid in level_nodes:
                        state["progress"][nid] = {
                            "status": "running",
                            "started_at": started_at,
                        }
                    await self.callback.send_progress(
                        callback_url, copy.deepcopy(state["progress"])
                    )

                    for nid in level_nodes:
                        logger.info(
                            "Job %s: node %s starting (level %d/%d)",
                            job_id,
                            nid,
                            level_idx + 1,
                            len(levels),
                        )

                    if len(level_nodes) == 1:
                        # Single node — run directly
                        nid = level_nodes[0]
                        handler = handlers[nid]
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
                            state["progress"][nid] = {
                                "status": "failed",
                                "started_at": started_at,
                                "completed_at": self._now_iso(),
                            }
                            for remaining_id in flat_sorted[executed_node_count + 1 :]:
                                if (
                                    state["progress"]
                                    .get(remaining_id, {})
                                    .get("status")
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

                        # Merge result
                        if isinstance(node_result, dict):
                            if "node_outputs" in node_result:
                                state["node_outputs"].update(
                                    node_result["node_outputs"]
                                )
                            if "result_data" in node_result:
                                result_data = self._merge_result_data(
                                    result_data, node_result["result_data"]
                                )
                    else:
                        # Parallel execution via asyncio.gather
                        tasks = [handlers[nid](state) for nid in level_nodes]
                        results = await asyncio.gather(*tasks, return_exceptions=True)

                        # Classify all results: mark each node done or failed
                        failed_nodes: list[str] = []
                        completed_at = self._now_iso()
                        for nid, result in zip(level_nodes, results):
                            if isinstance(result, Exception):
                                logger.error(
                                    "Job %s: node %s failed (parallel): %s",
                                    job_id,
                                    nid,
                                    result,
                                    exc_info=(
                                        type(result),
                                        result,
                                        result.__traceback__,
                                    ),
                                )
                                state["progress"][nid] = {
                                    "status": "failed",
                                    "started_at": started_at,
                                    "completed_at": completed_at,
                                }
                                failed_nodes.append(nid)

                        # If any node failed, abort the pipeline
                        if failed_nodes:
                            # Mark remaining future nodes as failed
                            remaining_start = executed_node_count + len(level_nodes)
                            for remaining_id in flat_sorted[remaining_start:]:
                                if (
                                    state["progress"]
                                    .get(remaining_id, {})
                                    .get("status")
                                    == "pending"
                                ):
                                    state["progress"][remaining_id] = {
                                        "status": "failed",
                                        "completed_at": completed_at,
                                    }
                            await self.callback.send_failed(
                                callback_url,
                                error_message=(
                                    f"Parallel nodes failed: "
                                    f"{', '.join(failed_nodes)}"
                                ),
                                progress=state["progress"],
                            )
                            return

                        # All succeeded — merge results
                        for nid, result in zip(level_nodes, results):
                            if isinstance(result, dict):
                                if "node_outputs" in result:
                                    state["node_outputs"].update(result["node_outputs"])
                                if "result_data" in result:
                                    result_data = self._merge_result_data(
                                        result_data, result["result_data"]
                                    )

                    # Check if any node requires human approval BEFORE
                    # marking as done, so progress shows the correct state.
                    awaiting_node = None
                    for nid in level_nodes:
                        node_out = state["node_outputs"].get(nid)
                        if (
                            isinstance(node_out, dict)
                            and node_out.get("status") == "awaiting_approval"
                        ):
                            awaiting_node = nid
                            break

                    # Mark all nodes in this level as done (or
                    # awaiting_approval for the gated node).
                    completed_at = self._now_iso()
                    for nid in level_nodes:
                        if nid == awaiting_node:
                            state["progress"][nid] = {
                                "status": "awaiting_approval",
                                "started_at": started_at,
                                "completed_at": completed_at,
                            }
                        else:
                            state["progress"][nid] = {
                                "status": "done",
                                "started_at": started_at,
                                "completed_at": completed_at,
                            }
                    executed_node_count += len(level_nodes)

                    for nid in level_nodes:
                        logger.info(
                            "Job %s: node %s completed (level %d/%d)",
                            job_id,
                            nid,
                            level_idx + 1,
                            len(levels),
                        )

                    # Build partial result_data with ONLY this level's outputs
                    # to avoid exceeding the 1 MB CallbackSerializer limit.
                    # We intentionally do NOT merge the accumulated result_data
                    # into progress callbacks — external agents can return
                    # large payloads (creative generation, ad publishing) and
                    # sending them on every level inflates callbacks and
                    # duplicates data that ManagerNode will already include
                    # in the final completed callback.
                    level_outputs = {
                        nid: state["node_outputs"][nid]
                        for nid in level_nodes
                        if nid in state["node_outputs"]
                    }
                    partial_result_data: dict[str, Any] = {
                        "node_results": level_outputs,
                    }

                    # If a node requires human approval, send the
                    # awaiting_approval callback and pause the pipeline.
                    if awaiting_node:
                        logger.info(
                            "Job %s: node %s requires human approval "
                            "— pausing pipeline",
                            job_id,
                            awaiting_node,
                        )
                        # Surface the gating node's top-level keys
                        # (approval_request_id, preview_data, sandbox_mode,
                        # plan_warnings, status) alongside the accumulated
                        # result_data so Django's callback handler and the
                        # frontend ResultDashboard can find them without
                        # digging into node_payloads.
                        approval_result_data: dict[str, Any] = {}
                        if isinstance(result_data, dict):
                            approval_result_data.update(result_data)
                        gate_output = state["node_outputs"].get(awaiting_node)
                        if isinstance(gate_output, dict):
                            for key in (
                                "status",
                                "approval_request_id",
                                "preview_data",
                                "sandbox_mode",
                                "plan_warnings",
                            ):
                                if key in gate_output:
                                    approval_result_data[key] = gate_output[key]
                            payloads = approval_result_data.setdefault(
                                "node_payloads", {}
                            )
                            if isinstance(payloads, dict):
                                payloads[awaiting_node] = gate_output
                        await self.callback.send_awaiting_approval(
                            callback_url,
                            result_data=approval_result_data,
                            progress=copy.deepcopy(state["progress"]),
                        )
                        return

                    # Send per-level progress callback with partial results
                    await self.callback.send_progress(
                        callback_url,
                        copy.deepcopy(state["progress"]),
                        result_data=partial_result_data,
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
            for nid in flat_sorted:
                if final_progress.get(nid, {}).get("status") not in (
                    "done",
                    "failed",
                ):
                    final_progress[nid] = {
                        "status": "done",
                        "completed_at": self._now_iso(),
                    }

            # Use accumulated result_data or fall back to default.
            # Also backfill default summary/findings/recommendations when an
            # accumulated result_data exists but lacks these top-level keys
            # (e.g. pipelines without a ManagerNode where only external
            # agents contributed per-node payloads).
            if result_data is None:
                result_data = {
                    "summary": "Pipeline completed successfully.",
                    "findings": ["Analysis completed."],
                    "recommendations": [],
                }
            elif isinstance(result_data, dict):
                result_data.setdefault("summary", "Pipeline completed successfully.")
                result_data.setdefault("findings", ["Analysis completed."])
                result_data.setdefault("recommendations", [])

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

    @staticmethod
    def _resolve_callback_url(request: DispatchRequest) -> str:
        """Resolve the callback URL for this job.

        If ``ORCHESTRATOR_CALLBACK_BASE_URL`` is configured, build the
        callback URL from it (overriding whatever Django sent in the
        dispatch payload).  This makes callbacks resilient to Django
        having an incorrect ``CALLBACK_BASE_URL`` env var.
        """
        if settings.CALLBACK_BASE_URL:
            base = settings.CALLBACK_BASE_URL.rstrip("/")
            overridden = (
                f"{base}/api/v1/orchestration/jobs/" f"{request.job_id}/callback/"
            )
            logger.info(
                "Job %s: callback URL overridden to %s " "(was: %s)",
                request.job_id,
                overridden,
                (request.callback_url or "<empty>")[:80],
            )
            return overridden
        return request.callback_url

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
        callback_url: str,
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
            callback_url, copy.deepcopy(state["progress"])
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
                callback_url, copy.deepcopy(state["progress"])
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
                callback_url,
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

        node_id_set = set(node_ids)
        for i, edge in enumerate(edges):
            if len(edge) != 2:
                raise ValueError(
                    f"Edge at index {i} is malformed (expected 2 "
                    f"elements, got {len(edge)}): {edge}"
                )
            src, dst = edge[0], edge[1]
            unknown = [n for n in (src, dst) if n not in node_id_set]
            if unknown:
                raise ValueError(
                    f"Edge [{src}, {dst}] references unknown " f"node(s): {unknown}"
                )
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

    @staticmethod
    def _compute_execution_levels(
        nodes: list[dict[str, Any]],
        edges: list[list[str]],
    ) -> list[list[str]]:
        """Group nodes into parallel execution levels via Kahn's algorithm.

        Returns list of levels.  Within a level, nodes are independent
        and can run concurrently.  Between levels, all prior levels must
        complete before the next level starts.
        """
        node_ids = [n["id"] for n in nodes]
        if not edges:
            return [node_ids]

        in_degree: dict[str, int] = {nid: 0 for nid in node_ids}
        adjacency: dict[str, list[str]] = defaultdict(list)

        for edge in edges:
            src, dst = edge[0], edge[1]
            adjacency[src].append(dst)
            in_degree[dst] += 1

        levels: list[list[str]] = []
        queue = [nid for nid in node_ids if in_degree[nid] == 0]

        while queue:
            levels.append(queue)
            next_queue: list[str] = []
            for nid in queue:
                for neighbour in adjacency.get(nid, []):
                    in_degree[neighbour] -= 1
                    if in_degree[neighbour] == 0:
                        next_queue.append(neighbour)
            queue = next_queue

        return levels

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
