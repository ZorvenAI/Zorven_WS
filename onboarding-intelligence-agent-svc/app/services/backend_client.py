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

from typing import TYPE_CHECKING, Any

from urllib.parse import quote

import httpx

from app.circuit_breaker.breaker import (
    BreakerRegistry,
    CircuitBreaker,
    CircuitBreakerOpen,
)
from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.cache.outbox import OutboxWriter

logger = get_logger(__name__)

DEPENDENCY = "backend"
ASSET_REGISTER_PATH = "/api/v1/internal/assets/register/"
OCR_UPDATE_PATH = "/api/v1/internal/assets/{asset_id}/ocr/"
RECORDING_SUMMARY_PATH = (
    "/api/v1/onboarding/internal/recordings/{recording_id}/summary/"
)
SESSION_EVIDENCE_PATH = "/api/v1/onboarding/internal/sessions/{session_id}/evidence/"
COMPANY_FIELDS_PATH = "/api/v1/onboarding/internal/companies/{company_id}/fields/"
PROVENANCE_BULK_PATH = (
    "/api/v1/onboarding/internal/sessions/{session_id}/provenance/bulk/"
)
EXISTING_PROVENANCE_PATH = (
    "/api/v1/onboarding/internal/sessions/{session_id}/provenance/"
)
UPSERT_PATH = "/api/v1/onboarding/research-briefs/upsert/"
QUESTIONNAIRE_PATH = "/api/v1/onboarding/questionnaires/generate/"
VOCABULARY_PATH = "/api/v1/onboarding/field-vocabulary/"
PRECHECK_PATH = "/api/v1/onboarding/sessions/{session_id}/live-precheck/"
PROMPT_VERSIONS_PATH = (
    "/api/v1/onboarding/internal/sessions/{session_id}/prompt-versions/"
)
GENERATE_STRATEGY_PATH = (
    "/api/v1/onboarding/internal/companies/{company_id}/generate-strategy/"
)
GENERATE_IDENTITY_PATH = (
    "/api/v1/onboarding/internal/companies/{company_id}/generate-identity/"
)
FINALIZE_STUCK_PATH = (
    "/api/v1/onboarding/internal/sessions/{session_id}/finalize-stuck/"
)

#: Short. This is a fire-and-forget write on the tail of a turn the operator
#: is waiting on, and §2.1 gives PREP a 60 s budget that research and synthesis
#: have already spent most of.
TIMEOUT_S = 5.0

#: SKL-OIA-12 budget is 90 s for both calls. 45 s each leaves headroom.
GENERATE_TIMEOUT_S = 45.0


