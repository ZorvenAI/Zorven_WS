"""
LangGraph shared state schema.

AgentState is the TypedDict that flows through every node in the
pipeline graph. Each node reads from and writes to this shared state.

The `progress` dict matches the AgentProgress TypeScript type used
by the frontend ThoughtTrace component.
"""

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    """Shared memory for the LangGraph pipeline execution."""

    # ── Job identity ──
    job_id: str
    tenant_id: str

    # ── User input ──
    input_prompt: str
    input_context: dict[str, Any]
    tenant_context: dict[str, Any]
    global_config: dict[str, Any]

    # ── Callback ──
    callback_url: str

    # ── Intent routing ──
    available_manifests: list[dict[str, Any]] | None
    resolved_manifest_id: str | None

    # ── Node outputs (keyed by node_id) ──
    node_outputs: dict[str, Any]

    # ── Progress tracking ──
    # Matches AgentProgress TS type:
    #   {status: "pending"|"running"|"done"|"failed",
    #    output?: dict, started_at?: str, completed_at?: str}
    progress: dict[str, dict[str, Any]]

    # ── Final result ──
    result_data: dict[str, Any] | None

    # ── Error tracking ──
    error: str | None

    # ── Cancel flag ──
    cancelled: bool
