"""Prometheus metrics for onboarding-intelligence-agent-svc (M-04, Design §20).

Central metrics registry — all metrics as module-level singletons,
alert threshold constants, and convenience record functions.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# ── Panel 1: Active WebSocket sessions (per-instance) ──

WS_SESSIONS_ACTIVE = Gauge(
    "oia_ws_sessions_active",
    "Number of active WebSocket LIVE sessions on this instance",
)

# ── Panel 2: STT partial latency p50/p95 ──

STT_PARTIAL_LATENCY = Histogram(
    "oia_stt_partial_latency_ms",
    "Time to emit an STT partial transcript to the WebSocket client (ms)",
    buckets=[50, 100, 250, 500, 1000, 1500, 2000, 3000, 5000],
)

# ── Panel 3: Sufficiency scoring latency p95 ──

SUFFICIENCY_LATENCY = Histogram(
    "oia_sufficiency_latency_ms",
    "Sufficiency scoring latency in milliseconds",
    buckets=[100, 250, 500, 1000, 2000, 3000, 5000, 10000],
)

# ── Panel 4: Guardrail trigger rate by rule_id ──

GUARDRAIL_TRIGGERS = Counter(
    "oia_guardrail_triggers_total",
    "Guardrail trigger count by rule_id",
    ["rule_id"],
)

# ── Panel 5: Circuit breaker state per dependency ──

CIRCUIT_BREAKER_STATE = Gauge(
    "oia_circuit_breaker_state",
    "Circuit breaker state per dependency (0=CLOSED, 1=OPEN, 2=HALF_OPEN)",
    ["dependency"],
)

# ── Panel 6: DLQ depth ──

DLQ_MESSAGES = Counter(
    "oia_dlq_messages_total",
    "Messages dead-lettered since startup",
)

# ── Panel 7: Golden candidate volume ──

GOLDEN_CANDIDATES = Counter(
    "oia_golden_candidates_total",
    "Golden dataset candidates emitted",
)

# ── Panel 8: Dropped ungrounded facts per PROCESS job ──

DROPPED_UNGROUNDED = Counter(
    "oia_dropped_ungrounded_total",
    "Ungrounded facts dropped during PROCESS extraction",
)

# ── Auxiliary: event emitter dropped events ──

EVENTS_DROPPED = Counter(
    "oia_events_dropped_total",
    "Events dropped due to queue overflow",
)

# ── Panel 9: Sufficiency signals dropped due to timeout ──

SUFFICIENCY_DROPS = Counter(
    "oia_sufficiency_drops_total",
    "Sufficiency signals dropped due to timeout",
)

# ── Alert threshold constants ──

ALERT_STT_PARTIAL_P95_MS = 2000.0
ALERT_SUFFICIENCY_P95_MS = 5000.0
ALERT_DLQ_RATE = 0.1


# ── Convenience record functions ──


def record_guardrail_trigger(rule_id: str) -> None:
    GUARDRAIL_TRIGGERS.labels(rule_id=rule_id).inc()


def record_circuit_state(dependency: str, state_ordinal: int) -> None:
    CIRCUIT_BREAKER_STATE.labels(dependency=dependency).set(state_ordinal)


def record_stt_partial_latency(ms: float) -> None:
    STT_PARTIAL_LATENCY.observe(ms)


def record_sufficiency_latency(ms: float) -> None:
    SUFFICIENCY_LATENCY.observe(ms)


def record_sufficiency_drop() -> None:
    SUFFICIENCY_DROPS.inc()
