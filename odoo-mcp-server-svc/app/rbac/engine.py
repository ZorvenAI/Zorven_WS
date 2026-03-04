"""RBAC engine — top-level access control wrapper.

Supports three enforcement modes:
- enforcing: deny raises RBACDeniedError
- permissive: deny logs warning but allows
- disabled: skips evaluation entirely
"""

import logging
from typing import Optional

from app.rbac.evaluator import PolicyEvaluator
from app.rbac.models import PolicyDecision, PolicyResult

logger = logging.getLogger(__name__)


class RBACDeniedError(Exception):
    """Raised when access is denied in enforcing mode."""

    def __init__(self, result: PolicyResult) -> None:
        self.result = result
        super().__init__(
            f"RBAC denied: {result.reason} " f"(decision={result.decision.value})"
        )


class RBACEngine:
    """Top-level RBAC engine wrapping PolicyEvaluator.

    Args:
        evaluator: The policy evaluator instance.
        enforcement: One of "enforcing", "permissive", "disabled".
    """

    VALID_MODES = ("enforcing", "permissive", "disabled")

    def __init__(
        self,
        evaluator: PolicyEvaluator,
        enforcement: str = "enforcing",
    ) -> None:
        if enforcement not in self.VALID_MODES:
            raise ValueError(
                f"Invalid enforcement mode '{enforcement}'. "
                f"Must be one of: {self.VALID_MODES}"
            )
        self._evaluator = evaluator
        self._enforcement = enforcement

    @property
    def enforcement(self) -> str:
        """Current enforcement mode."""
        return self._enforcement

    async def check_access(
        self,
        user_roles: list[str],
        tool_name: str,
        model: str,
        operation: str,
        fields: Optional[list[str]] = None,
    ) -> PolicyResult:
        """Evaluate access without raising exceptions.

        In disabled mode, returns ALLOW without evaluation.
        Otherwise delegates to the evaluator.
        """
        if self._enforcement == "disabled":
            return PolicyResult(
                decision=PolicyDecision.ALLOW,
                reason="RBAC enforcement disabled",
            )

        return await self._evaluator.evaluate(
            user_roles=user_roles,
            tool_name=tool_name,
            model=model,
            operation=operation,
            fields=fields,
        )

    async def enforce_or_raise(
        self,
        user_roles: list[str],
        tool_name: str,
        model: str,
        operation: str,
        fields: Optional[list[str]] = None,
    ) -> PolicyResult:
        """Evaluate access and enforce the decision.

        - enforcing: raises RBACDeniedError on DENY/DENY_FIELD
        - permissive: logs warning on deny but returns the result
        - disabled: returns ALLOW without evaluation

        Returns:
            PolicyResult — always returned (even on deny in permissive mode).

        Raises:
            RBACDeniedError: In enforcing mode when access is denied.
        """
        result = await self.check_access(
            user_roles=user_roles,
            tool_name=tool_name,
            model=model,
            operation=operation,
            fields=fields,
        )

        if result.decision in (
            PolicyDecision.DENY,
            PolicyDecision.DENY_FIELD,
        ):
            if self._enforcement == "enforcing":
                logger.warning(
                    "RBAC DENIED (enforcing): roles=%s tool=%s "
                    "model=%s op=%s reason=%s",
                    user_roles,
                    tool_name,
                    model,
                    operation,
                    result.reason,
                )
                raise RBACDeniedError(result)

            if self._enforcement == "permissive":
                logger.warning(
                    "RBAC DENIED (permissive — allowing): roles=%s tool=%s "
                    "model=%s op=%s reason=%s",
                    user_roles,
                    tool_name,
                    model,
                    operation,
                    result.reason,
                )

        return result
