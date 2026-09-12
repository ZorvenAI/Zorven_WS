"""prompt-optimization-svc client.

Design §17.2 step 3 · implemented by story L-01.

Read-only client for POI's production endpoint. The hot-path is
``GET /v1/prompts/{name}/production`` with an optional ``X-Tenant-ID``
header. The endpoint has no auth requirement — it is open.

Failures are always swallowed: the resolution chain has fallbacks.
"""

from __future__ import annotations

import httpx

from app.circuit_breaker.breaker import CircuitBreaker, CircuitBreakerOpen
from app.core.logging import get_logger

logger = get_logger(__name__)

TIMEOUT_S = 5.0


class POIClient:
    """Read-only client for the POI production endpoint."""

    def __init__(
        self,
        base_url: str,
        *,
        breaker: CircuitBreaker | None = None,
        timeout: float = TIMEOUT_S,
    ) -> None:
        self._base_url = base_url.rstrip("/") if base_url else ""
        self._breaker = breaker
        self._timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self._base_url)

    async def get_production(
        self, name: str, tenant_id: str | None = None
    ) -> tuple[str, str] | None:
        """Fetch the production prompt template and version.

        Returns ``(template, version_str)`` on success, ``None`` on any
        failure. The caller moves to the next resolution step.
        """
        if not self.configured:
            return None

        if self._breaker is not None:
            try:
                self._breaker.before_call()
            except CircuitBreakerOpen:
                logger.debug("poi_breaker_open", name=name)
                return None

        headers: dict[str, str] = {}
        if tenant_id:
            headers["X-Tenant-ID"] = tenant_id

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                resp = await client.get(
                    f"{self._base_url}/v1/prompts/{name}/production",
                    headers=headers,
                )
                if resp.status_code == 404:
                    if self._breaker is not None:
                        self._breaker.record_success()
                    return None
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPStatusError as exc:
                if self._breaker is not None:
                    if exc.response.status_code < 500:
                        self._breaker.record_success()
                    else:
                        self._breaker.record_failure()
                logger.warning(
                    "poi_fetch_failed",
                    name=name,
                    error=f"{type(exc).__name__}: {exc}",
                )
                return None
            except Exception as exc:
                if self._breaker is not None:
                    self._breaker.record_failure()
                logger.warning(
                    "poi_fetch_failed",
                    name=name,
                    error=f"{type(exc).__name__}: {exc}",
                )
                return None

        if self._breaker is not None:
            self._breaker.record_success()

        template = data.get("template")
        version = data.get("version")
        if template is None or version is None:
            return None
        return str(template), str(version)
