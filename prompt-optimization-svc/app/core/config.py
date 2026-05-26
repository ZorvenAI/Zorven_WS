"""Prompt Optimization Service configuration via environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Service configuration loaded from POI_* environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="POI_",
        case_sensitive=False,
    )

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8110

    # MLflow Tracking Server
    MLFLOW_TRACKING_URI: str = "http://mlflow-server:5000"

    # PostgreSQL (shared with MLflow backend store)
    DATABASE_URL: str = "postgresql://mlflow:mlflow@mlflow-db:5432/mlflow"

    # Redis (DB 26 — general service cache/rate-limiting)
    REDIS_URL: str = "redis://localhost:6379/26"

    # Redis (DB 2 — prompt cache, optimization locks, progress tracking)
    PROMPT_CACHE_REDIS_URL: str = "redis://localhost:6379/2"

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = ""

    # Anthropic
    ANTHROPIC_API_KEY: str = ""

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/26"

    # Mining
    MINING_QUALITY_THRESHOLD: float = 0.8
    MINING_LOOKBACK_DAYS: int = 7

    # Logging
    LOG_LEVEL: str = "INFO"

    # Service auth
    SERVICE_TOKEN: str = ""
    JWT_SECRET: str = ""


settings = Settings()
