"""
Application configuration loaded from environment variables.

All settings use the CONTENT_ prefix. For example:
    CONTENT_GOOGLE_API_KEY=AIza...
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Content agent service configuration."""

    model_config = SettingsConfigDict(
        env_prefix="CONTENT_",
        case_sensitive=False,
    )

    # Redis connection
    REDIS_URL: str = "redis://localhost:6379/5"

    # Prompt optimization
    PROMPT_CACHE_REDIS_URL: str = "redis://localhost:6379/2"
    MLFLOW_TRACKING_URI: str = "http://prompt-optimization-svc:8110"
    PROMPT_FALLBACK_ONLY: bool = False

    # Kafka connection
    KAFKA_BOOTSTRAP_SERVERS: str = ""

    # Gemini AI (empty = stub mode)
    GOOGLE_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"

    # GCS (empty = stub mode)
    GCS_PROJECT_ID: str = ""
    GCS_BUCKET_NAME: str = ""
    GCS_CREDENTIALS_PATH: str = ""
    GCS_CREDENTIALS_JSON: str = ""

    # Core API (brand persona fetch)
    CORE_API_URL: str = "http://localhost:8001"
    CORE_API_TOKEN: str = "dev-service-token"

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 10

    # CORS origins (comma-separated)
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8050

    # Logging
    LOG_LEVEL: str = "INFO"


settings = Settings()
