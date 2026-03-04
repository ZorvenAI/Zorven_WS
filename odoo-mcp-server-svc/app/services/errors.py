"""Exception hierarchy for Odoo MCP Server.

All service-layer exceptions inherit from OdooMCPError so callers
can catch the base class for generic error handling while still
distinguishing specific failure modes (connection, auth, RBAC, etc.).
"""


class OdooMCPError(Exception):
    """Base exception for all Odoo MCP Server errors."""

    def __init__(self, message: str = "An Odoo MCP error occurred") -> None:
        self.message = message
        super().__init__(self.message)


class OdooConnectionError(OdooMCPError):
    """Cannot connect to the Odoo instance (network / DNS / port)."""

    def __init__(self, message: str = "Cannot connect to Odoo instance") -> None:
        super().__init__(message)


class OdooAuthenticationError(OdooMCPError):
    """Invalid credentials — Odoo returned False for authenticate()."""

    def __init__(self, message: str = "Invalid Odoo credentials") -> None:
        super().__init__(message)


class OdooAccessError(OdooMCPError):
    """Insufficient permissions on the Odoo side (ir.rule / ACL denial)."""

    def __init__(self, message: str = "Insufficient permissions in Odoo") -> None:
        super().__init__(message)


class OdooValidationError(OdooMCPError):
    """Invalid data or parameters sent to Odoo."""

    def __init__(
        self, message: str = "Invalid data or parameters for Odoo operation"
    ) -> None:
        super().__init__(message)


class OdooNotFoundError(OdooMCPError):
    """Requested record does not exist in Odoo."""

    def __init__(self, message: str = "Record not found in Odoo") -> None:
        super().__init__(message)


class TenantNotFoundError(OdooMCPError):
    """Tenant configuration not found in the registry."""

    def __init__(self, message: str = "Tenant configuration not found") -> None:
        super().__init__(message)


class RBACDeniedError(OdooMCPError):
    """RBAC check failed — the caller lacks the required permission."""

    def __init__(
        self,
        message: str = "RBAC permission denied",
        *,
        tool_name: str = "",
        required_permission: str = "",
    ) -> None:
        self.tool_name = tool_name
        self.required_permission = required_permission
        super().__init__(message)
