"""AC-2 — configuration is typed, prefixed, and fails loudly when incomplete."""

from __future__ import annotations

import os

import pytest
from pydantic import ValidationError

from app.core.config import Settings

pytestmark = pytest.mark.unit

REQUIRED = {"OIA_BACKEND_BASE_URL": "http://backend:8001", "OIA_GCS_BUCKET": "b"}


def clear_oia_env(monkeypatch) -> None:
    """Remove every OIA_ variable inherited from the developer's shell.

    Without this the tests are not hermetic: an ambient OIA_REDIS_URL or
    OIA_LOG_LEVEL silently changes what is under test, so a suite that passes
    in CI can fail on a machine where someone exported one.
    """
    for key in [k for k in os.environ if k.startswith("OIA_")]:
        monkeypatch.delenv(key, raising=False)


def build(monkeypatch, **env: str) -> Settings:
    """Construct Settings from a genuinely clean environment.

    Real environment variables and a real Settings class — the point of AC-2 is
    that configuration resolution behaves correctly, so nothing here is faked.
    """
    clear_oia_env(monkeypatch)
    for key, value in {**REQUIRED, **env}.items():
        monkeypatch.setenv(key, value)
    return Settings()  # type: ignore[call-arg]


def test_defaults_match_design_section_19(monkeypatch):
    s = build(monkeypatch)
    assert s.PORT == 8120
    assert s.SUFFICIENCY_GREEN_THRESHOLD == 0.7
    assert s.LIVE_ANALYSIS_SILENCE_MS == 4000
    assert s.TRANSCRIPT_BUFFER_MAX == 4000
    assert s.CONTEXT_SUMMARIZE_AT == 0.75
    assert s.RETENTION_DAYS_DEFAULT == 365
    assert s.STT_LANGUAGE_DEFAULT == "en-US"
    assert s.MAX_CONCURRENT_LIVE_PER_COMPANY == 1
    assert s.PROCESS_TIMEOUT_S == 300
    assert s.LOG_LEVEL == "INFO"


def test_redis_defaults_to_db_2_not_27(monkeypatch):
    """ERRATA-01: DB 27 does not exist on Memorystore."""
    s = build(monkeypatch)
    assert s.REDIS_DB == 2
    assert s.REDIS_URL.endswith("/2")
    assert s.POI_PROMPT_CACHE_DB == 2


@pytest.mark.parametrize("missing", sorted(REQUIRED))
def test_missing_required_variable_fails_at_startup(monkeypatch, missing):
    """The error must name the variable, not just say 'invalid config'."""
    clear_oia_env(monkeypatch)
    for key, value in REQUIRED.items():
        if key != missing:
            monkeypatch.setenv(key, value)

    with pytest.raises(ValidationError) as exc:
        Settings()  # type: ignore[call-arg]

    assert missing.removeprefix("OIA_") in str(exc.value)


def test_env_prefix_is_oia(monkeypatch):
    s = build(monkeypatch, OIA_PORT="9999")
    assert s.PORT == 9999


def test_unprefixed_variable_is_ignored(monkeypatch):
    """A bare PORT must not leak into the service's configuration."""
    monkeypatch.setenv("PORT", "1234")
    assert build(monkeypatch).PORT == 8120


@pytest.mark.parametrize("db", ["16", "27", "-1"])
def test_redis_db_outside_memorystore_range_is_rejected(monkeypatch, db):
    """The DB 27 mistake fails at startup instead of silently cacheless."""
    with pytest.raises(ValidationError, match="Memorystore"):
        build(monkeypatch, OIA_REDIS_DB=db)


@pytest.mark.parametrize("value", ["1.5", "-0.1"])
def test_fractions_are_range_checked(monkeypatch, value):
    with pytest.raises(ValidationError):
        build(monkeypatch, OIA_SUFFICIENCY_GREEN_THRESHOLD=value)


def test_types_are_coerced_from_strings(monkeypatch):
    s = build(
        monkeypatch, OIA_TRANSCRIPT_BUFFER_MAX="10", OIA_CONTEXT_SUMMARIZE_AT="0.5"
    )
    assert s.TRANSCRIPT_BUFFER_MAX == 10 and isinstance(s.TRANSCRIPT_BUFFER_MAX, int)
    assert s.CONTEXT_SUMMARIZE_AT == 0.5


def test_kafka_is_optional_and_reported(monkeypatch):
    """No GCP script provisions a broker, so absence is a valid state."""
    assert build(monkeypatch).kafka_enabled is False
    assert build(monkeypatch, OIA_KAFKA_BOOTSTRAP_SERVERS="kafka:9092").kafka_enabled
    assert build(monkeypatch, OIA_KAFKA_BOOTSTRAP_SERVERS="   ").kafka_enabled is False


def test_secrets_default_empty_and_are_never_inline(monkeypatch):
    s = build(monkeypatch)
    assert s.STT_CREDENTIALS == ""
    assert s.GEMINI_KEY == ""
    assert s.SERVICE_TOKEN == ""
    assert s.POI_TOKEN == ""


# ── Regression cover for PR #530 review findings ─────────────────────────


@pytest.mark.parametrize("db", [16, 27, 99])
def test_redis_url_with_an_impossible_db_is_rejected(monkeypatch, db):
    """REDIS_URL is what the service dials, so it is what must be validated.

    Review finding: validating REDIS_DB alone let
    OIA_REDIS_URL=redis://host:6379/27 through — exactly the misconfiguration
    ERRATA-01 exists to prevent.
    """
    with pytest.raises(ValidationError, match="Memorystore"):
        build(monkeypatch, OIA_REDIS_URL=f"redis://localhost:6379/{db}")


def test_redis_db_follows_the_url_when_only_the_url_is_set(monkeypatch):
    """Otherwise /health/diagnostics reports a database nothing connects to."""
    s = build(monkeypatch, OIA_REDIS_URL="redis://localhost:6379/5")
    assert s.REDIS_DB == 5


def test_url_and_db_disagreement_is_rejected(monkeypatch):
    with pytest.raises(ValidationError, match="must agree"):
        build(
            monkeypatch,
            OIA_REDIS_URL="redis://localhost:6379/5",
            OIA_REDIS_DB="7",
        )


def test_url_and_db_agreement_is_accepted(monkeypatch):
    s = build(monkeypatch, OIA_REDIS_URL="redis://localhost:6379/5", OIA_REDIS_DB="5")
    assert s.REDIS_DB == 5


def test_url_without_a_db_index_is_left_alone(monkeypatch):
    """A URL carrying no path keeps the declared default."""
    s = build(monkeypatch, OIA_REDIS_URL="redis://localhost:6379")
    assert s.REDIS_DB == 2


def test_ambient_oia_variables_do_not_leak_into_tests(monkeypatch):
    """Review finding: the suite must not depend on the developer's shell."""
    monkeypatch.setenv("OIA_LOG_LEVEL", "CRITICAL")
    monkeypatch.setenv("OIA_PORT", "9999")
    s = build(monkeypatch)
    assert s.LOG_LEVEL == "INFO"
    assert s.PORT == 8120
