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

from urllib.parse import quote

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
QUESTIONNAIRE_PATH = "/api/v1/onboarding/questionnaires/generate/"
VOCABULARY_PATH = "/api/v1/onboarding/field-vocabulary/"
PRECHECK_PATH = "/api/v1/onboarding/sessions/{session_id}/live-precheck/"

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

    async def _post(
        self, path: str, payload: dict[str, Any], *, tenant_id: str
    ) -> dict[str, Any] | None:
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
                headers={
                    "X-Service-Token": self._token,
                    # Django cannot infer the tenant on this path: its
                    # DefaultTenantMiddleware resolves an unmatched host to the
                    # *public* tenant, so an internal call with no header is
                    # attributed to the wrong tenant rather than rejected. The
                    # agent is the only party that knows, so it says.
                    "X-Tenant-ID": tenant_id,
                },
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
        tenant_id: str,
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

        body = await self._post(UPSERT_PATH, payload, tenant_id=tenant_id)
        return bool(body and body.get("stored"))

    async def store_questionnaire(
        self,
        *,
        tenant_id: str,
        questions: list[dict[str, Any]],
        depth: str,
        session_id: str | None = None,
        company_id: str | None = None,
        chat_session_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Persist a generated set as a DRAFT (C-03 AC-4).

        Returns the stored questionnaire, or None. Unlike the research brief,
        a failure here **is** worth surfacing: AC-4 says a row exists, and an
        operator told "12 questions ready" who then finds nothing to approve
        has been misled. The caller decides what to say; this still does not
        raise.
        """
        payload: dict[str, Any] = {"questions": questions, "depth": depth}
        if session_id:
            payload["session_id"] = session_id
        if company_id:
            payload["company_id"] = company_id
        if chat_session_id:
            payload["chat_session_id"] = chat_session_id

        return await self._post(QUESTIONNAIRE_PATH, payload, tenant_id=tenant_id)

    async def field_vocabulary(self, *, tenant_id: str) -> list[str]:
        """The target_field names B-06 defines (C-03).

        Empty on failure rather than raising: without it the generator omits
        field hints and Django drops any name it invents, so the questionnaire
        is still usable — it just loses the J-02 joins until the next fetch.
        """
        body = await self._get(VOCABULARY_PATH, tenant_id=tenant_id)
        fields = (body or {}).get("fields")
        return [str(f) for f in fields] if isinstance(fields, list) else []

    async def _get(self, path: str, *, tenant_id: str) -> dict[str, Any] | None:
        if not self.configured:
            return None
        try:
            self._breaker.before_call()
        except CircuitBreakerOpen:
            return None

        client = self._client or httpx.AsyncClient(timeout=TIMEOUT_S)
        owns_client = self._client is None
        try:
            response = await client.get(
                f"{self._base_url}{path}",
                headers={
                    "X-Service-Token": self._token,
                    "X-Tenant-ID": tenant_id,
                },
                timeout=TIMEOUT_S,
            )
            if response.status_code == 404:
                # Not a failure of ours, and not a breaker event. Django
                # answers 404 for a session outside the caller's tenant —
                # FR-PREP-06 is explicit that a cross-tenant read must not
                # confirm the row exists — so this is a *fact about the
                # request*, and collapsing it into None makes it
                # indistinguishable from Django being down. The caller then
                # cannot tell "no such session" (4404) from "we are broken"
                # (1011), and tells the operator the wrong one.
                self._breaker.record_success()
                return {"__status__": 404}
            response.raise_for_status()
            body = response.json()
        except Exception as exc:
            self._breaker.record_failure()
            logger.warning(
                "backend_read_failed", path=path, error=f"{type(exc).__name__}: {exc}"
            )
            return None
        finally:
            if owns_client:
                await client.aclose()

        self._breaker.record_success()
        return body if isinstance(body, dict) else None

    async def live_precheck(
        self, *, tenant_id: str, session_id: str, ticket: str = ""
    ) -> dict[str, Any] | None:
        """IG-10's data: may this session open a live socket?

        None on any failure, which the caller treats as a refusal. This is the
        one read in this client where failing closed matters — everywhere else
        a backend problem costs a stored copy, and here it would put a meeting
        on air against a questionnaire nobody approved.
        """
        path = PRECHECK_PATH.format(session_id=session_id)
        if ticket:
            # F-04: the ticket travels on the same call that already asks
            # about approval and consent, so one read decides the whole
            # handshake. Query rather than header because this endpoint is a
            # GET and the value is opaque and short-lived.
            path = f"{path}?ticket={quote(ticket, safe='')}"
        return await self._get(path, tenant_id=tenant_id)
