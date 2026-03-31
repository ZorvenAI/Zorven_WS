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

    async def __call__(self, state: AgentState) -> dict:
        tenant_ctx = state.get("tenant_context", {})
        tenant_id = (
            tenant_ctx.get("tenant_id", "") if isinstance(tenant_ctx, dict) else ""
        )

        input_context = dict(state.get("input_context", {}))
        job_id = state.get("job_id", "")
        if job_id:
            input_context["job_id"] = job_id

        payload = {
            "input_prompt": state.get("input_prompt", ""),
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
        # job executor can accumulate it for the final callback.
        if isinstance(result, dict) and "result_data" in result:
            update["result_data"] = result["result_data"]

        return update
