"""
Application configuration loaded from environment variables.

All settings use the MRA_ prefix. For example:
    MRA_ANTHROPIC_API_KEY=sk-xxx
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Market Research Agent service configuration."""

    model_config = SettingsConfigDict(
        env_prefix="MRA_",
        case_sensitive=False,
    )

    # Redis connection (DB 11)
    REDIS_URL: str = "redis://localhost:6379/11"
    # Prompt optimization
    PROMPT_CACHE_REDIS_URL: str = "redis://localhost:6379/2"
    MLFLOW_TRACKING_URI: str = "http://mlflow-server:5000"

    # Kafka connection
    KAFKA_BOOTSTRAP_SERVERS: str = ""

    # CORS origins (comma-separated)
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8021

    # Logging
    LOG_LEVEL: str = "INFO"

    # LLM — Claude Sonnet 4 (tenant-configurable)
    ANTHROPIC_API_KEY: str = ""
    LLM_MODEL: str = "claude-sonnet-5"
    LLM_TEMPERATURE: float = 0.3
    LLM_MAX_TOKENS: int = 16384

    # Data sources
    TAVILY_API_KEY: str = ""
    TAVILY_MCP_SERVER_URL: str = ""
    GNEWS_API_KEY: str = ""
    WORLD_BANK_BASE_URL: str = "https://api.worldbank.org/v2"

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 10

    # Cache TTLs (seconds)
    RESEARCH_CACHE_TTL: int = 14400  # 4 hours
    ECONOMIC_DATA_CACHE_TTL: int = 86400  # 24 hours
    NEWS_CACHE_TTL: int = 3600  # 1 hour

    # Guardrail settings
    INPUT_MAX_TOKENS: int = 16000  # ~4096 tokens
    OUTPUT_MAX_CHARS: int = 100000
    CONFIDENCE_THRESHOLD: float = 0.7
    TOKEN_BUDGET_PER_SESSION: int = 50000
    MAX_CONCURRENT_REQUESTS: int = 5

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

    # Scope topics (IG-03 — comma-separated)
    IN_SCOPE_TOPICS: str = (
        "market_research,industry_analysis,market_sizing,"
        "trend_analysis,economic_indicators"
    )


settings = Settings()
