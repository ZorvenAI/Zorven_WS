"""
Application configuration loaded from environment variables.

All settings use the DISCOVERY_ prefix. For example:
    DISCOVERY_TAVILY_API_KEY=tvly-xxx
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Discovery agent service configuration."""

    model_config = SettingsConfigDict(
        env_prefix="DISCOVERY_",
        case_sensitive=False,
    )

    # Redis connection
    REDIS_URL: str = "redis://localhost:6379/2"

    # Kafka connection
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"

    # Tavily search API key (empty = stub mode)
    TAVILY_API_KEY: str = ""
    TAVILY_MCP_SERVER_URL: str = ""

    # CORS origins (comma-separated)
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8020

    # Logging
    LOG_LEVEL: str = "INFO"

    # Scraping limits
    MAX_SCRAPE_URLS: int = 10
    SCRAPE_TIMEOUT: int = 30

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 10

    # GCS (empty = stub mode)
    GCS_PROJECT_ID: str = ""
    GCS_BUCKET_NAME: str = ""
    GCS_CREDENTIALS_PATH: str = ""


settings = Settings()
