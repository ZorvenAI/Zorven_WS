"""C-02 · the §18.2 breakers and their configuration.

Named by the C-02 card. The degradation case it specifies —
``test_tavily_open_produces_degraded_brief`` — needs the skill, so it lands in
PR 2; this file covers the mechanism that case depends on.

No mocks, and no patched clocks either. Timing is exercised by configuring a
breaker with a short reset timeout and actually waiting, because the thing
worth proving is that the state machine reads a real monotonic clock
correctly. A frozen clock would prove only that the arithmetic matches itself.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
import yaml

from app.circuit_breaker.breaker import (
    CONFIG_PATH,
    BreakerConfig,
    BreakerRegistry,
    CircuitBreaker,
    CircuitBreakerOpen,
    State,
)

pytestmark = pytest.mark.unit

#: §18.2 names exactly these. A missing one is a dependency with no defined
#: degraded behaviour, which is the outage the section exists to prevent.
EXPECTED_DEPENDENCIES = {"stt", "llm", "vision", "backend", "poi", "gcs", "tavily"}


def make(**overrides) -> CircuitBreaker:
    base = dict(
        name="test",
        failure_threshold=3,
        window_seconds=60,
        success_threshold=1,
        half_open_max_calls=1,
        reset_timeout_seconds=60,
        degraded_mode="SKIP_RESEARCH",
        user_message="degraded",
    )
    base.update(overrides)
    return CircuitBreaker(BreakerConfig(**base))


# ── The configuration file ───────────────────────────────────────────


def test_all_seven_dependencies_are_declared():
    assert set(BreakerRegistry().names()) == EXPECTED_DEPENDENCIES


def test_the_shipped_config_matches_the_design():
    """§18.2 gives this file verbatim, and F-06 and N-03 both read it later.

    Asserting the tavily row specifically because C-02's AC-3 depends on these
    exact numbers: three failures in sixty seconds, one success to recover.
    """
    tavily = BreakerRegistry().get("tavily").config

    assert tavily.failure_threshold == 3
    assert tavily.window_seconds == 60
    assert tavily.success_threshold == 1
    assert tavily.degraded_mode == "SKIP_RESEARCH"
    assert tavily.user_message == (
        "Web research unavailable — questionnaire generated from what you provided."
    )


def test_every_dependency_has_a_degraded_mode():
    registry = BreakerRegistry()

    for name in registry.names():
        assert registry.get(name).config.degraded_mode, f"{name} degrades to nothing"


def test_a_null_user_message_is_preserved_as_none():
    """§18.2 marks poi's message null — "invisible to the user, by design".

    The distinction matters: an empty string would render as a blank banner,
    while None means "show nothing".
    """
    assert BreakerRegistry().get("poi").config.user_message is None


def test_defaults_fill_in_unspecified_fields():
    """poi overrides three fields and inherits half_open_max_calls and
    reset_timeout_seconds from defaults."""
    poi = BreakerRegistry().get("poi").config

    assert poi.failure_threshold == 3  # overridden
    assert poi.half_open_max_calls == 1  # inherited
    assert poi.reset_timeout_seconds == 60  # inherited


def test_an_unknown_dependency_is_an_error_not_a_new_breaker():
    """A typo in circuit_breaker_dependency must fail loudly. Creating one on
    demand would silently disable protection for the real dependency."""
    with pytest.raises(KeyError, match="no breaker declared"):
        BreakerRegistry().get("tavilly")


def test_a_dependency_without_a_degraded_mode_is_rejected(tmp_path: Path):
    bad = tmp_path / "circuit_breakers.yaml"
    bad.write_text(
        yaml.safe_dump(
            {
                "defaults": {
                    "failure_threshold": 5,
                    "window_seconds": 30,
                    "success_threshold": 2,
                },
                "dependencies": {"tavily": {"user_message": "x"}},
            }
        )
    )

    with pytest.raises(ValueError, match="declares no degraded_mode"):
        BreakerRegistry(bad)


def test_the_config_path_resolves_to_a_real_file():
    """The path is built from __file__ and would break silently if the package
    moved — the registry would then raise at import time in production."""
    assert CONFIG_PATH.is_file(), CONFIG_PATH


# ── The state machine ────────────────────────────────────────────────


def test_a_breaker_starts_closed():
    assert make().state is State.CLOSED
    assert make().is_open is False


def test_it_opens_at_the_threshold_and_not_before():
    breaker = make(failure_threshold=3)

    breaker.record_failure()
    breaker.record_failure()
    assert breaker.is_open is False, "opened early"

    breaker.record_failure()
    assert breaker.is_open is True


def test_success_clears_accumulated_failures():
    """The threshold counts current trouble. A dependency serving again should
    not carry old failures toward opening."""
    breaker = make(failure_threshold=3)

    breaker.record_failure()
    breaker.record_failure()
    breaker.record_success()
    breaker.record_failure()
    breaker.record_failure()

    assert breaker.is_open is False


def test_failures_outside_the_window_do_not_count():
    breaker = make(failure_threshold=3, window_seconds=1)

    breaker.record_failure()
    breaker.record_failure()
    time.sleep(1.1)
    breaker.record_failure()

    assert breaker.is_open is False, "a stale failure was counted"


def test_an_open_breaker_refuses_the_call_with_the_degraded_context():
    """AC-3 needs the mode and the message to build a brief that says why it
    is thin, without re-reading the config."""
    breaker = make(failure_threshold=1)
    breaker.record_failure()

    with pytest.raises(CircuitBreakerOpen) as caught:
        breaker.before_call()

    assert caught.value.dependency == "test"
    assert caught.value.degraded_mode == "SKIP_RESEARCH"
    assert caught.value.user_message == "degraded"


def test_it_moves_to_half_open_after_the_reset_timeout():
    breaker = make(failure_threshold=1, reset_timeout_seconds=1)
    breaker.record_failure()
    assert breaker.state is State.OPEN

    time.sleep(1.1)

    assert breaker.state is State.HALF_OPEN
    assert breaker.is_open is False, "the trial call was refused"


def test_half_open_admits_only_its_trial_budget():
    """Without an atomic claim, a burst of callers would all slip through the
    instant the timeout elapsed — the stampede HALF_OPEN prevents."""
    breaker = make(failure_threshold=1, reset_timeout_seconds=1, half_open_max_calls=1)
    breaker.record_failure()
    time.sleep(1.1)

    breaker.before_call()  # the one trial

    with pytest.raises(CircuitBreakerOpen):
        breaker.before_call()


def test_a_failed_trial_reopens_immediately():
    """The dependency was already known bad; one failed trial is evidence it
    still is. Counting to the threshold again would send more doomed calls."""
    breaker = make(failure_threshold=3, reset_timeout_seconds=1)
    breaker.record_failure()
    breaker.record_failure()
    breaker.record_failure()
    time.sleep(1.1)
    assert breaker.state is State.HALF_OPEN

    breaker.before_call()
    breaker.record_failure()

    assert breaker.state is State.OPEN


def test_sustained_success_closes_it():
    breaker = make(failure_threshold=1, reset_timeout_seconds=1, success_threshold=2)
    breaker.record_failure()
    time.sleep(1.1)

    breaker.record_success()
    assert breaker.state is State.HALF_OPEN, "closed on one success of two"

    breaker.record_success()
    assert breaker.state is State.CLOSED
    assert breaker.is_open is False


def test_the_full_cycle():
    """CLOSED → OPEN → HALF_OPEN → CLOSED, the path a real recovery takes."""
    breaker = make(failure_threshold=2, reset_timeout_seconds=1, success_threshold=1)

    assert breaker.state is State.CLOSED
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state is State.OPEN

    time.sleep(1.1)
    assert breaker.state is State.HALF_OPEN

    breaker.before_call()
    breaker.record_success()
    assert breaker.state is State.CLOSED

    # And it can open again — the counters were reset, not left at threshold.
    breaker.record_failure()
    assert breaker.is_open is False
    breaker.record_failure()
    assert breaker.is_open is True


def test_concurrent_failures_are_not_lost():
    """FastAPI serves requests concurrently, so two can land in record_failure
    at once. A lost increment opens the breaker late — exactly when it
    matters. Real threads rather than a reasoned argument about the lock.
    """
    breaker = make(failure_threshold=50, window_seconds=60)
    barrier = threading.Barrier(10)

    def hammer():
        barrier.wait()
        for _ in range(5):
            breaker.record_failure()

    threads = [threading.Thread(target=hammer) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert breaker.is_open is True, "increments were lost under concurrency"
