"""Tests for error hierarchy — covers app/services/errors.py.

Focuses on:
  - Default messages for all error classes
  - Custom messages
  - RBACDeniedError with tool_name and required_permission kwargs
  - str() representation
  - Inheritance chain
"""

from app.services.errors import (
    OdooAccessError,
    OdooAuthenticationError,
    OdooConnectionError,
    OdooMCPError,
    OdooNotFoundError,
    OdooValidationError,
    RBACDeniedError,
    TenantNotFoundError,
)


class TestOdooMCPError:
    """Base error class."""

    def test_default_message(self):
        err = OdooMCPError()
        assert err.message == "An Odoo MCP error occurred"
        assert str(err) == "An Odoo MCP error occurred"

    def test_custom_message(self):
        err = OdooMCPError("custom error")
        assert err.message == "custom error"
        assert str(err) == "custom error"

    def test_isinstance_exception(self):
        assert isinstance(OdooMCPError(), Exception)


class TestOdooConnectionError:
    def test_default_message(self):
        err = OdooConnectionError()
        assert err.message == "Cannot connect to Odoo instance"
        assert str(err) == "Cannot connect to Odoo instance"

    def test_custom_message(self):
        err = OdooConnectionError("timeout at host:8069")
        assert err.message == "timeout at host:8069"

    def test_inherits_from_base(self):
        assert isinstance(OdooConnectionError(), OdooMCPError)


class TestOdooAuthenticationError:
    def test_default_message(self):
        err = OdooAuthenticationError()
        assert err.message == "Invalid Odoo credentials"
        assert str(err) == "Invalid Odoo credentials"

    def test_custom_message(self):
        err = OdooAuthenticationError("bad password")
        assert err.message == "bad password"

    def test_inherits_from_base(self):
        assert isinstance(OdooAuthenticationError(), OdooMCPError)


class TestOdooAccessError:
    def test_default_message(self):
        err = OdooAccessError()
        assert err.message == "Insufficient permissions in Odoo"
        assert str(err) == "Insufficient permissions in Odoo"

    def test_custom_message(self):
        err = OdooAccessError("ACL denied for model crm.lead")
        assert err.message == "ACL denied for model crm.lead"

    def test_inherits_from_base(self):
        assert isinstance(OdooAccessError(), OdooMCPError)


class TestOdooValidationError:
    def test_default_message(self):
        err = OdooValidationError()
        assert err.message == "Invalid data or parameters for Odoo operation"
        assert str(err) == "Invalid data or parameters for Odoo operation"

    def test_custom_message(self):
        err = OdooValidationError("missing required field 'name'")
        assert err.message == "missing required field 'name'"

    def test_inherits_from_base(self):
        assert isinstance(OdooValidationError(), OdooMCPError)


class TestOdooNotFoundError:
    def test_default_message(self):
        err = OdooNotFoundError()
        assert err.message == "Record not found in Odoo"
        assert str(err) == "Record not found in Odoo"

    def test_custom_message(self):
        err = OdooNotFoundError("res.partner(999) does not exist")
        assert err.message == "res.partner(999) does not exist"

    def test_inherits_from_base(self):
        assert isinstance(OdooNotFoundError(), OdooMCPError)


class TestTenantNotFoundError:
    def test_default_message(self):
        err = TenantNotFoundError()
        assert err.message == "Tenant configuration not found"
        assert str(err) == "Tenant configuration not found"

    def test_custom_message(self):
        err = TenantNotFoundError("tenant 'xyz' not in registry")
        assert err.message == "tenant 'xyz' not in registry"

    def test_inherits_from_base(self):
        assert isinstance(TenantNotFoundError(), OdooMCPError)


class TestRBACDeniedError:
    def test_default_message(self):
        err = RBACDeniedError()
        assert err.message == "RBAC permission denied"
        assert str(err) == "RBAC permission denied"
        assert err.tool_name == ""
        assert err.required_permission == ""

    def test_custom_message(self):
        err = RBACDeniedError("Not allowed")
        assert err.message == "Not allowed"

    def test_with_tool_name_and_permission(self):
        err = RBACDeniedError(
            tool_name="odoo_search",
            required_permission="read",
        )
        assert err.tool_name == "odoo_search"
        assert err.required_permission == "read"
        assert err.message == "RBAC permission denied"

    def test_with_all_params(self):
        err = RBACDeniedError(
            "Custom denial",
            tool_name="odoo_delete",
            required_permission="unlink",
        )
        assert err.message == "Custom denial"
        assert err.tool_name == "odoo_delete"
        assert err.required_permission == "unlink"

    def test_inherits_from_base(self):
        assert isinstance(RBACDeniedError(), OdooMCPError)


class TestAllErrorsWithDefaults:
    """Verify every error class works when instantiated with no args."""

    def test_all_instantiate_without_args(self):
        error_classes = [
            OdooMCPError,
            OdooConnectionError,
            OdooAuthenticationError,
            OdooAccessError,
            OdooValidationError,
            OdooNotFoundError,
            TenantNotFoundError,
            RBACDeniedError,
        ]
        for cls in error_classes:
            err = cls()
            assert err.message  # not empty
            assert str(err)  # has string representation
            assert isinstance(err, OdooMCPError)
            assert isinstance(err, Exception)
