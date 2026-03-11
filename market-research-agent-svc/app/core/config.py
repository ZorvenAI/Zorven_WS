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
    LLM_MODEL: str = "claude-sonnet-4-20250514"
    LLM_TEMPERATURE: float = 0.3
    LLM_MAX_TOKENS: int = 4096

    # Data sources
    TAVILY_API_KEY: str = ""
    GNEWS_API_KEY: str = ""
    WORLD_BANK_BASE_URL: str = "https://api.worldbank.org/v2"

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 10

    # Cache TTLs (seconds)
    RESEARCH_CACHE_TTL: int = 14400  # 4 hours
    ECONOMIC_DATA_CACHE_TTL: int = 86400  # 24 hours
    NEWS_CACHE_TTL: int = 3600  # 1 hour


settings = Settings()
