"""
Application configuration loaded from environment variables.

All settings use the CIA_ prefix. For example:
    CIA_ANTHROPIC_API_KEY=sk-xxx
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Competitor Intelligence Agent service configuration."""

    model_config = SettingsConfigDict(
        env_prefix="CIA_",
        case_sensitive=False,
    )

    # Redis connection (DB 12)
    REDIS_URL: str = "redis://localhost:6379/12"
    # Prompt optimization
    PROMPT_CACHE_REDIS_URL: str = "redis://localhost:6379/2"
    MLFLOW_TRACKING_URI: str = "http://mlflow-server:5000"

    # Kafka connection
    KAFKA_BOOTSTRAP_SERVERS: str = ""
    KAFKA_CONSUMERS_ENABLED: bool = False
    KAFKA_CONSUMER_GROUP: str = "competitor-intel-agent-group"

    # CORS origins (comma-separated)
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8022

    # Logging
    LOG_LEVEL: str = "INFO"

    # LLM — Claude Sonnet 4
    ANTHROPIC_API_KEY: str = ""
    LLM_MODEL: str = "claude-sonnet-5"
    LLM_TEMPERATURE: float = 0.3
    LLM_MAX_TOKENS: int = 32768

    # Data sources
    TAVILY_API_KEY: str = ""
    TAVILY_MCP_SERVER_URL: str = ""

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 10

    # Cache TTLs (seconds)
    RESULT_CACHE_TTL: int = 14400  # 4 hours
    COMPETITOR_PROFILE_TTL: int = 86400  # 24 hours

    # Guardrail settings
    INPUT_MAX_TOKENS: int = 16000  # ~4096 tokens
    OUTPUT_MAX_CHARS: int = 150000
    CONFIDENCE_THRESHOLD: float = 0.7
    TOKEN_BUDGET_PER_SESSION: int = 75000
    MAX_COMPETITORS: int = 20
    MAX_PAGES_PER_DOMAIN: int = 5

    # RBAC
    RBAC_ENABLED: bool = True

    # Circuit breaker
    CB_FAILURE_THRESHOLD: int = 5
    CB_RECOVERY_TIMEOUT: int = 30
    CB_LLM_FAILURE_THRESHOLD: int = 3
    CB_LLM_RECOVERY_TIMEOUT: int = 60

    # RAG service
    RAG_SERVICE_URL: str = "http://localhost:8070"
    RAG_ENABLED: bool = False

    # GCS persistence
    GCS_ENABLED: bool = False
    GCS_CREDENTIALS_JSON: str = ""

    # Service auth
    SERVICE_TOKEN: str = "dev-service-token"

    # Scope topics (IG-03 — comma-separated)
    IN_SCOPE_TOPICS: str = (
        "competitor,competitive,SWOT,benchmarking,positioning,"
        "market_share,competitor_analysis,competitive_intelligence,"
        "brand,business,industry,market"
    )


settings = Settings()
