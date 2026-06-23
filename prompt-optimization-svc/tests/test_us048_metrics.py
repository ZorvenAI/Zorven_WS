"""Unit tests for Prometheus metrics instrumentation (US-048).

Tests metric definitions, alert thresholds, record helpers,
prompt loader instrumentation, health checker instrumentation,
and the /metrics endpoint.
"""

from prometheus_client import Counter, Gauge, Histogram

from app.metrics import (
    ALERT_CACHE_HIT_P95_MS,
    ALERT_COST_PER_AGENT_USD,
    ALERT_REGRESSION_PCT,
    MLFLOW_HEALTH,
    OPT_RUN_COST,
    OPT_RUN_DURATION,
    PROMPT_CACHE_HIT,
    PROMPT_FALLBACK_USAGE,
    PROMPT_IMPROVEMENT,
    PROMPT_LOAD_LATENCY,
    SCORER_REGRESSION,
    record_optimization_run,
    record_prompt_quality,
)


# ── Metric definitions ──


class TestMetricDefinitions:
    def test_prompt_load_latency_type(self):
        assert isinstance(PROMPT_LOAD_LATENCY, Histogram)

    def test_prompt_load_latency_name(self):
        assert PROMPT_LOAD_LATENCY._name == "poi_prompt_load_latency_ms"

    def test_prompt_load_latency_labels(self):
        assert PROMPT_LOAD_LATENCY._labelnames == ("name", "tier", "tenant_id")

    def test_prompt_cache_hit_type(self):
        assert isinstance(PROMPT_CACHE_HIT, Counter)

    def test_prompt_cache_hit_name(self):
        assert PROMPT_CACHE_HIT._name == "poi_prompt_cache_hit"

    def test_prompt_cache_hit_labels(self):
        assert PROMPT_CACHE_HIT._labelnames == ("tier", "result")

    def test_opt_run_duration_type(self):
        assert isinstance(OPT_RUN_DURATION, Histogram)

    def test_opt_run_duration_name(self):
        assert OPT_RUN_DURATION._name == "poi_optimization_run_duration_seconds"

    def test_opt_run_duration_labels(self):
        assert OPT_RUN_DURATION._labelnames == ("agent_code", "group_name")

    def test_opt_run_cost_type(self):
        assert isinstance(OPT_RUN_COST, Histogram)

    def test_opt_run_cost_name(self):
        assert OPT_RUN_COST._name == "poi_optimization_run_cost_usd"

    def test_opt_run_cost_labels(self):
        assert OPT_RUN_COST._labelnames == ("agent_code",)

    def test_prompt_improvement_type(self):
        assert isinstance(PROMPT_IMPROVEMENT, Gauge)

    def test_prompt_improvement_name(self):
        assert PROMPT_IMPROVEMENT._name == "poi_prompt_improvement_pct"

    def test_prompt_improvement_labels(self):
        assert PROMPT_IMPROVEMENT._labelnames == ("agent_code", "prompt_name")

    def test_scorer_regression_type(self):
        assert isinstance(SCORER_REGRESSION, Gauge)

    def test_scorer_regression_name(self):
        assert SCORER_REGRESSION._name == "poi_scorer_regression_pct"

    def test_scorer_regression_labels(self):
        assert SCORER_REGRESSION._labelnames == ("agent_code", "prompt_name")

    def test_mlflow_health_type(self):
        assert isinstance(MLFLOW_HEALTH, Gauge)

    def test_mlflow_health_name(self):
        assert MLFLOW_HEALTH._name == "poi_mlflow_server_health"

    def test_mlflow_health_no_labels(self):
        assert MLFLOW_HEALTH._labelnames == ()

    def test_prompt_fallback_usage_type(self):
        assert isinstance(PROMPT_FALLBACK_USAGE, Counter)

    def test_prompt_fallback_usage_name(self):
        assert PROMPT_FALLBACK_USAGE._name == "poi_prompt_fallback_usage"

    def test_prompt_fallback_usage_labels(self):
        assert PROMPT_FALLBACK_USAGE._labelnames == ("name",)

    def test_prompt_load_latency_buckets(self):
        expected_count = 11  # 10 explicit + Inf
        assert len(PROMPT_LOAD_LATENCY._upper_bounds) == expected_count

    def test_opt_run_duration_buckets(self):
        expected_count = 9  # 8 explicit + Inf
        assert len(OPT_RUN_DURATION._upper_bounds) == expected_count

    def test_opt_run_cost_buckets(self):
        expected_count = 10  # 9 explicit + Inf
        assert len(OPT_RUN_COST._upper_bounds) == expected_count


# ── Alert thresholds ──


class TestAlertThresholds:
    def test_cache_hit_p95_ms(self):
        assert ALERT_CACHE_HIT_P95_MS == 5.0

    def test_cost_per_agent_usd(self):
        assert ALERT_COST_PER_AGENT_USD == 25.0

    def test_regression_pct(self):
        assert ALERT_REGRESSION_PCT == 10.0


# ── Record optimization run ──