class BackendClient:
    """The agent's HTTP client for Django."""

    def __init__(
        self,
        base_url: str,
        service_token: str,
        *,
        breaker: CircuitBreaker | None = None,
        client: httpx.AsyncClient | None = None,
        outbox: OutboxWriter | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = service_token
        self._breaker = breaker or BreakerRegistry().get(DEPENDENCY)
        self._client = client
        self._outbox = outbox

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
        self,
        path: str,
        payload: dict[str, Any],
        *,
        tenant_id: str,
        timeout: float = TIMEOUT_S,
    ) -> dict[str, Any] | None:
        if not self.configured:
            logger.warning(
                "backend_not_configured", base_url=self._base_url or "(unset)"
            )
            return None

        try:
            self._breaker.before_call()
        except CircuitBreakerOpen as exc:
            if self._outbox is not None:
                await self._outbox.enqueue(
                    method="POST",
                    path=path,
                    payload=payload,
                    tenant_id=tenant_id,
                    timeout=timeout,
                )
                logger.info(
                    "backend_write_buffered",
                    path=path,
                    user_message=exc.user_message,
                )
            else:
                logger.warning("backend_breaker_open", path=path)
            return None

        client = self._client or httpx.AsyncClient(timeout=timeout)
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
                timeout=timeout,
            )
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code < 500:
                self._breaker.record_success()
            else:
                self._breaker.record_failure()
            logger.warning(
                "backend_write_failed", path=path, error=f"{type(exc).__name__}: {exc}"
            )
            return None
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

    async def send_callback(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        tenant_id: str,
        timeout: float = 30.0,
    ) -> dict[str, Any] | None:
        """POST a callback payload to Django with an appropriate timeout."""
        return await self._post(path, payload, tenant_id=tenant_id, timeout=timeout)

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

    async def _get(
        self, path: str, *, tenant_id: str, timeout: float = TIMEOUT_S
    ) -> dict[str, Any] | None:
        if not self.configured:
            return None
        try:
            self._breaker.before_call()
        except CircuitBreakerOpen:
            return None

        client = self._client or httpx.AsyncClient(timeout=timeout)
        owns_client = self._client is None
        try:
            response = await client.get(
                f"{self._base_url}{path}",
                headers={
                    "X-Service-Token": self._token,
                    "X-Tenant-ID": tenant_id,
                },
                timeout=timeout,
            )
            if response.status_code == 404:
                self._breaker.record_success()
                return {"__status__": 404}
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code < 500:
                self._breaker.record_success()
            else:
                self._breaker.record_failure()
            logger.warning(
                "backend_read_failed", path=path, error=f"{type(exc).__name__}: {exc}"
            )
            return None
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

    async def get_session_evidence(
        self, *, tenant_id: str, session_id: str
    ) -> dict[str, Any] | None:
        """Fetch the full evidence bundle for a session (J-02)."""
        path = SESSION_EVIDENCE_PATH.format(session_id=session_id)
        return await self._get(path, tenant_id=tenant_id, timeout=GENERATE_TIMEOUT_S)

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

    async def _patch(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        tenant_id: str,
    ) -> dict[str, Any] | None:
        if not self.configured:
            logger.warning(
                "backend_not_configured",
                base_url=self._base_url or "(unset)",
            )
            return None

        try:
            self._breaker.before_call()
        except CircuitBreakerOpen as exc:
            if self._outbox is not None:
                await self._outbox.enqueue(
                    method="PATCH",
                    path=path,
                    payload=payload,
                    tenant_id=tenant_id,
                )
                logger.info(
                    "backend_write_buffered",
                    path=path,
                    user_message=exc.user_message,
                )
            else:
                logger.warning("backend_breaker_open", path=path)
            return None

        client = self._client or httpx.AsyncClient(timeout=TIMEOUT_S)
        owns_client = self._client is None
        try:
            response = await client.patch(
                f"{self._base_url}{path}",
                json=payload,
                headers={
                    "X-Service-Token": self._token,
                    "X-Tenant-ID": tenant_id,
                },
                timeout=TIMEOUT_S,
            )
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code < 500:
                self._breaker.record_success()
            else:
                self._breaker.record_failure()
            logger.warning(
                "backend_write_failed",
                path=path,
                error=f"{type(exc).__name__}: {exc}",
            )
            return None
        except Exception as exc:
            self._breaker.record_failure()
            logger.warning(
                "backend_write_failed",
                path=path,
                error=f"{type(exc).__name__}: {exc}",
            )
            return None
        finally:
            if owns_client:
                await client.aclose()

        self._breaker.record_success()
        return body if isinstance(body, dict) else None

    async def update_asset_ocr(
        self,
        *,
        tenant_id: str,
        asset_id: int,
        ocr_text: str,
        ocr_confidence: float,
        sensitivity_class: str,
        rag_excluded: bool,
    ) -> bool:
        """Write OCR results back to a BrandAsset (H-03)."""
        path = OCR_UPDATE_PATH.format(asset_id=asset_id)
        body = await self._patch(
            path,
            {
                "ocr_text": ocr_text,
                "ocr_confidence": ocr_confidence,
                "sensitivity_class": sensitivity_class,
                "rag_excluded": rag_excluded,
            },
            tenant_id=tenant_id,
        )
        return body is not None

    async def update_recording_summary(
        self,
        *,
        tenant_id: str,
        recording_id: str,
        summary: dict[str, Any],
        transcript_segments: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Write summary and transcript back to a MeetingRecording (I-02, I-03)."""
        path = RECORDING_SUMMARY_PATH.format(recording_id=recording_id)
        payload: dict[str, Any] = {"summary": summary}
        if transcript_segments is not None:
            payload["transcript"] = transcript_segments
        body = await self._patch(
            path,
            payload,
            tenant_id=tenant_id,
        )
        return body is not None

    async def patch_company_fields(
        self,
        *,
        tenant_id: str,
        company_id: int,
        fields: dict[str, Any],
    ) -> dict[str, Any] | None:
        """PATCH Company fields back to Django (J-03)."""
        path = COMPANY_FIELDS_PATH.format(company_id=company_id)
        return await self._patch(path, fields, tenant_id=tenant_id)

    async def create_provenance_bulk(
        self,
        *,
        tenant_id: str,
        session_id: str,
        records: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Bulk-create FieldProvenance records (J-03)."""
        path = PROVENANCE_BULK_PATH.format(session_id=session_id)
        return await self._post(path, {"records": records}, tenant_id=tenant_id)

    async def get_existing_provenance(
        self,
        *,
        tenant_id: str,
        session_id: str,
    ) -> list[dict[str, Any]]:
        """Fetch existing FieldProvenance for PG-06 checks (J-03)."""
        path = EXISTING_PROVENANCE_PATH.format(session_id=session_id)
        body = await self._get(path, tenant_id=tenant_id)
        if body is None or body.get("__status__") == 404:
            return []
        records = body.get("records", [])
        return records if isinstance(records, list) else []

    async def persist_prompt_versions(
        self,
        *,
        tenant_id: str,
        session_id: str,
        prompt_versions: dict[str, Any],
    ) -> bool:
        """Persist resolved prompt versions to Django (L-03)."""
        if not prompt_versions:
            return False
        path = PROMPT_VERSIONS_PATH.format(session_id=session_id)
        body = await self._patch(
            path,
            {"prompt_versions": prompt_versions},
            tenant_id=tenant_id,
        )
        return bool(body and body.get("stored"))

    async def generate_brand_strategy(
        self, *, tenant_id: str, company_id: int
    ) -> dict[str, Any] | None:
        """Trigger brand strategy generation (J-06, SKL-OIA-12)."""
        path = GENERATE_STRATEGY_PATH.format(company_id=company_id)
        return await self._post(
            path, {}, tenant_id=tenant_id, timeout=GENERATE_TIMEOUT_S
        )

    async def finalize_stuck_session(
        self, *, tenant_id: str, session_id: str
    ) -> dict[str, Any] | None:
        """Ask Django to transition a stuck MEETING_LIVE session to GATHERED (M-04)."""
        path = FINALIZE_STUCK_PATH.format(session_id=session_id)
        return await self._post(
            path,
            {"reason": "watchdog_stuck_session"},
            tenant_id=tenant_id,
        )

    async def register_brand_asset(
        self,
        *,
        tenant_id: str,
        file_name: str,
        file_type: str,
        file_size: int,
        gcs_uri: str,
    ) -> dict[str, Any] | None:
        """Register a BrandAsset and trigger the data pipeline (SKL-OIA-11).

        Returns ``{"asset_id": ..., "company_id": ..., ...}`` on success,
        or None on failure. Failure is logged and swallowed — the caller
        aggregates results and reports partial success.
        """
        return await self._post(
            ASSET_REGISTER_PATH,
            {
                "file_name": file_name,
                "file_type": file_type,
                "file_size": file_size,
                "gcs_uri": gcs_uri,
            },
            tenant_id=tenant_id,
        )

    async def generate_brand_identity(
        self, *, tenant_id: str, company_id: int
    ) -> dict[str, Any] | None:
        """Trigger brand identity generation (J-06, SKL-OIA-12)."""
        path = GENERATE_IDENTITY_PATH.format(company_id=company_id)
        return await self._post(
            path, {}, tenant_id=tenant_id, timeout=GENERATE_TIMEOUT_S
        )

    async def replay_entry(self, entry: dict[str, Any]) -> bool:
        """Replay a buffered outbox entry. Returns True on success.

        Used by the outbox drain — goes through the breaker but does NOT
        re-enqueue on failure (that would loop). Non-retryable failures
        (4xx) are logged and discarded.
        """
        method = entry.get("method", "POST")
        path = entry.get("path", "")
        payload = entry.get("payload", {})
        tenant_id = entry.get("tenant_id", "")
        timeout = float(entry.get("timeout", TIMEOUT_S))

        if not self.configured or not path or not tenant_id:
            return False

        try:
            self._breaker.before_call()
        except CircuitBreakerOpen:
            return False

        client = self._client or httpx.AsyncClient(timeout=timeout)
        owns_client = self._client is None
        try:
            if method == "PATCH":
                response = await client.patch(
                    f"{self._base_url}{path}",
                    json=payload,
                    headers={
                        "X-Service-Token": self._token,
                        "X-Tenant-ID": tenant_id,
                    },
                    timeout=timeout,
                )
            else:
                response = await client.post(
                    f"{self._base_url}{path}",
                    json=payload,
                    headers={
                        "X-Service-Token": self._token,
                        "X-Tenant-ID": tenant_id,
                    },
                    timeout=timeout,
                )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code < 500:
                self._breaker.record_success()
                logger.warning(
                    "outbox_replay_client_error",
                    path=path,
                    status=exc.response.status_code,
                )
                return True
            self._breaker.record_failure()
            logger.warning("outbox_replay_server_error", path=path)
            return False
        except Exception as exc:
            self._breaker.record_failure()
            logger.warning(
                "outbox_replay_failed",
                path=path,
                error=f"{type(exc).__name__}: {exc}",
            )
            return False
        finally:
            if owns_client:
                await client.aclose()

        self._breaker.record_success()
        return True
