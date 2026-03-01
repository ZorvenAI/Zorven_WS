"""
TrackedNode — wraps any pipeline node with per-node progress tracking.

Sends HTTP progress callbacks and Kafka trace events before and after
each node execution, so the frontend can display real-time per-node
status updates (pending → running → done/failed).
"""

import logging
from datetime import datetime, timezone
from typing import Any

from app.services.callback_client import CallbackClient
from app.state.schema import AgentState

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    """Current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


class TrackedNode:
    """Wraps a pipeline node with per-node progress tracking.

    Before execution: marks the node ``"running"`` and sends an HTTP
    progress callback + Kafka trace.

    After execution: marks the node ``"done"`` (or ``"failed"`` on error)
    and sends another callback + trace.

    The updated ``progress`` dict is returned alongside the inner node's
    result so LangGraph merges it into the shared state.
    """

    def __init__(
        self,
        node_id: str,
        inner: Any,
        callback_client: CallbackClient,
    ) -> None:
        self.node_id = node_id
        self.inner = inner
        self.callback_client = callback_client

    async def __call__(self, state: AgentState) -> dict:
        callback_url = state.get("callback_url", "")
        job_id = state.get("job_id", "")

        logger.info(
            "[TrackedNode] Node %s STARTING (job=%s, callback_url=%s)",
            self.node_id,
            job_id,
            callback_url[:80] if callback_url else "<empty>",
        )

        # Copy progress and mark this node as running
        progress = dict(state.get("progress", {}))
        started_at = _now_iso()
        progress[self.node_id] = {
            "status": "running",
            "started_at": started_at,
        }

        # Send running callback (non-blocking, non-fatal)
        if callback_url:
            ok = await self.callback_client.send_progress(
                callback_url, progress
            )
            logger.info(
                "[TrackedNode] Node %s → running callback sent (ok=%s)",
                self.node_id,
                ok,
            )
        else:
            logger.warning(
                "[TrackedNode] Node %s has NO callback_url — skipping progress",
                self.node_id,
            )

        # Emit Kafka trace (best-effort)
        await self._emit_trace(job_id, "started")

        # Execute the actual node
        try:
            result = await self.inner(state)
        except Exception as exc:
            logger.error(
                "[TrackedNode] Node %s FAILED: %s", self.node_id, exc
            )
            # Mark as failed
            progress[self.node_id] = {
                "status": "failed",
                "started_at": started_at,
                "completed_at": _now_iso(),
            }
            if callback_url:
                await self.callback_client.send_progress(
                    callback_url, progress
                )
            await self._emit_trace(job_id, "failed")
            raise

        # Mark as done
        progress[self.node_id] = {
            "status": "done",
            "started_at": started_at,
            "completed_at": _now_iso(),
        }

        logger.info(
            "[TrackedNode] Node %s DONE (job=%s)", self.node_id, job_id
        )

        # Send done callback
        if callback_url:
            ok = await self.callback_client.send_progress(
                callback_url, progress
            )
            logger.info(
                "[TrackedNode] Node %s → done callback sent (ok=%s)",
                self.node_id,
                ok,
            )

        # Emit Kafka trace
        await self._emit_trace(job_id, "completed")

        # Merge progress into the node result
        result["progress"] = progress
        return result

    async def _emit_trace(self, job_id: str, status: str) -> None:
        """Emit a Kafka trace event (best-effort, no-op if unavailable)."""
        try:
            from app.main import trace_producer

            if trace_producer and trace_producer.is_connected:
                await trace_producer.send_trace(
                    job_id=job_id,
                    node_id=self.node_id,
                    status=status,
                )
        except Exception:
            pass  # Kafka failures must not break execution
