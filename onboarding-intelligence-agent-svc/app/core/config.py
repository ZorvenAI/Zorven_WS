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
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Memorystore is fixed at 16 databases. Anything outside this range does not
#: exist in production.
MAX_REDIS_DB = 15


def redis_db_from_url(url: str) -> int | None:
    """Extract the database index from a Redis URL, if it carries one."""
    path = urlparse(url).path.lstrip("/")
    if not path:
        return None
    try:
        return int(path)
    except ValueError:
        return None


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
    COVERAGE_GREEN_THRESHOLD: float = 0.7
    LIVE_ANALYSIS_SILENCE_MS: int = 4000
    TRANSCRIPT_BUFFER_MAX: int = 4000
    CONTEXT_SUMMARIZE_AT: float = 0.75
    RETENTION_DAYS_DEFAULT: int = 365
    STT_LANGUAGE_DEFAULT: str = "en-US"
    MAX_CONCURRENT_LIVE_PER_COMPANY: int = 1
    PROCESS_TIMEOUT_S: int = 300
    CONTEXT_WINDOW_TOKENS: int = 1_000_000
    OCR_AWAIT_TIMEOUT_S: int = 30
    COVERAGE_CROSSCHECK_TOLERANCE: float = 0.05

    # ── Extraction (J-03, Design §8.2 SKL-OIA-10) ──────────
    PROCESS_MODEL: str = "gemini-2.0-flash"
    EXTRACTION_MAX_STEPS: int = 40
    EXTRACTION_TEMPERATURE: float = 0.1
    EXTRACTION_RETRY_LIMIT: int = 1

    # ── Output guardrails (J-04, Design §5.3 OG-03) ──────
    OG03_KEY_CONFIDENCE_THRESHOLD: float = 0.6

    # ── Batcher (G-02, Design §4.3) ────────────────────────
    BATCH_WINDOW_S: float = 3.0
    BATCH_MIN_DURATION_S: float = 0.4

    # ── STT v2 (F-05) ───────────────────────────────────────
    STT_PROJECT: str = ""
    STT_LOCATION: str = "global"
    STT_RECOGNIZER: str = "_"
    STT_STREAM_LIMIT_S: int = 280
    PII_ENTITIES: str = (
        "PERSON,PHONE_NUMBER,EMAIL_ADDRESS,CREDIT_CARD,"
        "IBAN_CODE,US_SSN,US_ITIN,LOCATION"
    )

    # ── Video OCR (H-04, Design §8.4) ─────────────────────────
    VIDEO_MAX_FRAMES: int = 30
    VIDEO_FPS: float = 1.0
    VIDEO_DEDUP_THRESHOLD: int = 8
    VIDEO_MAX_DURATION_S: int = 120

    # ── Secret references (never inline; Design §19) ─────────
    STT_CREDENTIALS: str = ""
    GEMINI_KEY: str = ""
    #: Empty is a supported state, not a misconfiguration: research degrades
    #: to the operator-provided information only (C-02 AC-3), which is the
    #: same path the tavily breaker takes when it opens. Local development and
    #: CI run this way.
    TAVILY_API_KEY: str = ""
    SERVICE_TOKEN: str = ""
    POI_TOKEN: str = ""
    POI_URL: str = ""

    # ── Observability ────────────────────────────────────────
    OTEL_EXPORTER_ENDPOINT: str = ""

    @field_validator(
        "SUFFICIENCY_GREEN_THRESHOLD",
        "COVERAGE_GREEN_THRESHOLD",
        "CONTEXT_SUMMARIZE_AT",
    )
    @classmethod
    def _must_be_a_fraction(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("must be between 0.0 and 1.0")
        return v

    @field_validator("REDIS_DB", "POI_PROMPT_CACHE_DB")
    @classmethod
    def _must_exist_on_memorystore(cls, v: int) -> int:
        # A value outside 0-15 is the DB 27 mistake ERRATA-01 exists to
        # prevent, and it fails silently at runtime — the agent RedisManagers
        # fail open and run cacheless.
        if not 0 <= v <= MAX_REDIS_DB:
            raise ValueError(_bad_db_message(v))
        return v

    @model_validator(mode="after")
    def _redis_url_agrees_with_redis_db(self) -> "Settings":
        """Validate the database index that is actually connected to.

        REDIS_URL is what RedisManager.connect() dials; REDIS_DB is what
        /health/diagnostics reports. Validating only the latter would let
        OIA_REDIS_URL=redis://host:6379/27 through — the precise
        misconfiguration this class exists to reject — and would let
        diagnostics report a database the service is not using.

        When only the URL is set, REDIS_DB follows it. When both are set they
        must agree.
        """
        url_db = redis_db_from_url(self.REDIS_URL)
        if url_db is None:
            return self

        if not 0 <= url_db <= MAX_REDIS_DB:
            raise ValueError(f"REDIS_URL: {_bad_db_message(url_db)}")

        if "REDIS_DB" in self.model_fields_set:
            if url_db != self.REDIS_DB:
                raise ValueError(
                    f"REDIS_URL selects DB {url_db} but REDIS_DB is "
                    f"{self.REDIS_DB}. They must agree — the URL is what the "
                    "service connects to and REDIS_DB is what /health "
                    "reports, so a mismatch makes diagnostics lie."
                )
        else:
            object.__setattr__(self, "REDIS_DB", url_db)

        return self

    @property
    def kafka_enabled(self) -> bool:
        """Whether this environment has a Kafka broker at all."""
        return bool(self.KAFKA_BOOTSTRAP_SERVERS.strip())


def _bad_db_message(db: int) -> str:
    return (
        f"Redis DB {db} does not exist in production. Memorystore is fixed at "
        f"16 databases (0-{MAX_REDIS_DB}); OIA uses DB 2 with the oia:v1: key "
        "prefix (ERRATA-01)."
    )


@lru_cache
def get_settings() -> Settings:
    """Process-wide settings singleton."""
    return Settings()  # type: ignore[call-arg]
