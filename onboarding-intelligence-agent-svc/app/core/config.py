"""Typed configuration for the Onboarding Intelligence Agent.

Every setting carries the ``OIA_`` prefix, matching the fleet convention. The
thirteen settings in Design §19 are all declared here with their documented
defaults.

Settings with no default are **required**: the service fails at startup with a
Pydantic validation error naming the missing variable, rather than starting and
failing on the first meeting (A-05 AC-2).

Redis note (ERRATA-01). OIA lives in **DB 2** behind the ``oia:v1:`` key
prefix, not DB 27. Production Redis is Memorystore, which is fixed at 16
databases (0–15) and exposes no ``databases`` tunable, so DB 27 cannot exist
there. The default below is the production-safe value so a missing environment
variable fails safe rather than pointing at a database that does not exist.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Onboarding Intelligence Agent service configuration."""

    model_config = SettingsConfigDict(
        env_prefix="OIA_",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Server ───────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8120
    LOG_LEVEL: str = "INFO"

    # ── Redis (ERRATA-01: DB 2, not 27) ──────────────────────
    REDIS_URL: str = "redis://localhost:6379/2"
    REDIS_DB: int = 2
    # The prompt cache is read-only and shares DB 2 under the poi: prefix.
    POI_PROMPT_CACHE_DB: int = 2

    # ── Required: no default, so absence fails at startup ────
    BACKEND_BASE_URL: str = Field(..., description="Django API root")
    GCS_BUCKET: str = Field(..., description="Tenant asset bucket")

    # ── Kafka (optional — see health semantics below) ────────
    #
    # There is no Kafka broker in GCP: no deployment/gcp script provisions
    # one and every deployed service sets *_KAFKA_ENABLED=false. An empty
    # bootstrap string therefore means "Kafka is not part of this
    # environment", and /health does not fail for its absence. When a broker
    # IS configured, it becomes a hard health dependency.
    KAFKA_BOOTSTRAP_SERVERS: str = ""

    # ── Behavioural settings (Design §19) ────────────────────
    SUFFICIENCY_GREEN_THRESHOLD: float = 0.7
    LIVE_ANALYSIS_SILENCE_MS: int = 4000
    TRANSCRIPT_BUFFER_MAX: int = 4000
    CONTEXT_SUMMARIZE_AT: float = 0.75
    RETENTION_DAYS_DEFAULT: int = 365
    STT_LANGUAGE_DEFAULT: str = "en-US"
    MAX_CONCURRENT_LIVE_PER_COMPANY: int = 1
    PROCESS_TIMEOUT_S: int = 300

    # ── Secret references (never inline; Design §19) ─────────
    STT_CREDENTIALS: str = ""
    GEMINI_KEY: str = ""
    SERVICE_TOKEN: str = ""
    POI_TOKEN: str = ""

    # ── Observability ────────────────────────────────────────
    OTEL_EXPORTER_ENDPOINT: str = ""

    @field_validator("SUFFICIENCY_GREEN_THRESHOLD", "CONTEXT_SUMMARIZE_AT")
    @classmethod
    def _must_be_a_fraction(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("must be between 0.0 and 1.0")
        return v

    @field_validator("REDIS_DB", "POI_PROMPT_CACHE_DB")
    @classmethod
    def _must_exist_on_memorystore(cls, v: int) -> int:
        # Memorystore is fixed at 16 databases. A value outside 0–15 is the
        # DB 27 mistake ERRATA-01 exists to prevent, and it fails silently at
        # runtime — the agent RedisManagers fail open and run cacheless.
        if not 0 <= v <= 15:
            raise ValueError(
                f"Redis DB {v} does not exist in production. Memorystore is "
                "fixed at 16 databases (0-15); OIA uses DB 2 with the "
                "oia:v1: key prefix (ERRATA-01)."
            )
        return v

    @property
    def kafka_enabled(self) -> bool:
        """Whether this environment has a Kafka broker at all."""
        return bool(self.KAFKA_BOOTSTRAP_SERVERS.strip())


@lru_cache
def get_settings() -> Settings:
    """Process-wide settings singleton."""
    return Settings()  # type: ignore[call-arg]
