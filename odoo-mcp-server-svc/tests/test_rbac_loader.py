"""Tests for RBAC role definition loader."""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from app.rbac.loader import RoleLoadError, load_role_definitions
from app.rbac.models import RoleDefinition

# ── Fixtures ──


@pytest.fixture
def roles_dir(tmp_path: Path) -> Path:
    """Create a temporary roles directory with valid YAML files."""
    # super_admin role
    super_admin = {
        "name": "super_admin",
        "description": "Full access",
        "inherits": [],
        "permissions": [
            {
                "tool": "*",
                "models": ["*"],
                "operations": ["read", "create", "write", "unlink"],
                "fields_allowed": [],
                "fields_denied": [],
                "domain_filter": [],
            }
        ],
    }
    (tmp_path / "super_admin.yaml").write_text(yaml.dump(super_admin))

    # tenant_owner role (inherits super_admin)
    tenant_owner = {
        "name": "tenant_owner",
        "description": "Tenant owner",
        "inherits": ["super_admin"],
        "permissions": [
            {
                "tool": "*",
                "models": ["*"],
                "operations": ["read", "create", "write", "unlink"],
                "fields_allowed": [],
                "fields_denied": [],
                "domain_filter": [["company_id", "=", "__tenant_company_id__"]],
            }
        ],
    }
    (tmp_path / "tenant_owner.yaml").write_text(yaml.dump(tenant_owner))

    # readonly role
    readonly = {
        "name": "readonly_viewer",
        "description": "Read only",
        "inherits": [],
        "permissions": [
            {
                "tool": "*",
                "models": ["*"],
                "operations": ["read"],
                "fields_allowed": [],
                "fields_denied": ["password"],
                "domain_filter": [],
            }
        ],
    }
    (tmp_path / "readonly_viewer.yaml").write_text(yaml.dump(readonly))

    return tmp_path


@pytest.fixture
def single_role_dir(tmp_path: Path) -> Path:
    """Directory with a single role file."""
    role = {
        "name": "sales_user",
        "description": "Sales user",
        "inherits": [],
        "permissions": [
            {
                "tool": "*",
                "models": ["crm.lead", "sale.order"],
                "operations": ["read", "create"],
            }
        ],
    }
    (tmp_path / "sales_user.yaml").write_text(yaml.dump(role))
    return tmp_path


# ── Load from directory tests ──


class TestLoadRoleDefinitions:
    """Test loading role definitions from YAML files."""

    def test_load_valid_roles(self, roles_dir: Path) -> None:
        """Load multiple valid role files."""
        roles = load_role_definitions(str(roles_dir))

        assert len(roles) == 3
        assert "super_admin" in roles
        assert "tenant_owner" in roles
        assert "readonly_viewer" in roles

    def test_loaded_role_structure(self, roles_dir: Path) -> None:
        """Verify loaded role has correct structure."""
        roles = load_role_definitions(str(roles_dir))
        admin = roles["super_admin"]

        assert isinstance(admin, RoleDefinition)
        assert admin.name == "super_admin"
        assert admin.description == "Full access"
        assert admin.inherits == []
        assert len(admin.permissions) == 1
        assert admin.permissions[0].tool == "*"
        assert admin.permissions[0].models == ["*"]
        assert "read" in admin.permissions[0].operations
        assert "unlink" in admin.permissions[0].operations

    def test_loaded_role_with_inheritance(self, roles_dir: Path) -> None:
        """Role with inherits field is preserved."""
        roles = load_role_definitions(str(roles_dir))
        owner = roles["tenant_owner"]

        assert owner.inherits == ["super_admin"]
        assert owner.permissions[0].domain_filter == [
            ["company_id", "=", "__tenant_company_id__"]
        ]

    def test_loaded_role_with_denied_fields(self, roles_dir: Path) -> None:
        """Role with denied fields is preserved."""
        roles = load_role_definitions(str(roles_dir))
        viewer = roles["readonly_viewer"]

        assert viewer.permissions[0].fields_denied == ["password"]

    def test_load_single_role(self, single_role_dir: Path) -> None:
        """Load a directory with a single role."""
        roles = load_role_definitions(str(single_role_dir))

        assert len(roles) == 1
        assert "sales_user" in roles
        assert roles["sales_user"].permissions[0].models == [
            "crm.lead",
            "sale.order",
        ]

    def test_load_yml_extension(self, tmp_path: Path) -> None:
        """Load files with .yml extension."""
        role = {
            "name": "test_role",
            "description": "Test",
            "permissions": [],
        }
        (tmp_path / "test_role.yml").write_text(yaml.dump(role))

        roles = load_role_definitions(str(tmp_path))
        assert "test_role" in roles

    def test_load_empty_directory(self, tmp_path: Path) -> None:
        """Empty directory returns empty dict."""
        roles = load_role_definitions(str(tmp_path))
        assert roles == {}

    def test_load_real_config_roles(self) -> None:
        """Load the actual config/roles directory."""
        roles_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "config",
            "roles",
        )
        if not os.path.exists(roles_dir):
            pytest.skip("config/roles directory not found")

        roles = load_role_definitions(roles_dir)
        assert len(roles) >= 1
        # Verify all roles have valid structure
        for name, role_def in roles.items():
            assert role_def.name == name
            assert isinstance(role_def.permissions, list)


