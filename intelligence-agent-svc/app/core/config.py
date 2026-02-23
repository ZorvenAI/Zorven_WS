"""
Application configuration loaded from environment variables.

All settings use the INTELLIGENCE_ prefix. For example:
    INTELLIGENCE_GEMINI_API_KEY=AIza...
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Intelligence agent service configuration."""

    model_config = SettingsConfigDict(
        env_prefix="INTELLIGENCE_",
        case_sensitive=False,
    )

    # Redis connection
    REDIS_URL: str = "redis://localhost:6379/3"

    # Kafka connection
    KAFKA_BOOTSTRAP_SERVERS: str = ""

    # Gemini AI (empty = stub mode, rule-based only)
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"

    # CORS origins (comma-separated)
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8030

    # Logging
    LOG_LEVEL: str = "INFO"

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 10

    # GCS (empty = stub mode)
    GCS_PROJECT_ID: str = ""
    GCS_BUCKET_NAME: str = ""
    GCS_CREDENTIALS_PATH: str = ""

    # Vertex AI RAG (empty = stub mode)
    RAG_PROJECT_ID: str = ""
    RAG_LOCATION: str = "us-central1"

    # ISO calculation defaults
    DEFAULT_HORIZON_YEARS: int = 5
    DEFAULT_TAX_RATE: float = 0.25
    DEFAULT_DISCOUNT_RATE: float = 0.10
    DEFAULT_TERMINAL_GROWTH_RATE: float = 0.025  # Long-term GDP-like growth


settings = Settings()
