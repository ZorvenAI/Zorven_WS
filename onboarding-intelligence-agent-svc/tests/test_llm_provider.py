"""C-02 · the Gemini provider and its breaker wiring.

The unit cases need no network: a missing key, an open breaker and an empty
completion are all decided before or after the call.

The integration case makes a **real Gemini call**. It skips when no key is
configured, because that is the honest state of a laptop or a CI runner
without one — but it *fails* when ``OIA_TEST_GEMINI`` is set, following the
same asymmetry the Kafka round-trip tests use. A green run that silently
covered nothing is worse than an honest red.
"""

from __future__ import annotations

import os

import pytest

from app.circuit_breaker.breaker import BreakerConfig, CircuitBreaker, State
from app.providers.llm import DEFAULT_MODEL, LLMProvider, LLMUnavailable


def breaker(**overrides) -> CircuitBreaker:
    base = dict(
        name="llm",
        failure_threshold=5,
        window_seconds=30,
        success_threshold=2,
        half_open_max_calls=1,
        reset_timeout_seconds=60,
        degraded_mode="MANUAL_CHECKBOXES",
        user_message=(
            "Suggestions paused. Check questions off manually — nothing is lost."
        ),
    )
    base.update(overrides)
    return CircuitBreaker(BreakerConfig(**base))


# ── Decided without a network call ───────────────────────────────────


@pytest.mark.unit
async def test_no_api_key_degrades_rather_than_crashing():
    provider = LLMProvider("", breaker=breaker())

    assert provider.configured is False
    with pytest.raises(LLMUnavailable, match="no Gemini API key"):
        await provider.generate("hello")


@pytest.mark.unit
async def test_a_missing_key_does_not_consume_the_breaker():
    """A keyless environment should report a configuration gap, not an
    outage it will then wait out."""
    brk = breaker(failure_threshold=1)

    with pytest.raises(LLMUnavailable):
        await LLMProvider("", breaker=brk).generate("hello")

    assert brk.state is State.CLOSED


@pytest.mark.unit
async def test_an_open_breaker_carries_the_configured_message():
    """§18.2 puts the operator-facing string in config so it is tunable
    without a deploy; it must come from there, not be re-typed here."""
    brk = breaker(failure_threshold=1)
    brk.record_failure()

    with pytest.raises(LLMUnavailable) as caught:
        await LLMProvider("key", breaker=brk).generate("hello")

    assert caught.value.degraded_mode == "MANUAL_CHECKBOXES"
    assert "Check questions off manually" in caught.value.reason


@pytest.mark.unit
def test_the_fleet_model_is_the_default():
    """Root CLAUDE.md sets gemini-3.5-flash as the fleet default and
    ai_services/services.py uses it. A silent divergence here would make OIA's
    output differ from the rest of the platform for no stated reason."""
    assert DEFAULT_MODEL == "gemini-3.5-flash"
    assert LLMProvider("key").model_name == "gemini-3.5-flash"


# ── An empty completion is a failure, not an empty answer ────────────


@pytest.mark.unit
def test_an_empty_completion_raises():
    """A safety block returns a response whose text is empty. Returning ""
    would let a caller build a brief out of nothing and present it as
    researched."""

    class Blocked:
        text = ""

    with pytest.raises(ValueError, match="no text"):
        LLMProvider._text_of(Blocked())


@pytest.mark.unit
def test_a_whitespace_completion_raises():
    class Whitespace:
        text = "   \n  "

    with pytest.raises(ValueError, match="no text"):
        LLMProvider._text_of(Whitespace())


@pytest.mark.unit
def test_a_response_with_no_text_attribute_raises():
    with pytest.raises(ValueError, match="no text"):
        LLMProvider._text_of(object())


# ── The real thing ───────────────────────────────────────────────────


@pytest.mark.integration
async def test_a_real_generation_round_trip():
    """A real call to Gemini with the real SDK.

    Deliberately not asserting on the content — the model is not
    deterministic. What is worth proving is that the key, the SDK, the async
    entry point and the breaker all line up, which is exactly the set of
    things a mocked client cannot tell you.
    """
    key = os.environ.get("OIA_GEMINI_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
    if not key:
        if os.environ.get("OIA_TEST_GEMINI"):
            pytest.fail(
                "OIA_TEST_GEMINI is set but no OIA_GEMINI_KEY/GOOGLE_API_KEY "
                "is configured — this test would silently cover nothing"
            )
        pytest.skip("no Gemini key configured")

    brk = breaker()
    provider = LLMProvider(key, breaker=brk)

    text = await provider.generate("Reply with the single word: ready")

    assert text.strip(), "the model returned nothing"
    assert brk.state is State.CLOSED
