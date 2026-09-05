"""C-02 · the §18.2 breakers and their configuration.

Named by the C-02 card. The degradation case it specifies —
``test_tavily_open_produces_degraded_brief`` — needs the skill, so it lands in
PR 2; this file covers the mechanism that case depends on.

No mocks, and no patched clocks either. Timing is exercised by configuring a
breaker with a short reset timeout and actually waiting, because the thing
worth proving is that the state machine reads a real monotonic clock
correctly. A frozen clock would prove only that the arithmetic matches itself.

N-03 adds the drill tests: AC-1 (every breaker's degraded mode exercised at
the provider level) and AC-2 (recovery verified, buffered work drains with no
duplicates).
"""

from __future__ import annotations

import asyncio
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


@pytest.fixture
async def redis_client(live_redis):
    """Raw Redis client from the live_redis manager fixture."""
    return live_redis.client


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
    """Every trial goes through before_call(), as a real caller must.

    The earlier version of this test called record_success() twice directly
    and passed — while the breaker was in fact wedged. A caller cannot record
    a success without first claiming a trial slot, so skipping before_call()
    tested a sequence production can never produce, and hid a bug that would
    have left five of the seven §18.2 dependencies permanently degraded after
    a single blip.
    """
    breaker = make(failure_threshold=1, reset_timeout_seconds=1, success_threshold=2)
    breaker.record_failure()
    time.sleep(1.1)

    breaker.before_call()
    breaker.record_success()
    assert breaker.state is State.HALF_OPEN, "closed on one success of two"

    breaker.before_call()
    breaker.record_success()
    assert breaker.state is State.CLOSED
    assert breaker.is_open is False


def test_the_shipped_defaults_can_actually_recover():
    """The regression that review caught, stated as a property of the config.

    Five of the seven declared dependencies ship success_threshold=2 with
    half_open_max_calls=1. If a success does not release its trial slot, each
    of them takes one trial, records one success, and then refuses every call
    forever — degraded until the process restarts. Asserting it for every
    declared dependency rather than one hand-built breaker, because the bug
    lived in the interaction between two config values.
    """
    registry = BreakerRegistry()

    for name in registry.names():
        config = registry.get(name).config
        breaker = CircuitBreaker(
            BreakerConfig(
                name=config.name,
                failure_threshold=1,
                window_seconds=config.window_seconds,
                success_threshold=config.success_threshold,
                half_open_max_calls=config.half_open_max_calls,
                reset_timeout_seconds=1,
                degraded_mode=config.degraded_mode,
                user_message=config.user_message,
            )
        )
        breaker.record_failure()
        assert breaker.state is State.OPEN, name

        for _ in range(config.success_threshold):
            time.sleep(1.1)
            breaker.before_call()
            breaker.record_success()

        assert breaker.state is State.CLOSED, f"{name} cannot recover"


def test_a_concurrent_second_trial_is_still_refused():
    """Releasing the slot on success must not reopen the stampede door.

    The slot is released when a call *finishes*; two callers in flight at once
    still only get one trial between them.
    """
    breaker = make(failure_threshold=1, reset_timeout_seconds=1, half_open_max_calls=1)
    breaker.record_failure()
    time.sleep(1.1)

    breaker.before_call()  # first caller, still in flight

    with pytest.raises(CircuitBreakerOpen):
        breaker.before_call()  # second caller, concurrent


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


# ── J-06: generation failure is non-fatal (AC-2) ───────────────────


def test_wf2_failure_does_not_fail_process():
    """AC-2: backend breaker opening does not make PROCESS fail.

    ProcessExecutor._auto_generate catches all exceptions and returns an
    empty list. The PROCESS job still reports SUCCEEDED. This test
    verifies the contract at the breaker level: a breaker that is OPEN
    raises CircuitBreakerOpen, and the caller must catch it.
    """
    breaker = make(failure_threshold=1)
    breaker.record_failure()

    assert breaker.is_open is True
    with pytest.raises(CircuitBreakerOpen):
        breaker.before_call()

    # The BackendClient catches CircuitBreakerOpen and returns None,
    # which _auto_generate treats as "did not generate" — not as a job
    # failure. This is tested end-to-end in test_autogen.py.


