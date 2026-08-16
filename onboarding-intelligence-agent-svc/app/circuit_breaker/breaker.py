"""Per-dependency circuit breakers.

Design §18.2 · implemented by story C-02.

Scaffolded by A-05, which named A-06 as the implementer. A-06's acceptance
criteria cover the registry, the guardrail chain, the RBAC evaluator and the
skill interfaces, and never mention breakers — so this stayed a stub through
A-06's completion and no later story picked it up. C-02 is the first story
that cannot be delivered without one (AC-3 requires the tavily breaker in the
open state), so it lands here.

**State is per-process, deliberately.** Cloud Run runs several instances and
each keeps its own view, so a dependency failing for everyone opens N breakers
independently rather than one shared one. That is the fleet pattern and it is
the right trade here: a shared breaker in Redis would add a network hop to
every call on the path it is supposed to be protecting, and would itself fail
when Redis does. The cost is that recovery is per-instance and slightly
staggered, which is invisible to an operator.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "circuit_breakers.yaml"


class State(str, Enum):
    """The three states of §18.2's breaker.

    HALF_OPEN is not a formality. Going straight from OPEN back to CLOSED on a
    timer would send the full call volume at a dependency that has not been
    shown to be healthy; HALF_OPEN admits a bounded number of trial calls and
    promotes only on sustained success.
    """

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass(frozen=True)
class BreakerConfig:
    """One dependency's row in config/circuit_breakers.yaml."""

    name: str
    failure_threshold: int
    window_seconds: int
    success_threshold: int
    half_open_max_calls: int
    reset_timeout_seconds: int
    degraded_mode: str
    #: None means the degradation is invisible to the operator by design
    #: (§18.2 says so of `poi`), not that a message was forgotten.
    user_message: str | None


class CircuitBreakerOpen(Exception):
    """Raised instead of calling a dependency whose breaker is open.

    Carries the degraded mode and the operator-facing message so a caller can
    degrade without re-reading the config — AC-3 needs both to build a brief
    that says *why* it is thin.
    """

    def __init__(self, config: BreakerConfig) -> None:
        super().__init__(f"circuit breaker open for {config.name}")
        self.dependency = config.name
        self.degraded_mode = config.degraded_mode
        self.user_message = config.user_message


@dataclass
class CircuitBreaker:
    """One dependency's breaker.

    Thread-safe: FastAPI runs sync dependencies in a threadpool and the
    provider calls this from async code, so two requests can land in
    ``record_failure`` concurrently. Without the lock the failure count can
    lose an increment and the breaker opens late, which is precisely when it
    matters.
    """

    config: BreakerConfig
    _state: State = State.CLOSED
    _failures: list[float] = field(default_factory=list)
    _successes: int = 0
    _opened_at: float = 0.0
    _half_open_calls: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _on_state_change: Callable[[str, State, State], None] | None = field(
        default=None, repr=False
    )

    def set_on_state_change(self, cb: Callable[[str, State, State], None]) -> None:
        """Register ``cb(dependency_name, old_state, new_state)``."""
        self._on_state_change = cb

    # ── State, with the timeout applied lazily ───────────────────────

    @property
    def state(self) -> State:
        """The current state, moving OPEN → HALF_OPEN once the timeout passes.

        Computed on read rather than by a background timer: a timer would keep
        the process awake and would have to be cancelled on shutdown, and
        nothing observes a breaker except a caller about to use it.
        """
        with self._lock:
            return self._state_locked()

    def _state_locked(self) -> State:
        if self._state is State.OPEN:
            if time.monotonic() - self._opened_at >= self.config.reset_timeout_seconds:
                self._state = State.HALF_OPEN
                self._half_open_calls = 0
                self._successes = 0
        return self._state

    @property
    def is_open(self) -> bool:
        """True when a call must not be attempted.

        HALF_OPEN counts as open once its trial budget is spent — otherwise a
        burst of concurrent callers would all slip through the moment the
        reset timeout elapsed, which is the stampede HALF_OPEN exists to
        prevent.
        """
        with self._lock:
            state = self._state_locked()
            if state is State.OPEN:
                return True
            if state is State.HALF_OPEN:
                return self._half_open_calls >= self.config.half_open_max_calls
            return False

    # ── Outcomes ─────────────────────────────────────────────────────

    def record_success(self) -> None:
        with self._lock:
            state = self._state_locked()
            if state is State.HALF_OPEN:
                self._successes += 1
                # Release the trial slot. before_call() claimed it to stop a
                # stampede of *concurrent* callers; a call that has come back
                # successfully is finished with it, and holding it would block
                # the next sequential trial.
                #
                # Without this the breaker wedges. Every dependency whose
                # success_threshold exceeds half_open_max_calls — five of the
                # seven in §18.2 ship 2 and 1 — would take its one trial,
                # record one success, and then refuse every subsequent call
                # forever, never reaching the threshold that closes it. A
                # single blip would degrade the dependency until the process
                # restarted.
                self._half_open_calls = max(0, self._half_open_calls - 1)
                if self._successes >= self.config.success_threshold:
                    self._reset_locked()
            else:
                # A success in CLOSED clears the window: the threshold counts
                # *consecutive-ish* trouble, and a dependency that is serving
                # again should not carry old failures toward opening.
                self._failures.clear()

    def record_failure(self) -> None:
        with self._lock:
            state = self._state_locked()
            now = time.monotonic()

            if state is State.HALF_OPEN:
                # One failed trial is enough. The dependency was already known
                # bad; a trial that fails is evidence it still is.
                self._open_locked(now)
                return

            cutoff = now - self.config.window_seconds
            self._failures = [t for t in self._failures if t >= cutoff]
            self._failures.append(now)

            if len(self._failures) >= self.config.failure_threshold:
                self._open_locked(now)

    def before_call(self) -> None:
        """Raise if the call must not be made; otherwise consume a trial slot.

        Callers should use this rather than reading :attr:`is_open`, because
        the check and the trial-slot claim have to be one atomic step. Two
        concurrent callers both seeing "half open, 0 calls used" would each
        proceed and defeat ``half_open_max_calls``.
        """
        with self._lock:
            state = self._state_locked()
            if state is State.OPEN:
                raise CircuitBreakerOpen(self.config)
            if state is State.HALF_OPEN:
                if self._half_open_calls >= self.config.half_open_max_calls:
                    raise CircuitBreakerOpen(self.config)
                self._half_open_calls += 1

    # ── Internals (call with the lock held) ──────────────────────────

    def _open_locked(self, now: float) -> None:
        prev = self._state
        self._state = State.OPEN
        self._opened_at = now
        self._failures.clear()
        self._successes = 0
        self._half_open_calls = 0
        if self._on_state_change and prev is not State.OPEN:
            try:
                self._on_state_change(self.config.name, prev, State.OPEN)
            except Exception:  # noqa: BLE001
                pass

    def _reset_locked(self) -> None:
        prev = self._state
        self._state = State.CLOSED
        self._failures.clear()
        self._successes = 0
        self._half_open_calls = 0
        if self._on_state_change and prev is not State.CLOSED:
            try:
                self._on_state_change(self.config.name, prev, State.CLOSED)
            except Exception:  # noqa: BLE001
                pass

    def reset(self) -> None:
        """Force back to CLOSED. For tests and operator intervention only."""
        with self._lock:
            self._reset_locked()