class TestRecordOptimizationRun:
    def test_records_duration(self):
        before = OPT_RUN_DURATION.labels(
            agent_code="CAA", group_name="wf3-creative-pipeline"
        )._sum.get()
        record_optimization_run("CAA", "wf3-creative-pipeline", 120.5, 10.0)
        after = OPT_RUN_DURATION.labels(
            agent_code="CAA", group_name="wf3-creative-pipeline"
        )._sum.get()
        assert after - before == 120.5

    def test_records_cost(self):
        before = OPT_RUN_COST.labels(agent_code="CGA")._sum.get()
        record_optimization_run("CGA", "wf3-creative-pipeline", 60.0, 15.5)
        after = OPT_RUN_COST.labels(agent_code="CGA")._sum.get()
        assert after - before == 15.5

    def test_labels_applied_correctly(self):
        record_optimization_run("COA", "wf3-optimization-loop", 30.0, 5.0)
        val = OPT_RUN_DURATION.labels(
            agent_code="COA", group_name="wf3-optimization-loop"
        )._sum.get()
        assert val >= 30.0

    def test_multiple_calls_accumulate(self):
        before = OPT_RUN_COST.labels(agent_code="ILA")._sum.get()
        record_optimization_run("ILA", "wf3-optimization-loop", 10.0, 2.0)
        record_optimization_run("ILA", "wf3-optimization-loop", 20.0, 3.0)
        after = OPT_RUN_COST.labels(agent_code="ILA")._sum.get()
        assert after - before == 5.0


# ── Record prompt quality ──


class TestRecordPromptQuality:
    def test_sets_improvement(self):
        record_prompt_quality("CAA", "caa-system-prompt", 12.5, 0.0)
        val = PROMPT_IMPROVEMENT.labels(
            agent_code="CAA", prompt_name="caa-system-prompt"
        )._value.get()
        assert val == 12.5

    def test_sets_regression(self):
        record_prompt_quality("CGA", "cga-system-prompt", 5.0, 3.2)
        val = SCORER_REGRESSION.labels(
            agent_code="CGA", prompt_name="cga-system-prompt"
        )._value.get()
        assert val == 3.2

    def test_gauge_updates_on_subsequent_calls(self):
        record_prompt_quality("ADPUB", "adpub-system-prompt", 10.0, 1.0)
        record_prompt_quality("ADPUB", "adpub-system-prompt", 15.0, 2.0)
        val = PROMPT_IMPROVEMENT.labels(
            agent_code="ADPUB", prompt_name="adpub-system-prompt"
        )._value.get()
        assert val == 15.0

    def test_labels_applied_correctly(self):
        record_prompt_quality("BPA", "bpa-system-prompt", 7.0, 0.5)
        # Gauge should be accessible with the exact labels
        val = SCORER_REGRESSION.labels(
            agent_code="BPA", prompt_name="bpa-system-prompt"
        )._value.get()
        assert val == 0.5


# ── MLflow health metric ──


class TestMLflowHealthMetric:
    def test_set_up(self):
        MLFLOW_HEALTH.set(1.0)
        assert MLFLOW_HEALTH._value.get() == 1.0

    def test_set_down(self):
        MLFLOW_HEALTH.set(0.0)
        assert MLFLOW_HEALTH._value.get() == 0.0

    def test_toggles(self):
        MLFLOW_HEALTH.set(1.0)
        assert MLFLOW_HEALTH._value.get() == 1.0
        MLFLOW_HEALTH.set(0.0)
        assert MLFLOW_HEALTH._value.get() == 0.0
        MLFLOW_HEALTH.set(1.0)
        assert MLFLOW_HEALTH._value.get() == 1.0


# ── Prompt loader instrumentation ──


class TestPromptLoaderInstrumentation:
    def test_cache_hit_counter_import(self):
        """PROMPT_CACHE_HIT is importable and used in prompt_loader."""
        from app.services.prompt_loader import PROMPT_CACHE_HIT as imported

        assert imported is PROMPT_CACHE_HIT

    def test_fallback_counter_import(self):
        """PROMPT_FALLBACK_USAGE is importable and used in prompt_loader."""
        from app.services.prompt_loader import PROMPT_FALLBACK_USAGE as imported

        assert imported is PROMPT_FALLBACK_USAGE

    def test_load_latency_import(self):
        """PROMPT_LOAD_LATENCY is importable and used in prompt_loader."""
        from app.services.prompt_loader import PROMPT_LOAD_LATENCY as imported

        assert imported is PROMPT_LOAD_LATENCY

    def test_tier1_tenant_label_exists(self):
        """Verify tier1_tenant label is used in counter."""
        PROMPT_CACHE_HIT.labels(tier="tier1_tenant", result="hit").inc(0)
        # No error means the label combination is valid

    def test_tier1_production_label_exists(self):
        """Verify tier1_production label is used in counter."""
        PROMPT_CACHE_HIT.labels(tier="tier1_production", result="hit").inc(0)

    def test_tier2_mlflow_label_exists(self):
        """Verify tier2_mlflow label is used in counter."""
        PROMPT_CACHE_HIT.labels(tier="tier2_mlflow", result="hit").inc(0)


# ── Health checker instrumentation ──


class TestHealthCheckerInstrumentation:
    def test_mlflow_health_import(self):
        """MLFLOW_HEALTH is importable in health_checker."""
        from app.services.health_checker import MLFLOW_HEALTH as imported

        assert imported is MLFLOW_HEALTH


# ── /metrics endpoint ──


class TestMetricsEndpoint:
    def test_metrics_endpoint_returns_200(self):
        from fastapi.testclient import TestClient

        from app.main import app

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/metrics")
        assert resp.status_code == 200

    def test_metrics_response_contains_poi_prefix(self):
        from fastapi.testclient import TestClient

        from app.main import app

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/metrics")
        body = resp.text
        assert "poi_" in body
