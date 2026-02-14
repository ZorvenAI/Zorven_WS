"""Tests for brand_automator.tenant_utils."""

from brand_automator.tenant_utils import parse_tenant_pk


class TestParseTenantPk:
    """parse_tenant_pk converts string tenant ids to integer PKs."""

    def test_valid_integer_string(self):
        assert parse_tenant_pk("42") == 42

    def test_valid_one(self):
        assert parse_tenant_pk("1") == 1

    def test_empty_string_returns_none(self):
        assert parse_tenant_pk("") is None

    def test_none_returns_none(self):
        assert parse_tenant_pk(None) is None

    def test_public_returns_none(self):
        assert parse_tenant_pk("public") is None

    def test_non_numeric_returns_none(self):
        assert parse_tenant_pk("abc") is None

    def test_float_string_returns_none(self):
        assert parse_tenant_pk("3.14") is None

    def test_negative_is_allowed(self):
        """Negative PKs are technically valid integers."""
        assert parse_tenant_pk("-1") == -1

    def test_zero(self):
        assert parse_tenant_pk("0") == 0

    def test_whitespace_only_returns_none(self):
        """Empty-ish strings are falsy."""
        # " " is truthy, so it hits int() and fails → None
        assert parse_tenant_pk(" ") is None