# ── Validation tests ──


class TestValidation:
    """Test validation of role definitions."""

    def test_missing_directory(self) -> None:
        """Non-existent directory raises RoleLoadError."""
        with pytest.raises(RoleLoadError, match="does not exist"):
            load_role_definitions("/nonexistent/path/to/roles")

    def test_not_a_directory(self, tmp_path: Path) -> None:
        """Path to a file (not directory) raises RoleLoadError."""
        file_path = tmp_path / "not_a_dir.yaml"
        file_path.write_text("name: test")

        with pytest.raises(RoleLoadError, match="not a directory"):
            load_role_definitions(str(file_path))

    def test_duplicate_role_name(self, tmp_path: Path) -> None:
        """Duplicate role names across files raises RoleLoadError."""
        role = {"name": "duplicate_role", "permissions": []}
        (tmp_path / "role_a.yaml").write_text(yaml.dump(role))
        (tmp_path / "role_b.yaml").write_text(yaml.dump(role))

        with pytest.raises(RoleLoadError, match="Duplicate role name"):
            load_role_definitions(str(tmp_path))

    def test_missing_name_field(self, tmp_path: Path) -> None:
        """Role file without 'name' field raises RoleLoadError."""
        (tmp_path / "bad.yaml").write_text(yaml.dump({"description": "no name"}))

        with pytest.raises(RoleLoadError, match="missing 'name' field"):
            load_role_definitions(str(tmp_path))

    def test_empty_file(self, tmp_path: Path) -> None:
        """Empty YAML file raises RoleLoadError."""
        (tmp_path / "empty.yaml").write_text("")

        with pytest.raises(RoleLoadError, match="Invalid role file"):
            load_role_definitions(str(tmp_path))

    def test_invalid_yaml_syntax(self, tmp_path: Path) -> None:
        """Malformed YAML raises RoleLoadError."""
        (tmp_path / "bad.yaml").write_text("name: [invalid: yaml: {{")

        with pytest.raises(RoleLoadError, match="Failed to parse"):
            load_role_definitions(str(tmp_path))

    def test_circular_inheritance_self(self, tmp_path: Path) -> None:
        """Role inheriting from itself raises RoleLoadError."""
        role = {
            "name": "self_ref",
            "inherits": ["self_ref"],
            "permissions": [],
        }
        (tmp_path / "self_ref.yaml").write_text(yaml.dump(role))

        with pytest.raises(RoleLoadError, match="Circular inheritance"):
            load_role_definitions(str(tmp_path))

    def test_circular_inheritance_indirect(self, tmp_path: Path) -> None:
        """Indirect circular inheritance raises RoleLoadError."""
        role_a = {
            "name": "role_a",
            "inherits": ["role_b"],
            "permissions": [],
        }
        role_b = {
            "name": "role_b",
            "inherits": ["role_a"],
            "permissions": [],
        }
        (tmp_path / "role_a.yaml").write_text(yaml.dump(role_a))
        (tmp_path / "role_b.yaml").write_text(yaml.dump(role_b))

        with pytest.raises(RoleLoadError, match="Circular inheritance"):
            load_role_definitions(str(tmp_path))

    def test_unknown_parent_role(self, tmp_path: Path) -> None:
        """Inheriting from a non-existent role raises RoleLoadError."""
        role = {
            "name": "orphan",
            "inherits": ["nonexistent_parent"],
            "permissions": [],
        }
        (tmp_path / "orphan.yaml").write_text(yaml.dump(role))

        with pytest.raises(RoleLoadError, match="unknown role"):
            load_role_definitions(str(tmp_path))

    def test_valid_deep_inheritance(self, tmp_path: Path) -> None:
        """Three-level inheritance chain is valid."""
        base = {"name": "base", "inherits": [], "permissions": []}
        mid = {"name": "mid", "inherits": ["base"], "permissions": []}
        top = {"name": "top", "inherits": ["mid"], "permissions": []}

        (tmp_path / "base.yaml").write_text(yaml.dump(base))
        (tmp_path / "mid.yaml").write_text(yaml.dump(mid))
        (tmp_path / "top.yaml").write_text(yaml.dump(top))

        roles = load_role_definitions(str(tmp_path))
        assert len(roles) == 3
        assert roles["top"].inherits == ["mid"]
