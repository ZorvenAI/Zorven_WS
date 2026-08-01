"""Guards the wiring between agent URLs, settings, and the deploy script.

This file exists because of a production incident. Twenty orchestrator env
vars were named ``ORCHESTRATOR_<NAME>_URL`` while the Settings fields are
``<NAME>_AGENT_URL``, so pydantic silently kept every docker-compose default.
Nothing errored at deploy or at startup — the orchestrator simply called
``http://voc-agent-svc:8025`` on Cloud Run, where that name does not resolve,
and every external node failed with "Name or service not known".

A misnamed environment variable is invisible by construction: pydantic cannot
warn about a variable it was never asked for. The only place to catch it is
here, by asserting the three artefacts agree.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

import pytest

from app.core.config import Settings, settings
from app.factory.graph_builder import _SERVICE_URL_MAP
from app.factory.node_registry import EXTERNAL_ENDPOINTS

REPO_ROOT = Path(__file__).resolve().parents[2]
REDEPLOY_SCRIPT = REPO_ROOT / "deployment" / "gcp" / "10-redeploy-with-urls.sh"
ENV_PREFIX = "ORCHESTRATOR_"


def orchestrator_env_vars_in_script() -> set[str]:
    """Every ORCHESTRATOR_* variable the deploy script sets."""
    if not REDEPLOY_SCRIPT.is_file():
        pytest.skip(f"{REDEPLOY_SCRIPT} not available")
    text = REDEPLOY_SCRIPT.read_text()
    return set(re.findall(r"^(ORCHESTRATOR_[A-Z0-9_]+)=", text, re.MULTILINE))


def test_every_env_var_the_script_sets_maps_to_a_real_setting():
    """The incident, asserted directly.

    A variable the script sets but Settings never reads is dead weight at
    best and a silent fallback to a compose hostname at worst.
    """
    fields = set(Settings.model_fields)
    unknown = sorted(
        name
        for name in orchestrator_env_vars_in_script()
        if name.removeprefix(ENV_PREFIX) not in fields
    )
    assert not unknown, (
        "these env vars do not correspond to any Settings field, so they are "
        f"silently ignored: {unknown}"
    )


def test_every_agent_url_setting_is_wired_by_the_script():
    """The converse: a setting nobody sets keeps its compose default."""
    script_vars = orchestrator_env_vars_in_script()
    unwired = sorted(
        name
        for name in Settings.model_fields
        if name.endswith("_AGENT_URL") and f"{ENV_PREFIX}{name}" not in script_vars
    )
    assert not unwired, (
        "these agent URLs are never set by the deploy script and will fall "
        f"back to their docker-compose defaults on Cloud Run: {unwired}"
    )


def test_every_external_endpoint_host_can_be_translated():
    """Every compose host in EXTERNAL_ENDPOINTS must be in the rewrite map.

    An endpoint whose host is absent from the map is passed through
    unchanged, which on Cloud Run means an unresolvable hostname.
    """
    hosts = {urlparse(url).netloc for url in EXTERNAL_ENDPOINTS.values()}
    uncovered = sorted(host for host in hosts if host not in _SERVICE_URL_MAP)
    assert not uncovered, f"these hosts have no entry in _SERVICE_URL_MAP: {uncovered}"


def test_translation_actually_rewrites_a_compose_url(monkeypatch):
    """Prove the mechanism, not just the table."""
    from app.factory.graph_builder import GraphBuilder

    monkeypatch.setitem(
        _SERVICE_URL_MAP, "voc-agent-svc:8025", "https://voc.example.run.app"
    )
    translated = GraphBuilder._translate_url("http://voc-agent-svc:8025/v1/execute")
    assert translated == "https://voc.example.run.app/v1/execute"


def test_an_unmapped_url_is_left_alone():
    from app.factory.graph_builder import GraphBuilder

    url = "http://something-else:9999/v1/execute"
    assert GraphBuilder._translate_url(url) == url


def test_defaults_are_compose_hostnames_not_cloud_urls():
    """The defaults are for local compose; production must override them.

    If a default ever became a .run.app URL, a missing env var would stop
    being detectable by this suite.
    """
    for name in Settings.model_fields:
        if not name.endswith("_AGENT_URL"):
            continue
        default = getattr(Settings(), name)
        assert ".run.app" not in default, (
            f"{name} defaults to a Cloud Run URL, which hides a missing "
            "environment variable"
        )


def test_live_settings_are_not_silently_defaulted():
    """A diagnostic: report any agent URL still on its compose default.

    Skipped unless ORCHESTRATOR_* vars are present, so it is a no-op locally
    and a real check in a deployed environment.
    """
    import os

    if not any(k.startswith(ENV_PREFIX) for k in os.environ):
        pytest.skip("no ORCHESTRATOR_* environment — nothing to verify")

    defaulted = [
        name
        for name in Settings.model_fields
        if name.endswith("_AGENT_URL")
        and getattr(settings, name).startswith("http://")
        and "localhost" not in getattr(settings, name)
    ]
    assert (
        not defaulted
    ), f"still on docker-compose defaults in a configured environment: {defaulted}"
