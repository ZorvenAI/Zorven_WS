"""Tests for OdooRPCClient — maximise coverage of app/services/odoo_rpc_client.py.

Covers:
  - _translate_fault (AccessDenied, AccessError, MissingError, ValidationError, generic)
  - authenticate success, failure (False), connection error, Fault
  - execute_kw: uid None, Fault, retry on connection error, exhaust retries
  - Convenience methods: search_read (with order), search_count, create, write,
    unlink, fields_get
"""

import xmlrpc.client
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.errors import (
    OdooAccessError,
    OdooAuthenticationError,
    OdooConnectionError,
    OdooMCPError,
    OdooNotFoundError,
    OdooValidationError,
)
from app.services.odoo_rpc_client import OdooRPCClient, _translate_fault


@pytest.fixture
def rpc_client() -> OdooRPCClient:
    """Return an unauthenticated RPC client with test credentials."""
    return OdooRPCClient(
        url="http://odoo.test:8069",
        db="test_db",
        username="admin",
        password="admin",
    )


@pytest.fixture
def authed_client(rpc_client: OdooRPCClient) -> OdooRPCClient:
    """Return an RPC client with uid already set (skips auth call)."""
    rpc_client.uid = 2
    return rpc_client


# ── _translate_fault ───────────────────────────────────────────────


class TestTranslateFault:
    """Map XML-RPC Faults to specific OdooMCPError subclasses."""

    def test_access_denied_lowercase(self):
        fault = xmlrpc.client.Fault(2, "AccessDenied: invalid token")
        err = _translate_fault(fault)
        assert isinstance(err, OdooAuthenticationError)
        assert "AccessDenied" in err.message

    def test_access_denied_with_spaces(self):
        fault = xmlrpc.client.Fault(2, "Access Denied for user admin")
        err = _translate_fault(fault)
        assert isinstance(err, OdooAuthenticationError)

    def test_access_error_lowercase(self):
        fault = xmlrpc.client.Fault(1, "AccessError: you do not have access")
        err = _translate_fault(fault)
        assert isinstance(err, OdooAccessError)

    def test_access_error_with_spaces(self):
        fault = xmlrpc.client.Fault(1, "Access Error: insufficient rights")
        err = _translate_fault(fault)
        assert isinstance(err, OdooAccessError)

    def test_missing_error_lowercase(self):
        fault = xmlrpc.client.Fault(1, "MissingError: record does not exist")
        err = _translate_fault(fault)
        assert isinstance(err, OdooNotFoundError)

    def test_missing_error_with_spaces(self):
        fault = xmlrpc.client.Fault(1, "Missing Error: no such record")
        err = _translate_fault(fault)
        assert isinstance(err, OdooNotFoundError)

    def test_validation_error_lowercase(self):
        fault = xmlrpc.client.Fault(1, "ValidationError: required field missing")
        err = _translate_fault(fault)
        assert isinstance(err, OdooValidationError)

    def test_validation_error_with_spaces(self):
        fault = xmlrpc.client.Fault(1, "Validation Error: invalid data")
        err = _translate_fault(fault)
        assert isinstance(err, OdooValidationError)

    def test_generic_fault(self):
        fault = xmlrpc.client.Fault(42, "Some other error")
        err = _translate_fault(fault)
        assert isinstance(err, OdooMCPError)
        assert not isinstance(err, OdooAuthenticationError)
        assert not isinstance(err, OdooAccessError)
        assert not isinstance(err, OdooNotFoundError)
        assert not isinstance(err, OdooValidationError)
        assert "XML-RPC fault 42" in err.message

    def test_empty_fault_string(self):
        fault = xmlrpc.client.Fault(0, "")
        err = _translate_fault(fault)
        assert isinstance(err, OdooMCPError)
        assert "XML-RPC fault 0" in err.message

    def test_none_fault_string(self):
        """faultString can be None in edge cases."""
        fault = xmlrpc.client.Fault(0, None)
        err = _translate_fault(fault)
        assert isinstance(err, OdooMCPError)


# ── Authenticate ───────────────────────────────────────────────────


