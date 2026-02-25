"""
Application configuration loaded from environment variables.

All settings use the TITLING_ prefix. For example:
    TITLING_GOOGLE_API_KEY=AIza...
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Chat titling worker configuration."""

    model_config = SettingsConfigDict(
        env_prefix="TITLING_",
        case_sensitive=False,
    )

    # Redis connection
    REDIS_URL: str = "redis://localhost:6379/4"

    # Kafka connection
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_GROUP_ID: str = "titling-consumers"
    KAFKA_TOPIC: str = "chat-titling-topic"

    # Google Gemini (empty = stub mode)
    GOOGLE_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"

    # Core API callback
    CORE_API_URL: str = "http://localhost:8001"
    WORKER_TOKEN: str = "dev-worker-token"

    # CORS origins (comma-separated)
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8040

    # Logging
    LOG_LEVEL: str = "INFO"


settings = Settings()
