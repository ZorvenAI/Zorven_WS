"""
Application configuration loaded from environment variables.

All settings use the ORCHESTRATOR_ prefix. For example:
    ORCHESTRATOR_SERVICE_TOKEN=my-secret-token
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Pipeline orchestrator service configuration."""

    model_config = SettingsConfigDict(
        env_prefix="ORCHESTRATOR_",
        case_sensitive=False,
    )

    # Auth tokens (shared secrets with core-api-service)
    SERVICE_TOKEN: str = "dev-service-token"
    CALLBACK_TOKEN: str = "dev-callback-token"

    # Redis connection
    REDIS_URL: str = "redis://localhost:6379/1"

    # Kafka connection
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8010

    # Logging
    LOG_LEVEL: str = "INFO"


settings = Settings()
