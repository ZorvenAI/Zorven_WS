"""Writes to the Django backend.

Design §10.1, §18.2 (`backend` breaker) · implemented by story C-02.

Scaffolded by A-05. C-02 needs one write — persisting a research brief so AC-2's
"or opens the Onboarding Interface" holds — so this implements that one and
leaves the rest to the stories that need them.

**Persistence must never cost the operator their turn.** The brief is already
returned in the response and cached in Redis by the time this runs; the durable
copy is what lets the Interface show it later. So every failure here is logged
and swallowed, and the breaker opens so a backend outage stops costing a round
trip per turn. A raise would trade a working conversation for a storage
detail.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.circuit_breaker.breaker import (
    BreakerRegistry,
    CircuitBreaker,
    CircuitBreakerOpen,
)
from app.core.logging import get_logger

logger = get_logger(__name__)

DEPENDENCY = "backend"
UPSERT_PATH = "/api/v1/onboarding/research-briefs/upsert/"

#: Short. This is a fire-and-forget write on the tail of a turn the operator
#: is waiting on, and §2.1 gives PREP a 60 s budget that research and synthesis
#: have already spent most of.
TIMEOUT_S = 5.0


class BackendClient:
    """The agent's HTTP client for Django."""

    def __init__(
        self,
        base_url: str,
        service_token: str,
        *,
        breaker: CircuitBreaker | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = service_token
        self._breaker = breaker or BreakerRegistry().get(DEPENDENCY)
        self._client = client

    @property
    def configured(self) -> bool:
        """False when there is nowhere real to write.

        ``PLACEHOLDER`` is checked explicitly because that is the literal
        string the GCP deploy set on this service until C-02 added it to
        ``10-redeploy-with-urls.sh``. Treating it as a URL would mean every
        write failing DNS resolution and opening the breaker, which reports an
        outage when the truth is a missing deploy step.
        """
        return bool(self._base_url) and "PLACEHOLDER" not in self._base_url

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if not self.configured:
            logger.warning(
                "backend_not_configured", base_url=self._base_url or "(unset)"
            )
            return None

        try:
            self._breaker.before_call()
        except CircuitBreakerOpen:
            logger.warning("backend_breaker_open", path=path)
            return None

        client = self._client or httpx.AsyncClient(timeout=TIMEOUT_S)
        owns_client = self._client is None
        try:
            response = await client.post(
                f"{self._base_url}{path}",
                json=payload,
                headers={"X-Service-Token": self._token},
                timeout=TIMEOUT_S,
            )
            response.raise_for_status()
            body = response.json()
        except Exception as exc:
            self._breaker.record_failure()
            logger.warning(
                "backend_write_failed", path=path, error=f"{type(exc).__name__}: {exc}"
            )
            return None
        finally:
            if owns_client:
                await client.aclose()

        self._breaker.record_success()
        return body if isinstance(body, dict) else None

    async def store_research_brief(
        self,
        *,
        company_name: str,
        brief: dict[str, Any],
        session_id: str | None = None,
    ) -> bool:
        """Persist a brief. Returns whether it was stored.

        A degraded brief is not sent at all. Django refuses it anyway — the
        rule is enforced on both sides deliberately — but sending one would
        spend a round trip to be told no, on the exact path where the
        dependency may already be unwell.
        """
        if brief.get("degraded"):
            return False

        payload: dict[str, Any] = {"company_name": company_name, "brief": brief}
        if session_id:
            payload["session_id"] = session_id

        body = await self._post(UPSERT_PATH, payload)
        return bool(body and body.get("stored"))
