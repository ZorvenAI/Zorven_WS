"""Tavily web search, behind the §18.2 breaker.

Design §8.1 SKL-OIA-01, §18.2 · implemented by story C-02.

Two deliberate departures from the fleet's existing Tavily code
(``discovery-agent-svc/app/scrapers/search_engine.py``):

1. **The async client.** The fleet calls the synchronous ``TavilyClient`` from
   inside ``async def``, which blocks the event loop for the duration of a
   network round trip. OIA serves live WebSocket sessions from the same loop,
   so a blocked loop is a stalled meeting.
2. **Failures are not swallowed.** The fleet catches every exception and
   returns ``[]``, which is indistinguishable from "the web has nothing on
   this business". C-02's AC-3 requires the opposite: a failure must be
   visible, must count toward the breaker, and must surface as
   ``degraded: true`` with a reason.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.circuit_breaker.breaker import (
    BreakerRegistry,
    CircuitBreaker,
    CircuitBreakerOpen,
)

logger = logging.getLogger(__name__)

DEPENDENCY = "tavily"

#: Tavily's own cap is higher, but a research brief that cites twenty sources
#: is not more grounded than one citing five — it just costs more and gives
#: the model more to dilute. Overridable per call.
DEFAULT_MAX_RESULTS = 5


@dataclass(frozen=True)
class SearchResult:
    """One source. ``url`` is the part that matters.

    AC-1 requires every asserted fact to carry a source URL, so a result
    without one cannot ground anything and is dropped at parse time rather
    than being carried forward to fail a guardrail later.
    """

    title: str
    url: str
    snippet: str


class TavilyUnavailable(Exception):
    """Search could not be performed. Carries the operator-facing reason.

    Distinct from "search returned nothing": the caller degrades on this and
    reports an empty result set normally.
    """

    def __init__(self, reason: str, *, degraded_mode: str = "SKIP_RESEARCH") -> None:
        super().__init__(reason)
        self.reason = reason
        self.degraded_mode = degraded_mode


class TavilyProvider:
    """Search the web, or say plainly that it could not.

    The breaker is consulted through ``before_call`` rather than ``is_open``
    so the check and the half-open trial claim are one atomic step.
    """

    def __init__(
        self,
        api_key: str,
        *,
        breaker: CircuitBreaker | None = None,
        client: Any | None = None,
    ) -> None:
        self._api_key = api_key
        self._breaker = breaker or BreakerRegistry().get(DEPENDENCY)
        self._client = client

    @property
    def configured(self) -> bool:
        """False when no API key is set.

        Not an error: local development and CI run without a Tavily key, and
        the correct behaviour there is the same degraded brief AC-3 describes,
        not a crash. It is reported as a distinct reason so an operator can
        tell a missing key from an outage.
        """
        return bool(self._api_key)

    def _ensure_client(self) -> Any:
        if self._client is None:
            from tavily import AsyncTavilyClient

            self._client = AsyncTavilyClient(api_key=self._api_key)
        return self._client

    async def search(
        self, query: str, *, max_results: int = DEFAULT_MAX_RESULTS
    ) -> list[SearchResult]:
        """Run one search.

        Raises :class:`TavilyUnavailable` when the breaker is open, when no key
        is configured, or when the call fails. Returns an empty list only when
        the search genuinely found nothing — the caller needs to tell those
        apart, because one means "we could not look" and the other means "we
        looked and there is nothing".
        """
        if not self.configured:
            raise TavilyUnavailable("no Tavily API key is configured")

        try:
            self._breaker.before_call()
        except CircuitBreakerOpen as exc:
            raise TavilyUnavailable(
                exc.user_message or f"{exc.dependency} is unavailable",
                degraded_mode=exc.degraded_mode,
            ) from exc

        try:
            response = await self._ensure_client().search(
                query=query,
                max_results=max_results,
                search_depth="basic",
            )
        except Exception as exc:
            # Broad by intent. Tavily's client raises its own exception types,
            # httpx raises transport errors, and a bad key raises something
            # else again; every one of them means "this call did not work" and
            # must reach the breaker. Narrowing here would let an unlisted
            # exception escape into the chat turn.
            self._breaker.record_failure()
            logger.warning("tavily search failed: %s: %s", type(exc).__name__, exc)
            raise TavilyUnavailable(f"web search failed: {type(exc).__name__}") from exc

        self._breaker.record_success()
        return self._parse(response)

    @staticmethod
    def _parse(response: Any) -> list[SearchResult]:
        """Pull results out of a response, skipping anything unsourced.

        Defensive about shape on purpose: this is third-party JSON crossing a
        network, and C-01's review found the equivalent bug one layer up —
        assuming a decoded body is a dict, then raising AttributeError two
        frames away.
        """
        if not isinstance(response, dict):
            logger.warning("tavily returned %s, not an object", type(response).__name__)
            return []

        raw = response.get("results")
        if not isinstance(raw, list):
            return []

        results: list[SearchResult] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            if not url:
                # Cannot ground a fact, so it would be dropped by OG-01 later.
                continue
            results.append(
                SearchResult(
                    title=str(item.get("title") or "").strip(),
                    url=url,
                    snippet=str(item.get("content") or "")[:500],
                )
            )
        return results
