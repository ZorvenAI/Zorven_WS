"""Dispatching prep chat turns to the Onboarding Intelligence Agent (C-01).

§10.2 puts ``POST /v1/execute`` behind ``X-Service-Token`` and marks it "not
exposed publicly", so Django is the only caller and holds the token.

The design point worth keeping in view: preparation happens in the chat the
operator already uses, so a failure here has to read as *this feature is
unavailable*, not as a broken chat. AC-3 is explicit that a generic error or a
silent hang are both wrong.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import requests
from decouple import config

logger = logging.getLogger(__name__)

#: Provisional, mirroring the agent's ErrorCode.AGENT_UNAVAILABLE.
#:
#: C-01's AC-3 asks for ERR-13, which §18.4 spends on a field conflict
#: requiring a human (202, SKL-OIA-14) — a different thing needing a different
#: response. Nothing existing covers "Django cannot reach the agent": ERR-07,
#: 08 and 09 are the agent's *own* degraded dependencies and ERR-10 is a
#: buffered write in the opposite direction.
ERR_AGENT_UNAVAILABLE = "ERR-19"

EXECUTE_PATH = "/v1/execute"

#: Short on purpose. An operator is watching a chat box, and §2.1 puts PREP in
#: the "≤60 s" latency class only for the *skill*; the dispatch itself either
#: connects promptly or is not going to.
CONNECT_TIMEOUT_S = 3
READ_TIMEOUT_S = 60

#: Consecutive failures before the breaker opens, and how long it stays open.
#: Per-process and in memory: a shared breaker needs Redis and coordination
#: across Cloud Run instances, which is a larger change than this story.
#: Documented rather than implied, because an in-memory breaker on N instances
#: opens N times independently.
BREAKER_THRESHOLD = 3
BREAKER_COOLDOWN_S = 60


@dataclass
class AgentResult:
    """What the caller needs to decide what to show.

    ``ok`` is separate from ``payload`` so a caller cannot mistake an error
    body for a result — the failure path returns a message meant for a human,
    and rendering that as if it were agent output is the confusion AC-3 is
    trying to prevent.
    """

    ok: bool
    payload: dict | None = None
    code: str | None = None
    message: str | None = None


class _Breaker:
    """Trips after repeated failures so a dead agent is not retried per turn.

    Deliberately tiny. A dependency that has failed three times in a row will
    almost certainly fail the fourth, and making the operator wait out the
    connect timeout each time is worse than telling them immediately.
    """

    def __init__(self) -> None:
        self._failures = 0
        self._opened_at = 0.0

    @property
    def is_open(self) -> bool:
        if self._failures < BREAKER_THRESHOLD:
            return False
        if time.monotonic() - self._opened_at >= BREAKER_COOLDOWN_S:
            # Half-open: let the next call through to test the water.
            self._failures = 0
            return False
        return True

    def record_success(self) -> None:
        self._failures = 0

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures == BREAKER_THRESHOLD:
            self._opened_at = time.monotonic()
            logger.warning(
                "onboarding agent breaker opened after %s consecutive failures",
                BREAKER_THRESHOLD,
            )


_breaker = _Breaker()

UNAVAILABLE_MESSAGE = (
    "Onboarding preparation is temporarily unavailable. You can still "
    "prepare manually through the onboarding forms, and I'll pick this up "
    "again once the service is back."
)


def reset_breaker() -> None:
    """Test seam. The breaker is process state, and a test that trips it
    would otherwise leak that into the next one."""
    global _breaker
    _breaker = _Breaker()


def dispatch_prep_turn(
    *,
    tenant_id: str,
    user_id: str,
    role: str,
    trace_id: str,
    chat_session_id: str,
    prompt: str,
    session_id: str | None = None,
    input_context: dict | None = None,
) -> AgentResult:
    """Send one prep turn to the agent.

    Never raises. Every failure becomes an ``AgentResult`` naming preparation
    as unavailable, because AC-3 requires a specific message rather than "a
    generic error or a silent hang" — and because an exception escaping here
    would break the whole chat turn, not just its prep half.
    """
    if _breaker.is_open:
        logger.info("prep dispatch short-circuited: breaker open")
        return AgentResult(
            ok=False, code=ERR_AGENT_UNAVAILABLE, message=UNAVAILABLE_MESSAGE
        )

    base_url = config("OIA_SERVICE_URL", default="http://localhost:8120")
    token = config("OIA_SERVICE_TOKEN", default="")

    body = {
        "tenant_context": {
            "tenant_id": str(tenant_id),
            "user_id": str(user_id),
            "role": role,
            "trace_id": str(trace_id),
        },
        "chat_session_id": str(chat_session_id),
        "input_prompt": prompt,
        "input_context": input_context or {},
        "config": {},
        "previous_outputs": {},
    }
    if session_id:
        body["session_id"] = str(session_id)

    try:
        response = requests.post(
            f"{base_url.rstrip('/')}{EXECUTE_PATH}",
            json=body,
            headers={"X-Service-Token": token},
            timeout=(CONNECT_TIMEOUT_S, READ_TIMEOUT_S),
        )
    except requests.RequestException as exc:
        _breaker.record_failure()
        logger.warning("prep dispatch failed to reach the agent: %s", exc)
        return AgentResult(
            ok=False, code=ERR_AGENT_UNAVAILABLE, message=UNAVAILABLE_MESSAGE
        )

    if response.status_code >= 500:
        # 5xx is the agent saying it is unwell; 4xx is Django sending
        # something wrong, which is a bug here and must not trip the breaker
        # or it would mask itself as an outage.
        _breaker.record_failure()
        logger.warning("prep dispatch got %s from the agent", response.status_code)
        return AgentResult(
            ok=False, code=ERR_AGENT_UNAVAILABLE, message=UNAVAILABLE_MESSAGE
        )

    if response.status_code >= 400:
        logger.error(
            "prep dispatch rejected with %s — this is a bug in the caller, "
            "not an outage: %s",
            response.status_code,
            response.text[:300],
        )
        return AgentResult(
            ok=False, code=ERR_AGENT_UNAVAILABLE, message=UNAVAILABLE_MESSAGE
        )

    _breaker.record_success()
    return AgentResult(ok=True, payload=response.json())
