"""Fixtures that stand up the real echo service.

No mocks: every integration test runs against a uvicorn process on a real
socket, exactly as the gateway will see it.
"""

from __future__ import annotations

import os
import shutil
import socket
import string
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

SECRET = "spike-integration-secret"
ISSUER = "ai-brand-automator"
SPIKE_ROOT = Path(__file__).resolve().parents[1]

KONG_IMAGE_CANDIDATES = [
    "ghcr.io/zorvenai/zorven-kong:development_main",
    "kong:3.4",
]
ROUTE = "/api/v1/agents/onboarding/live"
# Suffixed so a long soak run and a normal test run can coexist.
CONTAINER_NAME = f"spike-a02-kong-{os.environ.get('SPIKE_KONG_SUFFIX', os.getpid())}"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_health(base_url: str, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{base_url}/health", timeout=2).status_code == 200:
                return
        except Exception as exc:  # noqa: BLE001 — retried until the deadline
            last = exc
        time.sleep(0.2)
    raise RuntimeError(f"echo service never became healthy: {last}")


@pytest.fixture(scope="session")
def echo_server():
    """A real uvicorn process running the echo service."""
    port = free_port()
    env = {
        **os.environ,
        "OIA_SPIKE_JWT_SECRET": SECRET,
        "OIA_SPIKE_JWT_ISSUER": ISSUER,
        "OIA_SPIKE_REPLAY_CAPACITY": "64",
        "PYTHONPATH": str(SPIKE_ROOT),
    }
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "echo.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=SPIKE_ROOT,
        env=env,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        wait_for_health(base)
        yield {"http": base, "ws": f"ws://127.0.0.1:{port}", "port": port}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture
def reset_stats(echo_server):
    """Zero the counters so each test reads its own numbers."""
    httpx.post(f"{echo_server['http']}/health/reset", timeout=5)
    yield


@pytest.fixture
def secret() -> str:
    return SECRET


def docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    return (
        subprocess.run(["docker", "info"], capture_output=True, timeout=30).returncode
        == 0
    )


def image_present(image: str) -> bool:
    return (
        subprocess.run(
            ["docker", "image", "inspect", image], capture_output=True
        ).returncode
        == 0
    )


def pick_image() -> str | None:
    for image in KONG_IMAGE_CANDIDATES:
        if image_present(image):
            return image
    # Nothing cached — try to pull the vanilla image once.
    pulled = subprocess.run(
        ["docker", "pull", KONG_IMAGE_CANDIDATES[-1]],
        capture_output=True,
        timeout=600,
    )
    return KONG_IMAGE_CANDIDATES[-1] if pulled.returncode == 0 else None


def render_config(dest: Path, upstream_url: str, secret: str) -> Path:
    template = (
        Path(__file__).resolve().parents[1] / "kong" / "oia-live.yaml"
    ).read_text()
    rendered = string.Template(template).safe_substitute(
        OIA_UPSTREAM_URL=upstream_url, JWT_SECRET_KEY=secret
    )
    dest.write_text(rendered)
    return dest


@pytest.fixture(scope="session")
def kong_gateway(echo_server, tmp_path_factory):
    """A real Kong container proxying to the real echo service."""
    if not docker_available():
        pytest.skip("docker is not available")
    image = pick_image()
    if image is None:
        pytest.skip("no Kong image available and pull failed")

    config = render_config(
        tmp_path_factory.mktemp("kong") / "kong.yaml",
        # Kong runs in a container; the echo runs on the host.
        f"http://host.docker.internal:{echo_server['port']}/v1/live",
        SECRET,
    )
    proxy_port = free_port()

    subprocess.run(["docker", "rm", "-f", CONTAINER_NAME], capture_output=True)
    run = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            CONTAINER_NAME,
            "-p",
            f"{proxy_port}:8000",
            "-v",
            f"{config}:/kong/kong.yaml:ro",
            "-e",
            "KONG_DATABASE=off",
            "-e",
            "KONG_DECLARATIVE_CONFIG=/kong/kong.yaml",
            "-e",
            "KONG_PROXY_LISTEN=0.0.0.0:8000",
            "-e",
            "KONG_ADMIN_LISTEN=0.0.0.0:8001",
            "-e",
            "KONG_PLUGINS=bundled,jwt",
            "--add-host",
            "host.docker.internal:host-gateway",
            # The fleet image wraps Kong in an envsubst entrypoint that wants
            # its own template; go straight to Kong's own entrypoint.
            "--entrypoint",
            "/docker-entrypoint.sh",
            image,
            "kong",
            "docker-start",
        ],
        capture_output=True,
        text=True,
    )
    if run.returncode != 0:
        pytest.skip(f"could not start Kong: {run.stderr[:300]}")

    base = f"127.0.0.1:{proxy_port}"
    try:
        _wait_for_kong(base)
        yield {"http": f"http://{base}", "ws": f"ws://{base}", "port": proxy_port}
    finally:
        subprocess.run(["docker", "rm", "-f", CONTAINER_NAME], capture_output=True)


def _wait_for_kong(base: str, timeout: float = 180.0) -> None:
    """Kong start-up is slower when the host is already busy (a soak running,
    other containers), so this window is generous rather than tight."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            # Any routed response proves the proxy is listening and the
            # declarative config parsed.
            httpx.get(f"http://{base}{ROUTE}/probe", timeout=3)
            return
        except Exception:  # noqa: BLE001 — retried until the deadline
            time.sleep(0.5)
    logs = subprocess.run(
        ["docker", "logs", "--tail", "40", CONTAINER_NAME],
        capture_output=True,
        text=True,
    )
    raise RuntimeError(f"Kong never became ready:\n{logs.stdout}\n{logs.stderr}")