class TestAuthenticate:
    async def test_authenticate_success(self, rpc_client):
        """authenticate() stores uid and returns it on success."""
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = 2
            uid = await rpc_client.authenticate()

        assert uid == 2
        assert rpc_client.uid == 2
        mock_thread.assert_awaited_once()

    async def test_authenticate_failure(self, rpc_client):
        """authenticate() raises OdooAuthenticationError when Odoo
        returns False (invalid credentials)."""
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = False

            with pytest.raises(OdooAuthenticationError):
                await rpc_client.authenticate()

        assert rpc_client.uid is None

    async def test_authenticate_connection_refused(self, rpc_client):
        """authenticate() raises OdooConnectionError on
        ConnectionRefusedError."""
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.side_effect = ConnectionRefusedError("Connection refused")

            with pytest.raises(OdooConnectionError, match="Cannot reach Odoo"):
                await rpc_client.authenticate()

    async def test_authenticate_os_error(self, rpc_client):
        """authenticate() raises OdooConnectionError on OSError."""
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.side_effect = OSError("Network unreachable")

            with pytest.raises(OdooConnectionError):
                await rpc_client.authenticate()

    async def test_authenticate_protocol_error(self, rpc_client):
        """authenticate() raises OdooConnectionError on
        xmlrpc.client.ProtocolError."""
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.side_effect = xmlrpc.client.ProtocolError(
                "http://odoo:8069", 500, "Internal Error", {}
            )

            with pytest.raises(OdooConnectionError):
                await rpc_client.authenticate()

    async def test_authenticate_fault(self, rpc_client):
        """authenticate() translates Fault to the appropriate
        OdooMCPError."""
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.side_effect = xmlrpc.client.Fault(
                2, "AccessDenied: bad credentials"
            )

            with pytest.raises(OdooAuthenticationError):
                await rpc_client.authenticate()

    async def test_authenticate_returns_false_zero(self, rpc_client):
        """authenticate() raises OdooAuthenticationError when Odoo
        returns 0 (falsy uid)."""
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = 0

            with pytest.raises(OdooAuthenticationError):
                await rpc_client.authenticate()


# ── execute_kw ─────────────────────────────────────────────────────


class TestExecuteKw:
    async def test_execute_kw_uid_none(self, rpc_client):
        """execute_kw raises OdooAuthenticationError when uid is None."""
        assert rpc_client.uid is None
        with pytest.raises(OdooAuthenticationError, match="not authenticated"):
            await rpc_client.execute_kw("res.partner", "search_read", [[]])

    async def test_execute_kw_fault(self, authed_client):
        """execute_kw translates Fault immediately (no retry)."""
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.side_effect = xmlrpc.client.Fault(1, "AccessError: denied")

            with pytest.raises(OdooAccessError):
                await authed_client.execute_kw("res.partner", "search_read", [[]])

        # Should be called only once — Faults are not retried
        assert mock_thread.await_count == 1

    async def test_execute_kw_success(self, authed_client):
        """execute_kw returns result on success."""
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = [{"id": 1, "name": "Partner"}]
            result = await authed_client.execute_kw("res.partner", "search_read", [[]])

        assert result == [{"id": 1, "name": "Partner"}]

    async def test_execute_kw_with_kwargs(self, authed_client):
        """execute_kw passes kwargs dict to the RPC call."""
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = []
            await authed_client.execute_kw(
                "res.partner",
                "search_read",
                [[]],
                {"fields": ["name"], "limit": 5},
            )

        mock_thread.assert_awaited_once()


