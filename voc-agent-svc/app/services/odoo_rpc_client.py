"""Odoo XML-RPC client for the Voice of Customer Agent.

Read-only operations only (PG-09 enforced at client level).
Supports both project.task and helpdesk.ticket models (Decision #1).
"""

import asyncio
import logging
import xmlrpc.client
from typing import Any

logger = logging.getLogger(__name__)


class OdooRPCClient:
    """Async-wrapped Odoo XML-RPC client (read-only)."""

    def __init__(
        self,
        url: str,
        db: str,
        username: str,
        password: str,
    ) -> None:
        self._url = url
        self._db = db
        self._username = username
        self._password = password
        self._uid: int | None = None
        self._common = None
        self._models = None

    async def authenticate(self) -> int:
        """Authenticate with Odoo and return UID."""
        loop = asyncio.get_event_loop()
        self._common = xmlrpc.client.ServerProxy(
            f"{self._url}/xmlrpc/2/common"
        )
        self._uid = await loop.run_in_executor(
            None,
            self._common.authenticate,
            self._db,
            self._username,
            self._password,
            {},
        )
        self._models = xmlrpc.client.ServerProxy(
            f"{self._url}/xmlrpc/2/object"
        )
        logger.info("Odoo authenticated: uid=%s", self._uid)
        return self._uid

    async def search_read(
        self,
        model: str,
        domain: list[Any],
        fields: list[str],
        limit: int = 100,
        offset: int = 0,
        order: str = "",
    ) -> list[dict[str, Any]]:
        """Read-only search_read operation."""
        if not self._uid or not self._models:
            await self.authenticate()

        loop = asyncio.get_event_loop()
        kwargs: dict[str, Any] = {
            "fields": fields,
            "limit": limit,
            "offset": offset,
        }
        if order:
            kwargs["order"] = order

        result = await loop.run_in_executor(
            None,
            self._models.execute_kw,
            self._db,
            self._uid,
            self._password,
            model,
            "search_read",
            [domain],
            kwargs,
        )
        return result or []

    async def search_count(
        self,
        model: str,
        domain: list[Any],
    ) -> int:
        """Count records matching domain."""
        if not self._uid or not self._models:
            await self.authenticate()

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            self._models.execute_kw,
            self._db,
            self._uid,
            self._password,
            model,
            "search_count",
            [domain],
        )
        return result or 0

    async def fields_get(
        self,
        model: str,
        attributes: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get field definitions for a model (read-only introspection)."""
        if not self._uid or not self._models:
            await self.authenticate()

        loop = asyncio.get_event_loop()
        kwargs = {}
        if attributes:
            kwargs["attributes"] = attributes

        result = await loop.run_in_executor(
            None,
            self._models.execute_kw,
            self._db,
            self._uid,
            self._password,
            model,
            "fields_get",
            [],
            kwargs,
        )
        return result or {}
