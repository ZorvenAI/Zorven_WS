"""Odoo XML-RPC client — async wrapper around xmlrpc.client.

Provides typed convenience methods for the Odoo external API
(/xmlrpc/2/common and /xmlrpc/2/object) with automatic retry,
exponential backoff, and translation of XML-RPC faults into
domain-specific OdooMCPError subclasses.
"""

import asyncio
import logging
import xmlrpc.client
from typing import Any

from app.core.config import settings
from app.services.errors import (
    OdooAccessError,
    OdooAuthenticationError,
    OdooConnectionError,
    OdooMCPError,
    OdooNotFoundError,
    OdooValidationError,
)

logger = logging.getLogger(__name__)


def _translate_fault(fault: xmlrpc.client.Fault) -> OdooMCPError:
    """Map an XML-RPC Fault to the most specific OdooMCPError subclass."""
    code = fault.faultCode
    msg = fault.faultString or ""

    # Odoo access-rights faults typically contain "AccessError" or
    # "AccessDenied" in the fault string.
    lower_msg = msg.lower()
    if "accessdenied" in lower_msg or "access denied" in lower_msg:
        return OdooAuthenticationError(msg)
    if "accesserror" in lower_msg or "access error" in lower_msg:
        return OdooAccessError(msg)
    if "missingerror" in lower_msg or "missing error" in lower_msg:
        return OdooNotFoundError(msg)
    if "validationerror" in lower_msg or "validation error" in lower_msg:
        return OdooValidationError(msg)

    # Fall back to base error with the original message
    return OdooMCPError(f"XML-RPC fault {code}: {msg}")


class OdooRPCClient:
    """Async Odoo XML-RPC client with retry and error translation."""

    def __init__(self, url: str, db: str, username: str, password: str) -> None:
        self.url = url.rstrip("/")
        self.db = db
        self.username = username
        self.password = password
        self.uid: int | None = None
        self._retry_attempts: int = settings.RPC_RETRY_ATTEMPTS
        self._retry_backoff: float = settings.RPC_RETRY_BACKOFF
        self._timeout: float = settings.RPC_TIMEOUT

    # ── Authentication ────────────────────────────────────────────

    async def authenticate(self) -> int:
        """Authenticate via /xmlrpc/2/common and return the user id.

        Raises OdooAuthenticationError when Odoo returns ``False``
        (invalid credentials) and OdooConnectionError on network errors.
        """
        common_url = f"{self.url}/xmlrpc/2/common"

        def _auth() -> Any:
            proxy = xmlrpc.client.ServerProxy(common_url, allow_none=True)
            return proxy.authenticate(self.db, self.username, self.password, {})

        try:
            uid = await asyncio.to_thread(_auth)
        except (
            ConnectionRefusedError,
            OSError,
            xmlrpc.client.ProtocolError,
        ) as exc:
            raise OdooConnectionError(
                f"Cannot reach Odoo at {self.url}: {exc}"
            ) from exc
        except xmlrpc.client.Fault as fault:
            raise _translate_fault(fault) from fault

        if not uid:
            raise OdooAuthenticationError(
                f"Authentication failed for user '{self.username}' "
                f"on database '{self.db}'"
            )

        self.uid = int(uid)
        logger.info(
            "Authenticated to Odoo %s (db=%s, uid=%d)",
            self.url,
            self.db,
            self.uid,
        )
        return self.uid

    # ── Core execute_kw with retry ────────────────────────────────

    async def execute_kw(
        self,
        model: str,
        method: str,
        args: list,
        kwargs: dict | None = None,
    ) -> Any:
        """Execute an Odoo ORM method via /xmlrpc/2/object.

        Retries up to ``settings.RPC_RETRY_ATTEMPTS`` times with
        exponential backoff on connection errors.  XML-RPC Faults
        are translated to OdooMCPError subclasses and raised
        immediately (no retry for application-level errors).
        """
        if self.uid is None:
            raise OdooAuthenticationError(
                "Client not authenticated — call authenticate() first"
            )

        object_url = f"{self.url}/xmlrpc/2/object"
        kw = kwargs or {}

        def _call() -> Any:
            proxy = xmlrpc.client.ServerProxy(object_url, allow_none=True)
            return proxy.execute_kw(
                self.db, self.uid, self.password, model, method, args, kw
            )

        last_exc: Exception | None = None
        for attempt in range(1, self._retry_attempts + 1):
            try:
                return await asyncio.to_thread(_call)
            except xmlrpc.client.Fault as fault:
                # Application-level fault — do not retry
                raise _translate_fault(fault) from fault
            except (
                ConnectionRefusedError,
                OSError,
                xmlrpc.client.ProtocolError,
            ) as exc:
                last_exc = exc
                if attempt < self._retry_attempts:
                    delay = self._retry_backoff * (2 ** (attempt - 1))
                    logger.warning(
                        "Odoo RPC connection error (attempt %d/%d), "
                        "retrying in %.1fs: %s",
                        attempt,
                        self._retry_attempts,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)

        raise OdooConnectionError(
            f"Failed to reach Odoo after {self._retry_attempts} "
            f"attempts: {last_exc}"
        ) from last_exc

    # ── Convenience helpers ───────────────────────────────────────

    async def search_read(
        self,
        model: str,
        domain: list,
        fields: list | None = None,
        limit: int = 80,
        offset: int = 0,
        order: str = "",
    ) -> list[dict]:
        """Search and read records in a single RPC call."""
        kw: dict[str, Any] = {"limit": limit, "offset": offset}
        if fields is not None:
            kw["fields"] = fields
        if order:
            kw["order"] = order
        result = await self.execute_kw(model, "search_read", [domain], kw)
        return result  # type: ignore[return-value]

    async def search_count(self, model: str, domain: list) -> int:
        """Return the count of records matching *domain*."""
        result = await self.execute_kw(model, "search_count", [domain])
        return int(result)

    async def create(self, model: str, values: dict) -> int:
        """Create a record and return its id."""
        result = await self.execute_kw(model, "create", [values])
        return int(result)

    async def write(self, model: str, ids: list[int], values: dict) -> bool:
        """Update existing records. Returns True on success."""
        result = await self.execute_kw(model, "write", [ids, values])
        return bool(result)

    async def unlink(self, model: str, ids: list[int]) -> bool:
        """Delete records. Returns True on success."""
        result = await self.execute_kw(model, "unlink", [ids])
        return bool(result)

    async def fields_get(
        self,
        model: str,
        attributes: list[str] | None = None,
    ) -> dict:
        """Retrieve field metadata for *model*."""
        attrs = attributes or ["string", "type", "help", "required"]
        result = await self.execute_kw(
            model,
            "fields_get",
            [],
            {"attributes": attrs},
        )
        return result  # type: ignore[return-value]
