"""Tests for brand_automator.tenant_utils."""

from unittest.mock import patch

from brand_automator.tenant_utils import parse_tenant_pk, ensure_public_db_connection


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


class TestEnsurePublicDbConnection:
    """ensure_public_db_connection resets the DB connection for workers."""

    @patch("django.db.connection")
    def test_close_and_set_public_by_default(self, mock_conn):
        """Default (close_existing=True) closes then sets public."""
        ensure_public_db_connection()
        mock_conn.close.assert_called_once()
        mock_conn.set_schema_to_public.assert_called_once()

    @patch("django.db.connection")
    def test_no_close_when_close_existing_false(self, mock_conn):
        """close_existing=False skips close but still sets public."""
        ensure_public_db_connection(close_existing=False)
        mock_conn.close.assert_not_called()
        mock_conn.set_schema_to_public.assert_called_once()

    @patch("django.db.connection")
    def test_close_called_before_set_schema(self, mock_conn):
        """close() must be called before set_schema_to_public()."""
        call_order = []
        mock_conn.close.side_effect = lambda: call_order.append("close")
        mock_conn.set_schema_to_public.side_effect = lambda: call_order.append(
            "set_schema"
        )
        ensure_public_db_connection()
        assert call_order == ["close", "set_schema"]

    @patch("django.db.connection")
    def test_idempotent(self, mock_conn):
        """Calling twice should work without error."""
        ensure_public_db_connection()
        ensure_public_db_connection()
        assert mock_conn.close.call_count == 2
        assert mock_conn.set_schema_to_public.call_count == 2
