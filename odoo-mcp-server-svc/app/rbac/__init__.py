"""RBAC subsystem for Odoo MCP Server."""

from app.rbac.engine import RBACDeniedError, RBACEngine
from app.rbac.evaluator import PolicyEvaluator
from app.rbac.loader import RoleLoadError, load_role_definitions
from app.rbac.models import (
    Permission,
    PolicyDecision,
    PolicyResult,
    RoleDefinition,
)

__all__ = [
    "load_role_definitions",
    "PolicyEvaluator",
    "RBACEngine",
    "RBACDeniedError",
    "RoleLoadError",
    "Permission",
    "PolicyDecision",
    "PolicyResult",
    "RoleDefinition",
]
