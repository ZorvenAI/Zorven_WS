"""RBAC role definition loader — reads YAML files from a directory."""

import logging
import os
from pathlib import Path
from typing import Any

import yaml

from app.rbac.models import Permission, RoleDefinition

logger = logging.getLogger(__name__)


class RoleLoadError(Exception):
    """Raised when role definitions cannot be loaded or validated."""


def _parse_role_file(file_path: Path) -> RoleDefinition:
    """Parse a single YAML file into a RoleDefinition."""
    with open(file_path, "r") as f:
        data: dict[str, Any] = yaml.safe_load(f)

    if not data or not isinstance(data, dict):
        raise RoleLoadError(f"Invalid role file (empty or not a mapping): {file_path}")

    name = data.get("name")
    if not name:
        raise RoleLoadError(f"Role file missing 'name' field: {file_path}")

    permissions_raw = data.get("permissions", [])
    permissions = [Permission(**p) for p in permissions_raw]

    return RoleDefinition(
        name=name,
        description=data.get("description", ""),
        inherits=data.get("inherits", []),
        permissions=permissions,
    )


def _validate_inheritance(roles: dict[str, RoleDefinition]) -> None:
    """Validate that inheritance chains have no cycles and all parents exist."""
    for role_name, role_def in roles.items():
        visited: set[str] = set()
        stack = list(role_def.inherits)

        while stack:
            parent_name = stack.pop()

            if parent_name == role_name:
                raise RoleLoadError(
                    f"Circular inheritance detected: "
                    f"'{role_name}' inherits from itself"
                )

            if parent_name in visited:
                continue

            if parent_name not in roles:
                raise RoleLoadError(
                    f"Role '{role_name}' inherits from unknown role " f"'{parent_name}'"
                )

            visited.add(parent_name)
            parent_def = roles[parent_name]
            stack.extend(parent_def.inherits)

        if role_name in visited:
            raise RoleLoadError(
                f"Circular inheritance detected involving role '{role_name}'"
            )


def load_role_definitions(roles_dir: str) -> dict[str, RoleDefinition]:
    """Load all YAML role definitions from a directory.

    Args:
        roles_dir: Path to directory containing .yaml role files.

    Returns:
        Dict mapping role name to RoleDefinition.

    Raises:
        RoleLoadError: If directory is missing, files are invalid,
            or inheritance chains are broken.
    """
    roles_path = Path(roles_dir)

    if not roles_path.exists():
        raise RoleLoadError(f"Roles directory does not exist: {roles_dir}")

    if not roles_path.is_dir():
        raise RoleLoadError(f"Roles path is not a directory: {roles_dir}")

    roles: dict[str, RoleDefinition] = {}
    yaml_files = sorted(roles_path.glob("*.yaml")) + sorted(roles_path.glob("*.yml"))

    if not yaml_files:
        logger.warning("No YAML role files found in %s", roles_dir)
        return roles

    for file_path in yaml_files:
        try:
            role_def = _parse_role_file(file_path)
        except (yaml.YAMLError, TypeError, ValueError) as exc:
            raise RoleLoadError(
                f"Failed to parse role file {file_path}: {exc}"
            ) from exc

        if role_def.name in roles:
            raise RoleLoadError(
                f"Duplicate role name '{role_def.name}' found in " f"{file_path}"
            )

        roles[role_def.name] = role_def
        logger.info("Loaded role: %s from %s", role_def.name, file_path.name)

    _validate_inheritance(roles)

    logger.info("Loaded %d role definitions from %s", len(roles), roles_dir)
    return roles