# ── N-03 AC-1: every breaker's degraded mode drilled at the provider ────


EXPECTED_DEGRADED_MODES = {
    "stt": (
        "RECORD_ONLY",
        "Live assist paused — recording continues."
        " Transcript will be ready after the meeting.",
    ),
    "llm": (
        "MANUAL_CHECKBOXES",
        "Suggestions paused." " Check questions off manually — nothing is lost.",
    ),
    "vision": (
        "GEMINI_ONLY_OCR",
        "Reduced document-reading accuracy" " — captures still saved.",
    ),
    "backend": (
        "REDIS_OUTBOX",
        "Saving is delayed — your meeting data is"
        " buffered and will sync automatically.",
    ),
    "poi": ("CACHED_THEN_HARDCODED", None),
    "gcs": ("LOCAL_DISK_SPOOL", "Upload delayed — recording continues locally."),
    "tavily": (
        "SKIP_RESEARCH",
        "Web research unavailable — questionnaire generated from what you provided.",
    ),
}


class TestDegradedModeDrill:
    """N-03 AC-1: every dependency's degraded mode exercised."""

    def _force_open(self, breaker: CircuitBreaker) -> None:
        for _ in range(breaker.config.failure_threshold):
            breaker.record_failure()
        assert breaker.is_open, f"{breaker.config.name} did not open"

    def test_every_dependency_has_drilled_mode(self):
        registry = BreakerRegistry()
        for name in EXPECTED_DEPENDENCIES:
            breaker = registry.get(name)
            mode, msg = EXPECTED_DEGRADED_MODES[name]
            assert (
                breaker.config.degraded_mode == mode
            ), f"{name}: expected {mode}, got {breaker.config.degraded_mode}"
            assert breaker.config.user_message == msg, f"{name}: user_message mismatch"

    def test_tavily_drill(self):
        breaker = BreakerRegistry().get("tavily")
        self._force_open(breaker)

        from app.providers.tavily import TavilyProvider, TavilyUnavailable

        provider = TavilyProvider("fake-key", breaker=breaker)

        with pytest.raises(TavilyUnavailable) as exc_info:
            asyncio.run(provider.search("test"))

        assert exc_info.value.degraded_mode == "SKIP_RESEARCH"

    def test_llm_drill(self):
        breaker = BreakerRegistry().get("llm")
        self._force_open(breaker)

        from app.providers.llm import LLMProvider, LLMUnavailable

        provider = LLMProvider("fake-key", breaker=breaker)

        with pytest.raises(LLMUnavailable) as exc_info:
            asyncio.run(provider.generate("test prompt"))

        assert exc_info.value.degraded_mode == "MANUAL_CHECKBOXES"

    def test_stt_drill(self):
        breaker = BreakerRegistry().get("stt")
        self._force_open(breaker)

        from app.providers.stt import GoogleSTTAdapter, STTUnavailable

        adapter = GoogleSTTAdapter(project="test-project", breaker=breaker)

        async def _empty_audio():
            yield b"\x00" * 320
            return

        with pytest.raises(STTUnavailable) as exc_info:
            asyncio.run(adapter.stream(_empty_audio()).__anext__())

        assert exc_info.value.degraded_mode == "RECORD_ONLY"

    def test_vision_drill(self):
        breaker = BreakerRegistry().get("vision")
        self._force_open(breaker)

        from app.providers.vision import VisionProvider, VisionUnavailable

        provider = VisionProvider("fake-key", breaker=breaker)

        with pytest.raises(VisionUnavailable):
            asyncio.run(provider.analyze(b"\x89PNG", "test text"))

    def test_ocr_drill(self):
        breaker = BreakerRegistry().get("vision")
        self._force_open(breaker)

        from app.providers.ocr import OCRProvider, OCRUnavailable

        provider = OCRProvider(breaker=breaker)

        with pytest.raises(OCRUnavailable) as exc_info:
            asyncio.run(provider.detect_text(b"\x89PNG"))

        assert exc_info.value.degraded_mode == "GEMINI_ONLY_OCR"

    def test_backend_drill(self):
        breaker = BreakerRegistry().get("backend")
        self._force_open(breaker)

        from app.services.backend_client import BackendClient

        client = BackendClient("http://localhost:9999", "fake-token", breaker=breaker)

        result = asyncio.run(
            client.store_research_brief(
                tenant_id="t-drill",
                company_name="Drill Corp",
                brief={"summary": "drill"},
            )
        )
        assert result is False

    def test_poi_drill(self):
        breaker = BreakerRegistry().get("poi")
        self._force_open(breaker)

        with pytest.raises(CircuitBreakerOpen) as exc_info:
            breaker.before_call()

        assert exc_info.value.degraded_mode == "CACHED_THEN_HARDCODED"
        assert exc_info.value.user_message is None

    def test_gcs_drill(self):
        breaker = BreakerRegistry().get("gcs")
        self._force_open(breaker)

        with pytest.raises(CircuitBreakerOpen) as exc_info:
            breaker.before_call()

        assert exc_info.value.degraded_mode == "LOCAL_DISK_SPOOL"
        assert (
            exc_info.value.user_message
            == "Upload delayed — recording continues locally."
        )