class TestRetryBehavior:
    async def test_retry_on_connection_error(self, authed_client):
        """execute_kw retries on transient ConnectionRefusedError
        and succeeds on a later attempt."""
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.side_effect = [
                ConnectionRefusedError("refused"),
                [{"id": 1}],
            ]
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await authed_client.execute_kw(
                    "res.partner", "search_read", [[]]
                )

        assert result == [{"id": 1}]
        assert mock_thread.await_count == 2

    async def test_retry_on_os_error(self, authed_client):
        """execute_kw retries on OSError."""
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.side_effect = [
                OSError("Network unreachable"),
                [{"id": 1}],
            ]
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await authed_client.execute_kw(
                    "res.partner", "search_read", [[]]
                )

        assert result == [{"id": 1}]

    async def test_retry_on_protocol_error(self, authed_client):
        """execute_kw retries on ProtocolError."""
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.side_effect = [
                xmlrpc.client.ProtocolError("http://odoo:8069", 503, "Unavailable", {}),
                [{"id": 1}],
            ]
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await authed_client.execute_kw(
                    "res.partner", "search_read", [[]]
                )

        assert result == [{"id": 1}]

    async def test_raises_odoo_connection_error_after_retries(self, authed_client):
        """execute_kw raises OdooConnectionError after exhausting
        all retry attempts."""
        authed_client._retry_attempts = 3

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.side_effect = ConnectionRefusedError("refused")
            with patch("asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(OdooConnectionError, match="3 attempts"):
                    await authed_client.execute_kw("res.partner", "search_read", [[]])

        assert mock_thread.await_count == 3

    async def test_exponential_backoff_delays(self, authed_client):
        """Verify that retry uses exponential backoff."""
        authed_client._retry_attempts = 3
        authed_client._retry_backoff = 1.0

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.side_effect = ConnectionRefusedError("refused")
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                with pytest.raises(OdooConnectionError):
                    await authed_client.execute_kw("res.partner", "search_read", [[]])

        # Attempts: 1 (sleep 1.0), 2 (sleep 2.0), 3 (no sleep — exhausted)
        assert mock_sleep.await_count == 2
        delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert delays[0] == 1.0  # 1.0 * 2^0
        assert delays[1] == 2.0  # 1.0 * 2^1


# ── Convenience Methods ───────────────────────────────────────────


class TestSearchRead:
    async def test_search_read_returns_records(self, authed_client):
        """search_read() delegates to execute_kw and returns a list."""
        records = [
            {"id": 1, "name": "Order 1"},
            {"id": 2, "name": "Order 2"},
        ]
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = records
            result = await authed_client.search_read(
                "sale.order",
                [["state", "=", "sale"]],
                fields=["name"],
                limit=10,
            )

        assert result == records
        assert len(result) == 2

    async def test_search_read_with_order(self, authed_client):
        """search_read() passes the order parameter when provided."""
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = [{"id": 1, "name": "A"}]
            result = await authed_client.search_read(
                "res.partner",
                [[]],
                fields=["name"],
                order="name asc",
            )

        assert result == [{"id": 1, "name": "A"}]
        # Verify execute_kw was called (via to_thread)
        mock_thread.assert_awaited_once()

    async def test_search_read_with_offset(self, authed_client):
        """search_read() passes offset parameter."""
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = []
            await authed_client.search_read(
                "res.partner",
                [[]],
                offset=20,
                limit=10,
            )

        mock_thread.assert_awaited_once()

    async def test_search_read_without_fields(self, authed_client):
        """search_read() works without specifying fields."""
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = [{"id": 1}]
            result = await authed_client.search_read(
                "res.partner",
                [[]],
            )

        assert result == [{"id": 1}]


class TestSearchCount:
    async def test_search_count(self, authed_client):
        """search_count() returns an integer count."""
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = 42
            result = await authed_client.search_count(
                "res.partner", [["active", "=", True]]
            )

        assert result == 42
        assert isinstance(result, int)


class TestCreate:
    async def test_create_returns_id(self, authed_client):
        """create() returns the integer id of the new record."""
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = 42
            record_id = await authed_client.create(
                "res.partner", {"name": "Test Partner"}
            )

        assert record_id == 42
        assert isinstance(record_id, int)


class TestWrite:
    async def test_write_returns_true(self, authed_client):
        """write() returns True on successful update."""
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = True
            result = await authed_client.write("res.partner", [42], {"name": "Updated"})

        assert result is True


class TestUnlink:
    async def test_unlink_returns_true(self, authed_client):
        """unlink() returns True on successful deletion."""
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = True
            result = await authed_client.unlink("res.partner", [42])

        assert result is True


class TestFieldsGet:
    async def test_fields_get_returns_schema(self, authed_client):
        """fields_get() returns field metadata dict."""
        schema = {
            "name": {
                "string": "Name",
                "type": "char",
                "required": True,
            },
            "email": {
                "string": "Email",
                "type": "char",
                "required": False,
            },
        }
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = schema
            result = await authed_client.fields_get("res.partner")

        assert "name" in result
        assert result["name"]["type"] == "char"

    async def test_fields_get_custom_attributes(self, authed_client):
        """fields_get() passes custom attributes list."""
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = {"name": {"type": "char"}}
            result = await authed_client.fields_get("res.partner", attributes=["type"])

        assert "name" in result
        mock_thread.assert_awaited_once()
