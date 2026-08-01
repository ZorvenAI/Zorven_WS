"""End-to-end: the real image, built and run.

Everything above this file tests the application. This tests the artefact that
actually deploys — which is where AC-4 lives, and where a missing dependency or
a wrong CMD shows up.

Skips cleanly when Docker is unavailable.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

import httpx
import pytest

from tests.conftest import free_port

pytestmark = [pytest.mark.e2e]

ROOT = Path(__file__).resolve().parents[2]
IMAGE = "zorven-oia-e2e:test"
CONTAINER = "oia-e2e-test"


def docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    return (
        subprocess.run(["docker", "info"], capture_output=True, timeout=60).returncode
        == 0
    )


@pytest.fixture(scope="module")
def image() -> str:
    if not docker_available():
        pytest.skip("docker is not available")
    build = subprocess.run(
        ["docker", "build", "-t", IMAGE, "."],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert build.returncode == 0, build.stderr[-2000:]
    return IMAGE


@pytest.fixture
def running_container(image):
    """The image running with a reachable Redis, as it would be deployed."""
    port = free_port()
    subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True)
    run = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            CONTAINER,
            "-p",
            f"{port}:8120",
            "--add-host",
            "host.docker.internal:host-gateway",
            "-e",
            "OIA_BACKEND_BASE_URL=http://backend:8001",
            "-e",
            "OIA_GCS_BUCKET=zorven-raw-assets",
            "-e",
            "OIA_REDIS_URL=redis://host.docker.internal:6379/2",
            image,
        ],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stderr
    base = f"http://127.0.0.1:{port}"
    try:
        _wait_for(base)
        yield base
    finally:
        subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True)


def _wait_for(base: str, timeout: float = 90.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{base}/health", timeout=3).status_code in (200, 503):
                return
        except Exception:  # noqa: BLE001 — retried until the deadline
            time.sleep(1)
    logs = subprocess.run(
        ["docker", "logs", "--tail", "50", CONTAINER], capture_output=True, text=True
    )
    raise RuntimeError(f"container never answered:\n{logs.stdout}\n{logs.stderr}")


def test_container_serves_health_on_the_assigned_port(running_container):
    """AC-4: reachable on its assigned port, /health green."""
    response = httpx.get(f"{running_container}/health", timeout=10)
    assert response.status_code == 200
    assert response.json()["service"] == "onboarding-intelligence-agent"


def test_container_serves_diagnostics(running_container):
    body = httpx.get(f"{running_container}/health/diagnostics", timeout=10).json()
    assert body["port"] == 8120
    assert body["redis_db"] == 2
    assert body["key_prefix"] == "oia:v1:"
    assert set(body["dependencies"]) == {"redis", "kafka", "backend", "poi", "gcs"}


def test_container_logs_are_structured_json(running_container):
    """Cloud Logging indexes fields; a plain string is a wasted log line."""
    logs = subprocess.run(
        ["docker", "logs", CONTAINER], capture_output=True, text=True
    ).stdout
    started = [
        line
        for line in logs.splitlines()
        if line.startswith("{") and "service_started" in line
    ]
    assert started, f"no structured startup event in logs:\n{logs[-1500:]}"
    event = json.loads(started[0])
    assert event["service"] == "onboarding-intelligence-agent"
    assert event["redis_db"] == 2


def test_missing_required_variable_exits_non_zero(image):
    """AC-2 at the artefact level: a misconfigured deploy fails at rollout.

    OIA_GCS_BUCKET is omitted; the container must die rather than serve.
    """
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--name",
            f"{CONTAINER}-badcfg",
            "-e",
            "OIA_BACKEND_BASE_URL=http://backend:8001",
            image,
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode != 0, "container started without a required variable"
    combined = result.stdout + result.stderr
    assert "GCS_BUCKET" in combined, combined[-1500:]


def test_health_reports_unhealthy_when_redis_is_unreachable(image):
    """The probe checks rather than reports optimism — in the real image."""
    port = free_port()
    name = f"{CONTAINER}-noredis"
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "-p",
            f"{port}:8120",
            "-e",
            "OIA_BACKEND_BASE_URL=http://backend:8001",
            "-e",
            "OIA_GCS_BUCKET=zorven-raw-assets",
            # Nothing is listening here.
            "-e",
            "OIA_REDIS_URL=redis://127.0.0.1:6399/2",
            image,
        ],
        capture_output=True,
        check=True,
    )
    try:
        base = f"http://127.0.0.1:{port}"
        _wait_for_status(base, 503)
        response = httpx.get(f"{base}/health", timeout=10)
        assert response.status_code == 503
        assert "redis" in response.json()["failed"]
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)


def _wait_for_status(base: str, expected: int, timeout: float = 90.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{base}/health", timeout=5).status_code == expected:
                return
        except Exception:  # noqa: BLE001 — retried until the deadline
            pass
        time.sleep(1)
    raise RuntimeError(f"never observed HTTP {expected} from {base}/health")