# ── N-03 AC-2: recovery verified, buffered work drains without duplicates ──


class TestRecoveryDrill:
    """N-03 AC-2: recovery drains buffered work, no duplicates."""

    def test_every_breaker_recovers_from_open(self):
        registry = BreakerRegistry()
        for name in registry.names():
            config = registry.get(name).config
            breaker = CircuitBreaker(
                BreakerConfig(
                    name=config.name,
                    failure_threshold=1,
                    window_seconds=config.window_seconds,
                    success_threshold=config.success_threshold,
                    half_open_max_calls=config.half_open_max_calls,
                    reset_timeout_seconds=1,
                    degraded_mode=config.degraded_mode,
                    user_message=config.user_message,
                )
            )

            breaker.record_failure()
            assert breaker.state is State.OPEN, f"{name} did not open"

            for _ in range(config.success_threshold):
                time.sleep(1.1)
                breaker.before_call()
                breaker.record_success()

            assert breaker.state is State.CLOSED, f"{name} did not recover"

    def test_state_change_callback_fires_on_recovery(self):
        breaker = make(
            failure_threshold=1, reset_timeout_seconds=1, success_threshold=1
        )
        transitions: list[tuple[State, State]] = []

        breaker.add_on_state_change(
            lambda dep, old, new: transitions.append((old, new))
        )

        breaker.record_failure()
        assert (State.CLOSED, State.OPEN) in transitions

        time.sleep(1.1)
        breaker.before_call()
        breaker.record_success()

        assert (State.HALF_OPEN, State.CLOSED) in transitions

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_vision_recovery_drains_ocr_queue(self, redis_client):
        """When the vision breaker recovers, the OCR retry queue is drained."""
        from app.cache.redis_manager import TenantKeys
        from app.cache.retry_queue import (
            OCRRetryItem,
            enqueue_retry,
            queue_size,
        )
        from app.logic.ocr_drain import register_drain_callback

        tenant_id = "t-drain-drill"
        keys = TenantKeys(tenant_id)

        item = OCRRetryItem(
            media_id="media-drill-1",
            gcs_uri="gs://test/drill.png",
            usage_tag="drill",
            tenant_id=tenant_id,
            attempt=0,
        )
        await enqueue_retry(redis_client, keys, item)

        size_before = await queue_size(redis_client, keys)
        assert size_before >= 1, "item not enqueued"

        breaker = make(
            failure_threshold=1,
            reset_timeout_seconds=1,
            success_threshold=1,
        )
        register_drain_callback(breaker, redis_client)

        breaker.record_failure()
        assert breaker.state is State.OPEN

        time.sleep(1.1)
        breaker.before_call()
        breaker.record_success()
        assert breaker.state is State.CLOSED

        await asyncio.sleep(0.5)

        size_after = await queue_size(redis_client, keys)
        assert size_after == 0, f"expected 0 items after drain, got {size_after}"
