"""Load test fixtures (N-02 AC-1/2/3).

Gated behind ``OIA_LOAD_TARGET``. When absent, all load-marked tests skip.
When set (e.g. ``OIA_LOAD_TARGET=wss://oia.zorven.dev``), tests connect
to the deployed service through the real gateway.

Environment label (``OIA_LOAD_ENVIRONMENT``) tags the output so both
Cloud Run direct and Kong dev-tier results are distinguishable.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import httpx
import pytest

LOAD_TARGET = os.environ.get("OIA_LOAD_TARGET", "")
LOAD_CONCURRENCY = int(os.environ.get("OIA_LOAD_CONCURRENCY", "5"))
LOAD_ENVIRONMENT = os.environ.get("OIA_LOAD_ENVIRONMENT", "local")
LOAD_TICKET = os.environ.get("OIA_LOAD_TICKET", "load-test")
LOAD_SERVICE_TOKEN = os.environ.get("OIA_LOAD_SERVICE_TOKEN", "load-test")

FIXTURE_2MIN = Path(__file__).parent.parent / "fixtures" / "two_speaker_2min.jsonl"


def pytest_collection_modifyitems(config: Any, items: list[Any]) -> None:
    if not LOAD_TARGET:
        skip = pytest.mark.skip(reason="OIA_LOAD_TARGET not set")
        for item in items:
            if "load" in item.keywords:
                item.add_marker(skip)


def _ws_to_http(ws_url: str) -> str:
    """Convert ws(s):// to http(s):// for metrics scraping."""
    return re.sub(
        r"^wss?://", lambda m: "https://" if "wss" in m.group() else "http://", ws_url
    )


@pytest.fixture
def target_url() -> str:
    return LOAD_TARGET


@pytest.fixture
def http_base() -> str:
    return _ws_to_http(LOAD_TARGET)


@pytest.fixture
def concurrency() -> int:
    return LOAD_CONCURRENCY


@pytest.fixture
def environment_label() -> str:
    return LOAD_ENVIRONMENT


@pytest.fixture
def load_ticket() -> str:
    return LOAD_TICKET


@pytest.fixture
def load_service_token() -> str:
    return LOAD_SERVICE_TOKEN


@pytest.fixture
def fixture_events() -> list[dict[str, Any]]:
    with open(FIXTURE_2MIN) as f:
        return [json.loads(line) for line in f]


@pytest.fixture
def metrics_client(http_base: str) -> httpx.Client:
    base = http_base.rstrip("/")
    return httpx.Client(base_url=base, timeout=10.0)


def parse_prometheus_counter(text: str, metric_name: str) -> float:
    """Extract a counter value from Prometheus text exposition format."""
    for line in text.splitlines():
        if line.startswith(metric_name + " ") or line.startswith(metric_name + "{"):
            parts = line.split()
            return float(parts[-1])
    return 0.0


def parse_prometheus_histogram_sum(text: str, metric_name: str) -> float:
    """Extract _sum from a histogram in Prometheus text exposition format."""
    sum_name = metric_name + "_sum"
    for line in text.splitlines():
        if line.startswith(sum_name + " ") or line.startswith(sum_name + "{"):
            parts = line.split()
            return float(parts[-1])
    return 0.0


def parse_prometheus_histogram_count(text: str, metric_name: str) -> float:
    """Extract _count from a histogram in Prometheus text exposition format."""
    count_name = metric_name + "_count"
    for line in text.splitlines():
        if line.startswith(count_name + " ") or line.startswith(count_name + "{"):
            parts = line.split()
            return float(parts[-1])
    return 0.0


def parse_prometheus_histogram_buckets(
    text: str, metric_name: str
) -> list[tuple[float, float]]:
    """Extract (le, count) pairs from histogram buckets."""
    bucket_name = metric_name + "_bucket"
    buckets: list[tuple[float, float]] = []
    for line in text.splitlines():
        if line.startswith(bucket_name + "{"):
            le_match = re.search(r'le="([^"]+)"', line)
            if le_match:
                le_val = le_match.group(1)
                count = float(line.split()[-1])
                le_float = float("inf") if le_val == "+Inf" else float(le_val)
                buckets.append((le_float, count))
    return sorted(buckets, key=lambda x: x[0])


def estimate_p95_from_buckets(
    buckets: list[tuple[float, float]],
) -> float | None:
    """Estimate p95 from histogram bucket boundaries.

    Uses linear interpolation within the bucket that contains the 95th
    percentile observation, matching Prometheus's histogram_quantile().
    """
    if not buckets:
        return None
    total = buckets[-1][1]
    if total == 0:
        return None
    target = 0.95 * total
    prev_le = 0.0
    prev_count = 0.0
    for le, count in buckets:
        if count >= target:
            if count == prev_count:
                return le
            fraction = (target - prev_count) / (count - prev_count)
            return prev_le + fraction * (le - prev_le)
        prev_le = le
        prev_count = count
    return buckets[-1][0]
