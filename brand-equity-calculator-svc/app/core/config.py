"""Service configuration — all settings from BRAND_EQUITY_ prefixed env vars."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BRAND_EQUITY_",
        case_sensitive=False,
    )

    # Anthropic Claude (empty = service unavailable, returns 503)
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_MODEL: str = "claude-opus-4-6"

    # Redis (DB 8)
    REDIS_URL: str = "redis://localhost:6379/8"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8090

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"

    # Logging
    LOG_LEVEL: str = "INFO"

    # Rate limiting (IP-based for public endpoint)
    RATE_LIMIT_PER_MINUTE: int = 5

    # Cache TTL (24 hours)
    RESULT_CACHE_TTL: int = 86400


settings = Settings()
