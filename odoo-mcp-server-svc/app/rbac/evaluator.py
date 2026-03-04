"""RBAC policy evaluator — matches permissions against access requests."""

import fnmatch
import hashlib
import json
import logging
from typing import Any, Optional

from app.rbac.models import (
    Permission,
    PolicyDecision,
    PolicyResult,
    RoleDefinition,
)

logger = logging.getLogger(__name__)


class PolicyEvaluator:
    """Evaluates access requests against loaded role definitions.

    Three-phase pipeline:
    1. Flatten inheritance chain for all user roles
    2. Find matching permissions (tool pattern, model pattern, operation)
    3. Check field-level access, apply domain filters
    """

    def __init__(
        self,
        roles: dict[str, RoleDefinition],
        redis_manager: Optional[Any] = None,
    ) -> None:
        self._roles = roles
        self._redis = redis_manager

    # ── Public API ──

    async def evaluate(
        self,
        user_roles: list[str],
        tool_name: str,
        model: str,
        operation: str,
        fields: Optional[list[str]] = None,
    ) -> PolicyResult:
        """Evaluate whether the given roles grant access to the request.

        Args:
            user_roles: List of role names assigned to the user.
            tool_name: MCP tool being invoked (e.g. "search_read").
            model: Odoo model name (e.g. "sale.order").
            operation: CRUD operation — read, create, write, unlink.
            fields: Optional list of field names being accessed.

        Returns:
            PolicyResult with the decision and metadata.
        """
        # Check cache first
        cached = await self._get_cached(user_roles, tool_name, model, operation)
        if cached is not None:
            return cached

        # Phase 1: Flatten inheritance
        all_permissions = self._flatten_permissions(user_roles)

        if not all_permissions:
            result = PolicyResult(
                decision=PolicyDecision.DENY,
                reason=f"No permissions found for roles: {user_roles}",
            )
            await self._set_cached(user_roles, tool_name, model, operation, result)
            return result

        # Phase 2: Find matching permissions
        matching = self._find_matching(all_permissions, tool_name, model, operation)

        if not matching:
            result = PolicyResult(
                decision=PolicyDecision.DENY,
                reason=(
                    f"No permission matches tool={tool_name}, "
                    f"model={model}, operation={operation}"
                ),
            )
            await self._set_cached(user_roles, tool_name, model, operation, result)
            return result

        # Phase 3: Field-level checks and domain filters
        result = self._check_fields_and_domains(matching, fields or [])

        await self._set_cached(user_roles, tool_name, model, operation, result)
        return result

    # ── Phase 1: Flatten inheritance ──

    def _flatten_permissions(self, user_roles: list[str]) -> list[Permission]:
        """Collect all permissions from user roles and their ancestors."""
        visited: set[str] = set()
        permissions: list[Permission] = []

        def _collect(role_name: str) -> None:
            if role_name in visited:
                return
            visited.add(role_name)

            role_def = self._roles.get(role_name)
            if role_def is None:
                logger.warning("Unknown role referenced: %s", role_name)
                return

            # Collect parent permissions first (child can override)
            for parent in role_def.inherits:
                _collect(parent)

            permissions.extend(role_def.permissions)

        for role in user_roles:
            _collect(role)

        return permissions

    # ── Phase 2: Match permissions ──

    @staticmethod
    def _matches_pattern(pattern: str, value: str) -> bool:
        """Check if a value matches a glob-style pattern."""
        return fnmatch.fnmatch(value, pattern)

    def _find_matching(
        self,
        permissions: list[Permission],
        tool_name: str,
        model: str,
        operation: str,
    ) -> list[Permission]:
        """Filter permissions that match the request."""
        matching: list[Permission] = []

        for perm in permissions:
            # Check tool pattern
            if not self._matches_pattern(perm.tool, tool_name):
                continue

            # Check model patterns
            model_match = any(self._matches_pattern(m, model) for m in perm.models)
            if not model_match:
                continue

            # Check operation
            if operation not in perm.operations and "*" not in perm.operations:
                continue

            matching.append(perm)

        return matching

    # ── Phase 3: Field-level access + domain filters ──

    @staticmethod
    def _check_fields_and_domains(
        matching: list[Permission],
        fields: list[str],
    ) -> PolicyResult:
        """Check field access and collect domain filters from matches."""
        # Merge domain filters from all matching permissions
        merged_domains: list[Any] = []
        all_denied_fields: set[str] = set()
        has_field_restriction = False

        for perm in matching:
            if perm.domain_filter:
                merged_domains.extend(perm.domain_filter)

            if perm.fields_denied:
                all_denied_fields.update(perm.fields_denied)

            if perm.fields_allowed:
                has_field_restriction = True

        # Check requested fields against denied fields
        if fields and all_denied_fields:
            blocked = [f for f in fields if f in all_denied_fields]
            if blocked:
                return PolicyResult(
                    decision=PolicyDecision.DENY_FIELD,
                    reason=f"Fields denied: {blocked}",
                    denied_fields=blocked,
                    domain_filter=merged_domains,
                )

        # Check requested fields against allowed fields (if any restriction)
        if fields and has_field_restriction:
            # Collect all allowed fields from all matching permissions
            all_allowed: set[str] = set()
            for perm in matching:
                if perm.fields_allowed:
                    all_allowed.update(perm.fields_allowed)

            if all_allowed:
                not_allowed = [f for f in fields if f not in all_allowed]
                if not_allowed:
                    return PolicyResult(
                        decision=PolicyDecision.DENY_FIELD,
                        reason=f"Fields not in allowed list: {not_allowed}",
                        denied_fields=not_allowed,
                        domain_filter=merged_domains,
                    )

        return PolicyResult(
            decision=PolicyDecision.ALLOW,
            reason="Access granted",
            domain_filter=merged_domains,
        )

    # ── Caching helpers ──

    @staticmethod
    def _cache_key(
        user_roles: list[str],
        tool_name: str,
        model: str,
        operation: str,
    ) -> str:
        """Build a deterministic cache key."""
        roles_part = ",".join(sorted(user_roles))
        raw = f"{roles_part}|{tool_name}|{model}|{operation}"
        digest = hashlib.md5(raw.encode()).hexdigest()
        return f"odoo_mcp:rbac:eval:{digest}"

    async def _get_cached(
        self,
        user_roles: list[str],
        tool_name: str,
        model: str,
        operation: str,
    ) -> Optional[PolicyResult]:
        """Retrieve cached evaluation result."""
        if self._redis is None:
            return None
        try:
            key = self._cache_key(user_roles, tool_name, model, operation)
            data = await self._redis.get_cached_result(key)
            if data:
                return PolicyResult(**data)
        except Exception:
            logger.warning("Failed to read RBAC eval cache")
        return None

    async def _set_cached(
        self,
        user_roles: list[str],
        tool_name: str,
        model: str,
        operation: str,
        result: PolicyResult,
    ) -> None:
        """Store evaluation result in cache."""
        if self._redis is None:
            return
        try:
            key = self._cache_key(user_roles, tool_name, model, operation)
            await self._redis.set_cached_result(key, result.model_dump(mode="json"))
        except Exception:
            logger.warning("Failed to write RBAC eval cache")
