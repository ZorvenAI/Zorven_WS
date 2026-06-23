"""Prometheus metrics for prompt-optimization-svc (US-048, §19.1).

Central metrics registry — all 8 metrics as module-level singletons,
alert threshold constants, and convenience record functions.
"""

from prometheus_client import Counter, Gauge, Histogram

# ── §19.1 Prompt loading ──

PROMPT_LOAD_LATENCY = Histogram(
    "poi_prompt_load_latency_ms",
    "Prompt load latency in milliseconds",
    ["name", "tier", "tenant_id"],
    buckets=[1, 2, 5, 10, 25, 50, 100, 250, 500, 1000],
)

PROMPT_CACHE_HIT = Counter(
    "poi_prompt_cache_hit",
    "Prompt cache hit/miss count by tier and result",
    ["tier", "result"],
)

# ── §19.1 Optimization run ──

OPT_RUN_DURATION = Histogram(
    "poi_optimization_run_duration_seconds",
    "Optimization run duration in seconds",
    ["agent_code", "group_name"],
    buckets=[10, 30, 60, 120, 300, 600, 1800, 3600],
)

OPT_RUN_COST = Histogram(
    "poi_optimization_run_cost_usd",
    "Optimization run cost in USD",
    ["agent_code"],
    buckets=[0.5, 1, 2, 5, 10, 15, 20, 25, 50],
)

# ── §19.1 Quality ──

PROMPT_IMPROVEMENT = Gauge(
    "poi_prompt_improvement_pct",
    "Latest prompt improvement percentage",
    ["agent_code", "prompt_name"],
)

SCORER_REGRESSION = Gauge(
    "poi_scorer_regression_pct",
    "Latest scorer regression percentage",
    ["agent_code", "prompt_name"],
)

# ── §19.1 Infrastructure health ──

MLFLOW_HEALTH = Gauge(
    "poi_mlflow_server_health",
    "MLflow server health (1=up, 0=down)",
)

# ── §19.1 Fallback usage ──

PROMPT_FALLBACK_USAGE = Counter(
    "poi_prompt_fallback_usage",
    "Prompt fallback template usage count",
    ["name"],
)

# ── AC-2: Alert threshold constants per §19.1 ──

ALERT_CACHE_HIT_P95_MS = 5.0
ALERT_COST_PER_AGENT_USD = 25.0
ALERT_REGRESSION_PCT = 10.0


# ── Convenience record functions ──


def record_optimization_run(
    agent_code: str,
    group_name: str,
    duration_seconds: float,
    cost_usd: float,
) -> None:
    """Record optimization run duration and cost metrics."""
    OPT_RUN_DURATION.labels(agent_code=agent_code, group_name=group_name).observe(
        duration_seconds
    )
    OPT_RUN_COST.labels(agent_code=agent_code).observe(cost_usd)


def record_prompt_quality(
    agent_code: str,
    prompt_name: str,
    improvement_pct: float,
    regression_pct: float,
) -> None:
    """Record prompt quality improvement and regression gauges."""
    PROMPT_IMPROVEMENT.labels(agent_code=agent_code, prompt_name=prompt_name).set(
        improvement_pct
    )
    SCORER_REGRESSION.labels(agent_code=agent_code, prompt_name=prompt_name).set(
        regression_pct
    )
