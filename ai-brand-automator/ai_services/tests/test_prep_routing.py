"""C-01 (Django half) · routing prep chat turns to the agent.

Lives in ``ai_services/tests/`` rather than the card's ``apps/chat/tests/``
because there is no ``apps/chat`` — chat is the ``ai_services`` app, and the
tests sit beside the code they cover.

The load-bearing assertion is AC-1's second half: **non-prep turns route
exactly as they do today.** A prep intent that swallowed ordinary questions
would be a worse regression than prep not working at all, because it would
break a feature people already rely on.
"""

from __future__ import annotations

import pytest

from ai_services.onboarding_agent import (
    ERR_AGENT_UNAVAILABLE,
    UNAVAILABLE_MESSAGE,
    AgentResult,
    dispatch_prep_turn,
    reset_breaker,
)
from ai_services.services import GeminiAIService

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _fresh_breaker():
    """The breaker is process state; a test that trips it would leak into the
    next one and make failures depend on ordering."""
    reset_breaker()
    yield
    reset_breaker()


# ── AC-1 · prep intents are recognised ───────────────────────────────


@pytest.mark.parametrize(
    "message",
    [
        "prepare questions for the onboarding meeting",
        "help me prep for the onboarding call tomorrow",
        "what should I ask on the discovery call",
        "build a questionnaire for the onboarding session",
        "draft an agenda for the kickoff call",
    ],
)
def test_prep_messages_are_classified_as_prep(message):
    assert GeminiAIService.classify_intent(message)["intent"] == "onboarding_prep"


# ── AC-1 · everything else routes exactly as before ──────────────────


@pytest.mark.parametrize(
    "message,expected",
    [
        # RAG queries that merely *mention* onboarding must stay RAG. This is
        # the case a one-signal keyword match would have hijacked.
        ("summarize the onboarding document", "rag"),
        ("what does the uploaded file say about onboarding", "rag"),
        # Pipeline work is unchanged.
        ("write a blog post about our coffee and schedule it", "pipeline"),
        # And ordinary conversation stays conversation.
        ("what is the weather like", "conversation"),
        ("thanks, that helps", "conversation"),
        # "prepare" alone is not onboarding prep. Note this is
        # "conversation", not "pipeline" — I expected the latter and was
        # wrong; see the docstring.
        ("prepare a social media post", "conversation"),
    ],
)
def test_non_prep_intents_unchanged(message, expected):
    """The card's named case. Prep is recognised on two signals — a subject
    *and* an action — precisely so these keep their existing routes.

    Every expected value here was captured by running the classifier with the
    prep branch stashed, not by reading the keyword lists. That caught one of
    my own guesses: "prepare a social media post" classifies as conversation,
    not pipeline. Asserting what I assumed would have written a wrong baseline
    into the regression guard for this AC.
    """
    assert GeminiAIService.classify_intent(message)["intent"] == expected


def test_prep_needs_both_a_subject_and_an_action():
    """Either signal alone is someone talking about something else."""
    assert (
        GeminiAIService.classify_intent("tell me about onboarding")["intent"]
        != "onboarding_prep"
    )
    assert (
        GeminiAIService.classify_intent("prepare the quarterly report")["intent"]
        != "onboarding_prep"
    )


# ── AC-3 · the agent being down degrades honestly ────────────────────


def test_an_unreachable_agent_names_preparation_as_unavailable(settings):
    """AC-3: not "a generic error or a silent hang".

    Pointed at a port with nothing behind it — a real closed socket rather
    than a simulated outage, so the timeout path is the one production takes.
    """
    settings.OIA_SERVICE_URL = "http://127.0.0.1:1"

    import os

    os.environ["OIA_SERVICE_URL"] = "http://127.0.0.1:1"
    result = dispatch_prep_turn(
        tenant_id="t-1",
        user_id="u-1",
        role="ADMIN",
        trace_id="trace-1",
        chat_session_id="chat-1",
        prompt="prepare questions for the onboarding meeting",
    )

    assert result.ok is False
    assert result.code == ERR_AGENT_UNAVAILABLE == "ERR-19"
    assert "preparation" in result.message.lower()
    assert "manual" in result.message.lower(), "no manual path was suggested"


def test_the_failure_message_is_not_a_stack_trace():
    """An operator sees this in a chat bubble. It has to read as a sentence."""
    assert UNAVAILABLE_MESSAGE.endswith(".")
    for leak in ("Traceback", "Exception", "127.0.0.1", "ERR-"):
        assert leak not in UNAVAILABLE_MESSAGE


def test_a_failure_never_raises():
    """An exception escaping the dispatcher would break the whole chat turn,
    not just its prep half."""
    import os

    os.environ["OIA_SERVICE_URL"] = "http://127.0.0.1:1"
    result = dispatch_prep_turn(
        tenant_id="t-1",
        user_id="u-1",
        role="ADMIN",
        trace_id="trace-1",
        chat_session_id="chat-1",
        prompt="prep the onboarding call",
    )
    assert isinstance(result, AgentResult)


def test_the_breaker_opens_after_repeated_failures():
    """A dependency that failed three times will almost certainly fail the
    fourth, and making the operator wait out the connect timeout each time is
    worse than telling them at once."""
    import os
    import time

    from ai_services.onboarding_agent import BREAKER_THRESHOLD

    os.environ["OIA_SERVICE_URL"] = "http://127.0.0.1:1"

    def call():
        return dispatch_prep_turn(
            tenant_id="t-1",
            user_id="u-1",
            role="ADMIN",
            trace_id="trace-1",
            chat_session_id="chat-1",
            prompt="prep the onboarding call",
        )

    for _ in range(BREAKER_THRESHOLD):
        assert call().ok is False

    started = time.monotonic()
    assert call().ok is False
    assert (
        time.monotonic() - started < 0.1
    ), "the breaker did not short-circuit — the caller waited on the network"


# ── The role comes from the membership, never a request body ─────────


@pytest.mark.django_db
def test_the_role_is_read_from_the_membership():
    """§15: roles come from the verified claim, never from a body or a header
    the client controls."""
    from django.contrib.auth.models import User

    from ai_services.views import _agent_role_for
    from tenants.models import Membership, Tenant

    tenant = Tenant.objects.create(name="C01 Co", schema_name="c01_role")
    user = User.objects.create_user("c01_user", "c01@test.com", "TestPass123!")
    Membership.objects.create(user=user, tenant=tenant, role=Membership.Role.EDITOR)

    assert _agent_role_for(user, tenant) == "EDITOR"


@pytest.mark.django_db
def test_a_user_with_no_membership_is_a_viewer():
    """Least privilege on the way out: an unknown role must not become ADMIN
    in the agent's tenant_context."""
    from django.contrib.auth.models import User

    from ai_services.views import _agent_role_for
    from tenants.models import Tenant

    tenant = Tenant.objects.create(name="C01 None", schema_name="c01_none")
    user = User.objects.create_user("c01_none", "none@test.com", "TestPass123!")

    assert _agent_role_for(user, tenant) == "VIEWER"
