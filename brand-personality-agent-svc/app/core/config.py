"""BPV service configuration loaded from environment variables.

All settings use the BPV_ prefix. For example:
    BPV_SERVICE_TOKEN=my-secret-token
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Brand Personality & Values Agent configuration."""

    model_config = SettingsConfigDict(
        env_prefix="BPV_",
        case_sensitive=False,
    )

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8033
    SERVICE_NAME: str = "brand-personality-agent"
    LOG_LEVEL: str = "INFO"

    # Redis (DB 18)
    REDIS_URL: str = "redis://localhost:6379/18"

    # Anthropic Claude Sonnet 4
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"
    ANTHROPIC_MAX_TOKENS: int = 8192
    ANTHROPIC_TEMPERATURE: float = 0.4

    # Service auth
    SERVICE_TOKEN: str = "dev-service-token"

    # Django backend (WF1 + BPA + Company context)
    BACKEND_URL: str = "http://localhost:8001"
    BACKEND_SERVICE_TOKEN: str = "dev-service-token"

    # Kafka (optional)
    KAFKA_BOOTSTRAP_SERVERS: str = ""
    KAFKA_CONSUMERS_ENABLED: bool = False

    # GCS (personality persistence — deferred to v2)
    GCS_BUCKET_PREFIX: str = ""
    GCS_CREDENTIALS_JSON: str = ""

    # Vertex AI RAG
    VERTEX_PROJECT_ID: str = ""
    VERTEX_LOCATION: str = "us-central1"
    RAG_SERVICE_URL: str = ""

    # Personality config
    MAX_CORE_VALUES: int = 5
    MAX_SUPPORTING_VALUES: int = 5
    MAX_ASPIRATIONAL_VALUES: int = 3

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"

    # Caching
    RESULT_CACHE_TTL: int = 14400  # 4 hours
    IDEMPOTENCY_TTL: int = 86400  # 24 hours

    # Guardrails
    CONFIDENCE_THRESHOLD: float = 0.7
    TOKEN_BUDGET_PER_SESSION: int = 100000


settings = Settings()
