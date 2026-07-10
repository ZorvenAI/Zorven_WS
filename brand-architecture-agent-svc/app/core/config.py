"""
Application configuration loaded from environment variables.

All settings use the BAA_ prefix. For example:
    BAA_ANTHROPIC_API_KEY=sk-xxx
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Brand Architecture Agent service configuration."""

    model_config = SettingsConfigDict(
        env_prefix="BAA_",
        case_sensitive=False,
    )

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8032
    SERVICE_NAME: str = "brand-architecture-agent"
    LOG_LEVEL: str = "INFO"

    # Redis connection (DB 17)
    REDIS_URL: str = "redis://localhost:6379/17"
    # Prompt optimization
    PROMPT_CACHE_REDIS_URL: str = "redis://localhost:6379/2"
    MLFLOW_TRACKING_URI: str = "http://mlflow-server:5000"
    PROMPT_FALLBACK_ONLY: bool = False

    # LLM — Claude Sonnet 4
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-5"
    ANTHROPIC_MAX_TOKENS: int = 8192
    ANTHROPIC_TEMPERATURE: float = 0.4

    # Tavily (supplementary research)
    TAVILY_API_KEY: str = ""

    # Auth
    SERVICE_TOKEN: str = "dev-service-token"

    # Django backend (WF1 + BPA + Company context)
    BACKEND_URL: str = "http://localhost:8001"
    BACKEND_SERVICE_TOKEN: str = "dev-service-token"

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = ""
    KAFKA_CONSUMERS_ENABLED: bool = False

    # GCS (strategy persistence)
    GCS_BUCKET_PREFIX: str = ""
    GCS_CREDENTIALS_JSON: str = ""

    # Vertex AI RAG
    VERTEX_PROJECT_ID: str = ""
    VERTEX_LOCATION: str = "us-central1"

    # RAG service
    RAG_SERVICE_URL: str = ""

    # Architecture config
    MAX_SUB_BRAND_COUNT: int = 15
    MAX_HIERARCHY_DEPTH: int = 4

    # CORS origins (comma-separated)
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"

    # Cache TTLs (seconds)
    RESULT_CACHE_TTL: int = 14400  # 4 hours
    IDEMPOTENCY_TTL: int = 86400  # 24 hours

    # Circuit breaker
    CB_FAILURE_THRESHOLD: int = 5
    CB_RECOVERY_TIMEOUT: int = 30

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 10

    # Guardrails
    TOKEN_BUDGET_PER_SESSION: int = 100000
    CONFIDENCE_THRESHOLD: float = 0.7


settings = Settings()
