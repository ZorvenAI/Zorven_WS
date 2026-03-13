"""Lightweight async XML-RPC wrapper for Odoo ERP integration.

Feature-gated by APA_ODOO_ENABLED. Uses asyncio.to_thread for blocking calls.
"""

import asyncio
import logging
import xmlrpc.client
from typing import Any

logger = logging.getLogger(__name__)


class OdooRPCClient:
    """Async XML-RPC client for Odoo ERP."""

    def __init__(
        self,
        url: str,
        db: str,
        username: str,
        password: str,
    ) -> None:
        self.url = url.rstrip("/")
        self.db = db
        self.username = username
        self.password = password
        self._uid: int | None = None

    async def authenticate(self) -> int:
        """Authenticate with Odoo and return uid."""
        if self._uid is not None:
            return self._uid

        try:
            common = xmlrpc.client.ServerProxy(
                f"{self.url}/xmlrpc/2/common",
                allow_none=True,
            )
            uid = await asyncio.to_thread(
                common.authenticate, self.db, self.username, self.password, {}
            )
            if not uid:
                raise ConnectionError("Odoo authentication failed (uid=0)")
            self._uid = uid
            logger.info("Odoo authenticated: uid=%d", uid)
            return uid
        except Exception as exc:
            logger.error("Odoo authentication failed: %s", exc)
            raise

    async def search_read(
        self,
        model: str,
        domain: list | None = None,
        fields: list[str] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Search and read records from an Odoo model."""
        uid = await self.authenticate()
        domain = domain or []
        fields = fields or []

        models_proxy = xmlrpc.client.ServerProxy(
            f"{self.url}/xmlrpc/2/object",
            allow_none=True,
        )

        retries = 0
        max_retries = 2
        while True:
            try:
                result = await asyncio.to_thread(
                    models_proxy.execute_kw,
                    self.db,
                    uid,
                    self.password,
                    model,
                    "search_read",
                    [domain],
                    {
                        "fields": fields,
                        "limit": limit,
                        "offset": offset,
                    },
                )
                return result if isinstance(result, list) else []
            except (ConnectionError, xmlrpc.client.ProtocolError) as exc:
                retries += 1
                if retries > max_retries:
                    logger.error(
                        "Odoo search_read failed after %d retries: %s",
                        max_retries,
                        exc,
                    )
                    raise
                logger.warning("Odoo connection error, retry %d: %s", retries, exc)
                await asyncio.sleep(1)

    async def search_count(
        self,
        model: str,
        domain: list | None = None,
    ) -> int:
        """Count records matching domain in an Odoo model."""
        uid = await self.authenticate()
        domain = domain or []

        models_proxy = xmlrpc.client.ServerProxy(
            f"{self.url}/xmlrpc/2/object",
            allow_none=True,
        )

        retries = 0
        max_retries = 2
        while True:
            try:
                result = await asyncio.to_thread(
                    models_proxy.execute_kw,
                    self.db,
                    uid,
                    self.password,
                    model,
                    "search_count",
                    [domain],
                )
                return int(result) if result else 0
            except (ConnectionError, xmlrpc.client.ProtocolError) as exc:
                retries += 1
                if retries > max_retries:
                    raise
                logger.warning("Odoo count error, retry %d: %s", retries, exc)
                await asyncio.sleep(1)
