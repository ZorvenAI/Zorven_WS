"""NTA service configuration loaded from environment variables.

All settings use the NTA_ prefix. For example:
    NTA_SERVICE_TOKEN=my-secret-token
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Naming & Tagline Agent configuration."""

    model_config = SettingsConfigDict(
        env_prefix="NTA_",
        case_sensitive=False,
    )

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8034
    SERVICE_NAME: str = "brand-naming-agent"
    LOG_LEVEL: str = "INFO"

    # Redis (DB 19)
    REDIS_URL: str = "redis://localhost:6379/19"
    # Prompt optimization
    PROMPT_CACHE_REDIS_URL: str = "redis://localhost:6379/2"
    MLFLOW_TRACKING_URI: str = "http://mlflow-server:5000"

    # Anthropic Claude Sonnet 4
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-5-20250929"
    ANTHROPIC_MAX_TOKENS: int = 8192
    ANTHROPIC_TEMPERATURE: float = 0.4

    # Service auth
    SERVICE_TOKEN: str = "dev-service-token"

    # Django backend (WF1 + BPA + BPV + Company context)
    BACKEND_URL: str = "http://localhost:8001"
    BACKEND_SERVICE_TOKEN: str = "dev-service-token"

    # Kafka (optional)
    KAFKA_BOOTSTRAP_SERVERS: str = ""
    KAFKA_CONSUMERS_ENABLED: bool = False

    # GCS (naming results persistence)
    GCS_BUCKET_PREFIX: str = ""
    GCS_CREDENTIALS_JSON: str = ""

    # Vertex AI RAG
    VERTEX_PROJECT_ID: str = ""
    VERTEX_LOCATION: str = "us-central1"
    RAG_SERVICE_URL: str = ""

    # Tavily (trademark search)
    TAVILY_API_KEY: str = ""

    # Naming config
    MAX_NAME_CANDIDATES: int = 15
    MIN_NAME_CANDIDATES: int = 7
    SHORTLIST_SIZE: int = 5
    DOMAIN_CHECK_TLDS: str = ".com,.io,.co"
    SOCIAL_PLATFORMS: str = "twitter,instagram,linkedin"

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"

    # Caching
    RESULT_CACHE_TTL: int = 14400  # 4 hours
    IDEMPOTENCY_TTL: int = 86400  # 24 hours

    # Guardrails
    CONFIDENCE_THRESHOLD: float = 0.7
    TOKEN_BUDGET_PER_SESSION: int = 100000


settings = Settings()
