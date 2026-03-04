"""Base tool abstract class for all Odoo MCP tools."""

from abc import ABC, abstractmethod
from typing import Any, Optional


class BaseTool(ABC):
    """Abstract base class for Odoo MCP tools.

    All domain tools inherit from this class and implement the execute method.
    """

    name: str = ""
    description: str = ""
    domain: str = ""  # e.g., "crm", "sales", "accounting"
    input_schema: dict[str, Any] = {}
    required_model: str = ""  # Odoo model, e.g., "crm.lead"
    required_operation: str = "read"  # read, create, write, unlink

    @abstractmethod
    async def execute(
        self,
        arguments: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Execute the tool with given arguments and context.

        Args:
            arguments: Tool-specific input parameters.
            context: Tenant context, RPC client, skill context, etc.

        Returns:
            Structured result dict.
        """
        ...

    def to_mcp_dict(self) -> dict[str, Any]:
        """Convert to MCP tool listing format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "domain": self.domain,
            "required_model": self.required_model,
            "required_operation": self.required_operation,
        }
