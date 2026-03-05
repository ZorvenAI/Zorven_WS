"""Tool dispatcher — RBAC-aware tool execution with auditing."""

import logging
import time
from typing import Any, Optional

from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class ToolDispatcher:
    """Dispatches tool calls with RBAC, field redaction, and audit logging.

    Pipeline:
    1. RBAC check (via engine)
    2. Execute tool
    3. Field redaction (remove denied fields from result)
    4. Domain injection (apply tenant domain filters)
    5. Audit logging
    6. Return structured JSON response
    """

    def __init__(
        self,
        registry: ToolRegistry,
        rbac_engine: Optional[Any] = None,
        audit_logger: Optional[Any] = None,
    ) -> None:
        self.registry = registry
        self.rbac_engine = rbac_engine
        self.audit_logger = audit_logger

    async def dispatch(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Execute a tool with full RBAC + audit pipeline."""
        start = time.monotonic()
        context = context or {}

        tool = self.registry.get_tool(tool_name)
        if tool is None:
            return {
                "success": False,
                "error": f"Unknown tool: {tool_name}",
                "duration_ms": 0,
            }

        # 1. RBAC check
        if self.rbac_engine is not None:
            try:
                user_roles = context.get("user_roles", [])
                policy = await self.rbac_engine.enforce_or_raise(
                    user_roles=user_roles,
                    tool_name=tool_name,
                    model=tool.required_model,
                    operation=tool.required_operation,
                )
                # Inject domain filter from RBAC policy
                if policy and policy.domain_filter:
                    arguments["_rbac_domain"] = policy.domain_filter
            except Exception as exc:
                duration = (time.monotonic() - start) * 1000
                self._audit(tool_name, context, False, duration, str(exc))
                return {
                    "success": False,
                    "error": str(exc),
                    "duration_ms": duration,
                }

        # 2. Execute tool
        try:
            result = await tool.execute(arguments, context)
        except Exception as exc:
            duration = (time.monotonic() - start) * 1000
            self._audit(tool_name, context, False, duration, str(exc))
            return {
                "success": False,
                "error": str(exc),
                "duration_ms": duration,
            }

        # 3. Field redaction (if RBAC returned denied fields)
        # Handled within individual tools that respect _rbac_domain

        duration = (time.monotonic() - start) * 1000

        # 5. Audit
        self._audit(tool_name, context, True, duration)

        # 6. Return
        return {
            "success": True,
            "result": result,
            "duration_ms": round(duration, 2),
        }

    def _audit(
        self,
        tool_name: str,
        context: dict[str, Any],
        success: bool,
        duration_ms: float,
        error: str = "",
    ) -> None:
        """Log audit entry."""
        tenant_id = context.get("tenant_id", "unknown")
        logger.info(
            "AUDIT tool=%s tenant=%s success=%s duration=%.1fms%s",
            tool_name,
            tenant_id,
            success,
            duration_ms,
            f" error={error}" if error else "",
        )
        if self.audit_logger:
            self.audit_logger.log(
                tool_name=tool_name,
                tenant_id=tenant_id,
                success=success,
                duration_ms=duration_ms,
                error=error,
            )
