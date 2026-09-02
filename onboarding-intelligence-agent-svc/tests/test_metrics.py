"""M-04 — Prometheus metrics module tests."""

from __future__ import annotations

from app.metrics import (
    CIRCUIT_BREAKER_STATE,
    DLQ_DEPTH,
    DROPPED_UNGROUNDED,
    EVENTS_DROPPED,
    GOLDEN_CANDIDATES,
    GUARDRAIL_TRIGGERS,
    STT_PARTIAL_LATENCY,
    SUFFICIENCY_LATENCY,
    WS_SESSIONS_ACTIVE,
    record_circuit_state,
    record_guardrail_trigger,
    record_stt_partial_latency,
    record_sufficiency_latency,
)


def test_all_metrics_have_oia_prefix():
    """Every metric name starts with oia_."""
    metrics = [
        WS_SESSIONS_ACTIVE,
        STT_PARTIAL_LATENCY,
        SUFFICIENCY_LATENCY,
        GUARDRAIL_TRIGGERS,
        CIRCUIT_BREAKER_STATE,
        DLQ_DEPTH,
        GOLDEN_CANDIDATES,
        DROPPED_UNGROUNDED,
        EVENTS_DROPPED,
    ]
    for m in metrics:
        desc = m.describe()[0]
        assert desc.name.startswith("oia_"), f"{desc.name} missing oia_ prefix"


def test_guardrail_trigger_increments_counter():
    before = GUARDRAIL_TRIGGERS.labels(rule_id="IG-01")._value.get()
    record_guardrail_trigger("IG-01")
    after = GUARDRAIL_TRIGGERS.labels(rule_id="IG-01")._value.get()
    assert after == before + 1


def test_ws_session_gauge_inc_dec():
    baseline = WS_SESSIONS_ACTIVE._value.get()
    WS_SESSIONS_ACTIVE.inc()
    assert WS_SESSIONS_ACTIVE._value.get() == baseline + 1
    WS_SESSIONS_ACTIVE.dec()
    assert WS_SESSIONS_ACTIVE._value.get() == baseline


def test_circuit_state_sets_gauge():
    record_circuit_state("redis", 1)
    val = CIRCUIT_BREAKER_STATE.labels(dependency="redis")._value.get()
    assert val == 1.0
    record_circuit_state("redis", 0)
    val = CIRCUIT_BREAKER_STATE.labels(dependency="redis")._value.get()
    assert val == 0.0


def test_dlq_depth_sets_absolute():
    DLQ_DEPTH.set(5)
    assert DLQ_DEPTH._value.get() == 5.0
    DLQ_DEPTH.set(0)


def test_stt_partial_latency_records():
    record_stt_partial_latency(150.0)
    assert STT_PARTIAL_LATENCY._sum.get() > 0


def test_sufficiency_latency_records():
    record_sufficiency_latency(2500.0)
    assert SUFFICIENCY_LATENCY._sum.get() > 0


def test_dropped_ungrounded_increments():
    before = DROPPED_UNGROUNDED._value.get()
    DROPPED_UNGROUNDED.inc(3)
    assert DROPPED_UNGROUNDED._value.get() == before + 3


def test_golden_candidates_increments():
    before = GOLDEN_CANDIDATES._value.get()
    GOLDEN_CANDIDATES.inc()
    assert GOLDEN_CANDIDATES._value.get() == before + 1


def test_events_dropped_increments():
    before = EVENTS_DROPPED._value.get()
    EVENTS_DROPPED.inc()
    assert EVENTS_DROPPED._value.get() == before + 1