class BreakerRegistry:
    """Every breaker declared in config/circuit_breakers.yaml.

    Loading the whole file rather than creating breakers on demand means an
    unknown dependency name is an error at lookup instead of a silently
    created breaker that never opens — a typo in ``circuit_breaker_dependency``
    would otherwise disable protection rather than fail.
    """

    def __init__(self, config_path: Path | None = None) -> None:
        self._breakers: dict[str, CircuitBreaker] = {}
        self._load(config_path or CONFIG_PATH)

    def _load(self, path: Path) -> None:
        parsed = yaml.safe_load(path.read_text())
        if parsed is None:
            parsed = {}
        if not isinstance(parsed, dict):
            # A malformed file otherwise fails with AttributeError on .get(),
            # deep in startup, naming neither the file nor the problem.
            raise ValueError(
                f"{path} must contain a mapping, not {type(parsed).__name__}"
            )
        raw: dict[str, Any] = parsed
        defaults: dict[str, Any] = raw.get("defaults", {}) or {}
        dependencies: dict[str, Any] = raw.get("dependencies", {}) or {}

        if not dependencies:
            raise ValueError(f"{path} declares no dependencies")

        for name, overrides in dependencies.items():
            merged = {**defaults, **(overrides or {})}
            missing = [
                key
                for key in ("failure_threshold", "window_seconds", "success_threshold")
                if key not in merged
            ]
            if missing:
                raise ValueError(f"breaker '{name}' is missing {', '.join(missing)}")
            for key in (
                "failure_threshold",
                "window_seconds",
                "success_threshold",
                "half_open_max_calls",
                "reset_timeout_seconds",
            ):
                value = merged.get(key, 1)
                if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                    # bool is an int in Python, and `failure_threshold: true`
                    # is a plausible YAML slip that would otherwise become 1.
                    raise ValueError(
                        f"breaker '{name}': {key} must be a positive integer, "
                        f"got {value!r}"
                    )

            if merged["success_threshold"] > merged.get("half_open_max_calls", 1):
                # Not a style rule — this combination used to wedge the breaker
                # permanently in HALF_OPEN. It is safe now that a success
                # releases its trial slot, but a config that needs N sequential
                # trials to recover takes N reset windows to do it, which is
                # worth being deliberate about rather than discovering during
                # an incident.
                logger_warning = (
                    f"breaker '{name}': success_threshold "
                    f"({merged['success_threshold']}) exceeds half_open_max_calls "
                    f"({merged.get('half_open_max_calls', 1)}); recovery needs "
                    "that many sequential trial calls"
                )
                logging.getLogger(__name__).info(logger_warning)

            if "degraded_mode" not in merged:
                # §18.2's whole point is that every dependency degrades to
                # something. One without a mode would fail closed with no
                # defined behaviour, which is the outage it is meant to avoid.
                raise ValueError(f"breaker '{name}' declares no degraded_mode")

            self._breakers[name] = CircuitBreaker(
                BreakerConfig(
                    name=name,
                    failure_threshold=int(merged["failure_threshold"]),
                    window_seconds=int(merged["window_seconds"]),
                    success_threshold=int(merged["success_threshold"]),
                    half_open_max_calls=int(merged.get("half_open_max_calls", 1)),
                    reset_timeout_seconds=int(merged.get("reset_timeout_seconds", 60)),
                    degraded_mode=str(merged["degraded_mode"]),
                    user_message=merged.get("user_message"),
                )
            )

    def get(self, dependency: str) -> CircuitBreaker:
        try:
            return self._breakers[dependency]
        except KeyError:
            raise KeyError(
                f"no breaker declared for '{dependency}' — "
                f"known: {', '.join(sorted(self._breakers))}"
            ) from None

    def names(self) -> list[str]:
        return sorted(self._breakers)

    def reset_all(self) -> None:
        for breaker in self._breakers.values():
            breaker.reset()
