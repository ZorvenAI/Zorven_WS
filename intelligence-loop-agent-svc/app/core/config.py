"""Intelligence Loop Agent service configuration.

All settings use the ILA_ prefix. WF3.5 — closes the feedback loop
across WF1 + WF2 + WF3 by extracting strategic learnings from
campaign performance and dispatching them back as RAG documents
and optional re-run requests.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Intelligence Loop Agent configuration."""

    model_config = SettingsConfigDict(env_prefix="ILA_", case_sensitive=False)

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8045
    SERVICE_NAME: str = "intelligence-loop-agent"
    LOG_LEVEL: str = "INFO"

    # Redis (DB 25)
    REDIS_URL: str = "redis://localhost:6379/25"

    # Service auth
    SERVICE_TOKEN: str = "dev-service-token"

    # Django backend (callbacks + ingest)
    BACKEND_URL: str = "http://localhost:8001"
    BACKEND_SERVICE_TOKEN: str = "dev-service-token"
    CALLBACK_TOKEN: str = "dev-callback-token"

    @property
    def backend_url(self) -> str:
        return self.BACKEND_URL.strip().rstrip("/")

    # Anthropic Claude Sonnet 4 (learning extraction)
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-5-20250929"
    ANTHROPIC_TEMPERATURE: float = 0.2

    # Kafka (optional)
    KAFKA_BOOTSTRAP_SERVERS: str = ""
    AUDIT_TOPIC: str = "ila-intelligence-audit-topic"
    EVENTS_TOPIC: str = "ila-intelligence-events-topic"

    # Behaviour
    DEFAULT_MODE: str = "store_only"  # store_only | auto_trigger
    MIN_CONFIDENCE_AUTO_TRIGGER: int = 75
    WF2_APPROVAL_TIMEOUT_HOURS: int = 72

    # CORS
    CORS_ORIGINS: str = "*"


settings = Settings()
