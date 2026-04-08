"""
ExternalWrapper — Generic HTTP handler for remote agent services.

Calls an external microservice (e.g., discovery-agent-svc) via HTTP POST,
passing the current pipeline state and propagating X-Tenant-ID.

Falls back to stub data when the external service is unreachable,
so pipelines can be tested before agent services are deployed.
"""

import logging
from typing import Any

import httpx

from app.core.config import settings
from app.nodes.base import BaseNode
from app.state.schema import AgentState

logger = logging.getLogger(__name__)


class ExternalWrapper(BaseNode):
    """HTTP wrapper for external agent service calls."""

    def __init__(self, url: str, node_id: str, config: dict | None = None):
        super().__init__(config)
        self.url = url
        self.node_id = node_id

    def _apply_brand_context_preamble(self, input_prompt: str, tenant_ctx: Any) -> str:
        """
        Guarantee the BRAND CONTEXT preamble is present on the prompt sent
        to the downstream agent, even if an upstream node rewrote
        ``state["input_prompt"]``.

        Chooses between the full and compact preamble variants based on
        the node's manifest config key ``brand_context_mode``:

          - ``"full"`` (default): re-apply the full preamble if missing.
          - ``"compact"``: re-apply the compact preamble if the full one
            is missing. Drops vision/mission/values/checklist for
            token-sensitive nodes.
          - ``"off"``: skip re-application entirely. Use sparingly —
            only for nodes that genuinely have no brand reasoning (e.g.
            raw storage/dispatch shims).

        Idempotent: if the prompt already starts with a BRAND CONTEXT
        block, returns it unchanged regardless of mode.
        """
        if not isinstance(tenant_ctx, dict):
            return input_prompt

        mode = (self.config or {}).get("brand_context_mode", "full")
        if mode == "off":
            return input_prompt

        brand_context_headers = (
            "BRAND CONTEXT",
            "# BRAND CONTEXT",
            "## BRAND CONTEXT",
            "### BRAND CONTEXT",
        )
        stripped_input_prompt = input_prompt.lstrip() if input_prompt else ""
        if stripped_input_prompt.startswith(brand_context_headers):
            return input_prompt

        full_preamble = tenant_ctx.get("brand_context_preamble") or ""
        compact_preamble = tenant_ctx.get("brand_context_preamble_compact") or ""

        if mode == "compact":
            # Fall back to full preamble if compact variant is missing.
            preamble = compact_preamble or full_preamble
        else:
            preamble = full_preamble

        if not preamble:
            return input_prompt

        logger.info(
            "Re-applying brand_context preamble (mode=%s) on node %s — "
            "upstream prompt was missing the guardrail.",
            mode,
            self.node_id,
        )
        return preamble + (input_prompt or "")

    async def __call__(self, state: AgentState) -> dict:
        tenant_ctx = state.get("tenant_context", {}) or {}
        tenant_id = (
            tenant_ctx.get("tenant_id", "") if isinstance(tenant_ctx, dict) else ""
        )

        input_context = dict(state.get("input_context", {}))
        job_id = state.get("job_id", "")
        if job_id:
            input_context["job_id"] = job_id

        input_prompt = self._apply_brand_context_preamble(
            state.get("input_prompt", ""),
            tenant_ctx,
        )

        payload = {
            "input_prompt": input_prompt,
            "input_context": input_context,
            "tenant_context": tenant_ctx,
            "config": self.config,
            "previous_outputs": state.get("node_outputs", {}),
        }

        logger.info(
            "Calling external service: node=%s url=%s",
            self.node_id,
            self.url,
        )
        try:
            async with httpx.AsyncClient(timeout=settings.AGENT_TIMEOUT) as client:
                response = await client.post(
                    self.url,
                    json=payload,
                    headers={
                        "X-Tenant-ID": str(tenant_id),
                        "X-Service-Token": settings.SERVICE_TOKEN,
                    },
                )
                logger.info(
                    "External service response: node=%s status=%d",
                    self.node_id,
                    response.status_code,
                )
                response.raise_for_status()
                result = response.json()

        except httpx.HTTPError as exc:
            logger.error(
                "External service %s unreachable for node %s: %s (type=%s)",
                self.url,
                self.node_id,
                str(exc),
                type(exc).__name__,
            )
            error_detail = f"{type(exc).__name__}: {exc}"
            result = {
                "error": True,
                "status": "service_unavailable",
                "message": (
                    f"The {self.node_id} service is currently unavailable. "
                    f"Could not connect to {self.url}. "
                    f"Error: {error_detail}"
                ),
                "findings": [
                    f"The {self.node_id} service could not be reached at "
                    f"{self.url}. Error: {error_detail}"
                ],
                "recommendations": [
                    f"The {self.node_id} service may be down or misconfigured. "
                    f"Please try again later or contact support."
                ],
            }

        node_outputs = dict(state.get("node_outputs", {}))
        node_outputs[self.node_id] = result

        update: dict[str, Any] = {"node_outputs": node_outputs}

        # Propagate result_data from external service responses so the
        # job executor can accumulate it across every node in the pipeline.
        #
        # Two shapes are supported:
        #   1. The agent explicitly wraps its payload in a ``result_data``
        #      key — we merge that dict as-is into accumulated result_data.
        #   2. The agent returns its payload flat (CAA/CGA/APA do this) —
        #      we namespace it under ``result_data["node_payloads"][node_id]``
        #      so downstream nodes cannot overwrite earlier agents' outputs
        #      and so the propagated data does not collide with ManagerNode's
        #      top-level keys (summary, findings, node_results, etc.).
        #
        # Without this, the final pipeline result would only contain the
        # last agent's output (e.g. ad-publishing) and earlier agents'
        # outputs (campaign architecture, creative generation) would be
        # dropped.
        if isinstance(result, dict) and not self._is_error_payload(result):
            if "result_data" in result and isinstance(result["result_data"], dict):
                update["result_data"] = result["result_data"]
            else:
                update["result_data"] = {"node_payloads": {self.node_id: result}}

        return update

    @staticmethod
    def _is_error_payload(result: dict) -> bool:
        """
        Decide whether an agent response represents a failure and should
        NOT be propagated into accumulated result_data.

        Services use a few different shapes to signal failure:
          - ``error: True`` (our stub fallback when the service is down).
          - ``status: "failed" | "error"`` (e.g. ad-publishing-agent-svc).
          - A non-empty ``errors`` list at the top level.
        """
        if result.get("error"):
            return True
        status = result.get("status")
        if isinstance(status, str) and status.lower() in {"failed", "error"}:
            return True
        errors = result.get("errors")
        if isinstance(errors, list) and errors:
            return True
        return False
