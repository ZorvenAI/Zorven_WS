"""IG-10 — a meeting cannot start without an approved questionnaire.

Design §5 IG-10, §10.2.3 · story C-04 AC-4.

§5 states the rule as "LIVE start requires questionnaire.status == APPROVED,
REFUSE with instruction to approve in PREP". The instruction half matters as
much as the refusal: an operator who is told only "forbidden" will retry the
same thing, and the one who is told "questionnaire 12 is DRAFT — approve it in
preparation" will go and fix it.

The verdict is computed here and delivered by ``app/api/ws.py``. Spike A-02
established that a close code cannot reach a client before ``accept()``: a
pre-accept close surfaces as plain HTTP 403 and §10.2.3's codes never arrive.
So the *decision* stays before accept and only the *delivery* moves after it.
Keeping the decision in this module rather than inline in the endpoint is what
lets it be tested without a socket.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.core.logging import get_logger
from app.logic.guardrails import Action, Verdict as ChainVerdict
from app.services.backend_client import BackendClient

logger = get_logger(__name__)

RULE_ID = "IG-10"

#: §10.2.3. 4403 is "forbidden" in the application range, and C-04 AC-4 names
#: it directly.
CLOSE_FORBIDDEN = 4403

#: Used when the backend cannot be reached. Failing closed is the only safe
#: reading: §5 says the guardrails "fail closed on any", and starting a meeting
#: that turns out to be unapproved cannot be undone once someone is talking.
UNREACHABLE_REASON = (
    "Preparation could not be verified, so the meeting was not started. "
    "Try again in a moment."
)


@dataclass(frozen=True)
class LiveVerdict:
    """Whether the socket may proceed, and what to tell the operator."""

    allowed: bool
    reason: str = ""
    close_code: int = CLOSE_FORBIDDEN

    @property
    def refused(self) -> bool:
        return not self.allowed


async def evaluate(
    backend: BackendClient | None, *, tenant_id: str, session_id: str
) -> LiveVerdict:
    """Decide whether this session may open a live socket.

    Fails closed on every uncertainty — an unreachable backend, an unknown
    session, a session with no questionnaire. The asymmetry is deliberate: a
    false refusal costs an operator one retry, and a false permit puts a
    meeting on air against a questionnaire nobody approved, which is the
    situation IG-10 exists to prevent and which cannot be walked back once the
    brand owner has started answering.
    """
    if backend is None:
        logger.warning("ig_10_no_backend", session_id=session_id)
        return LiveVerdict(allowed=False, reason=UNREACHABLE_REASON)

    body = await backend.live_precheck(tenant_id=tenant_id, session_id=session_id)
    if body is None:
        logger.warning("ig_10_backend_unreachable", session_id=session_id)
        return LiveVerdict(allowed=False, reason=UNREACHABLE_REASON)

    if body.get("approved") is True:
        return LiveVerdict(allowed=True)

    # Django's wording, not ours. It knows which questionnaire and what state
    # it is in, and re-deriving the sentence here is how the two drift.
    reason = str(body.get("reason") or "").strip() or (
        "This session has no approved questionnaire. Approve one in "
        "preparation before starting the meeting."
    )
    logger.info(
        "ig_10_refused",
        session_id=session_id,
        questionnaire_status=body.get("questionnaire_status"),
    )
    return LiveVerdict(allowed=False, reason=reason)


def as_rule(verdict: LiveVerdict) -> Callable[[Any, Any], ChainVerdict]:
    """Adapt a pre-computed LiveVerdict to the chain's synchronous Rule signature.

    Mirrors consent_gate.as_rule — the live verdict is evaluated before the
    chain runs and closed over here so the chain can emit EVT-004.
    """

    def _evaluate(payload: Any, context: Any) -> ChainVerdict:  # noqa: ARG001
        if verdict.allowed:
            return ChainVerdict(rule_id=RULE_ID, action=Action.PASS)
        return ChainVerdict(
            rule_id=RULE_ID,
            action=Action.BLOCK,
            detail=verdict.reason,
        )

    return _evaluate
