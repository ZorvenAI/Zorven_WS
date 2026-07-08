"""Ad Publishing Agent service configuration loaded from environment variables.

All settings use the ADPUB_ prefix. For example:
    ADPUB_SERVICE_TOKEN=my-secret-token
    ADPUB_META_ADS_SANDBOX_MODE=true
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Ad Publishing Agent configuration."""

    model_config = SettingsConfigDict(
        env_prefix="ADPUB_",
        case_sensitive=False,
    )

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8043
    SERVICE_NAME: str = "ad-publishing-agent"
    LOG_LEVEL: str = "INFO"

    # Redis (DB 23)
    REDIS_URL: str = "redis://localhost:6379/23"
    # Prompt optimization
    PROMPT_CACHE_REDIS_URL: str = "redis://localhost:6379/2"
    MLFLOW_TRACKING_URI: str = "http://mlflow-server:5000"

    # Anthropic Claude Sonnet 4 (targeting translation)
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-5"
    ANTHROPIC_MAX_TOKENS: int = 4096
    ANTHROPIC_TEMPERATURE: float = 0.2  # Low for targeting precision

    # Meta Marketing API v21.0
    META_APP_ID: str = ""
    META_APP_SECRET: str = ""
    META_API_VERSION: str = "v21.0"
    META_ADS_SANDBOX_MODE: bool = True  # DEFAULT: sandbox (no real spend)

    # Service auth
    SERVICE_TOKEN: str = "dev-service-token"

    # Django backend (context loading + callbacks)
    BACKEND_URL: str = "http://localhost:8001"
    BACKEND_SERVICE_TOKEN: str = "dev-service-token"

    @property
    def backend_url(self) -> str:
        """BACKEND_URL with whitespace stripped."""
        return self.BACKEND_URL.strip().rstrip("/")

    # Kafka (optional)
    KAFKA_BOOTSTRAP_SERVERS: str = ""
    KAFKA_CONSUMERS_ENABLED: bool = False

    # GCS (read creative package images)
    GCS_PROJECT_ID: str = ""
    GCS_BUCKET_NAME: str = ""
    GCS_CREDENTIALS_PATH: str = ""
    GCS_CREDENTIALS_JSON: str = ""

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"

    # Caching
    RESULT_CACHE_TTL: int = 14400  # 4 hours
    IDEMPOTENCY_TTL: int = 86400  # 24 hours

    # Approval gate (24h expiry — HARDCODED in logic, config only for Redis TTL)
    APPROVAL_EXPIRY_SECONDS: int = 86400

    # Budget guardrails
    DAILY_SPEND_CAP_USD: float = 500.0
    MAX_CAMPAIGN_BUDGET_USD: float = 10000.0

    # Guardrails
    CONFIDENCE_THRESHOLD: float = 0.7
    MIN_AUDIENCE_SIZE: int = 10000
    TOKEN_BUDGET_PER_SESSION: int = 100000


settings = Settings()
