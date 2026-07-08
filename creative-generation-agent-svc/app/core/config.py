"""CGA service configuration loaded from environment variables.

All settings use the CGA_ prefix. For example:
    CGA_SERVICE_TOKEN=my-secret-token
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Creative Generation Agent configuration."""

    model_config = SettingsConfigDict(
        env_prefix="CGA_",
        case_sensitive=False,
    )

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8042
    SERVICE_NAME: str = "creative-generation-agent"
    LOG_LEVEL: str = "INFO"

    # Redis (DB 22)
    REDIS_URL: str = "redis://localhost:6379/22"
    # Prompt optimization
    PROMPT_CACHE_REDIS_URL: str = "redis://localhost:6379/2"
    MLFLOW_TRACKING_URI: str = "http://mlflow-server:5000"

    # Anthropic Claude Sonnet 4 (copy generation + assembly)
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-5"
    ANTHROPIC_MAX_TOKENS: int = 8192
    ANTHROPIC_TEMPERATURE: float = 0.4

    # Nano Banana 2 image generation (google-genai)
    GOOGLE_API_KEY: str = ""
    IMAGE_GEN_MODEL: str = "gemini-2.5-flash-image"
    DEFAULT_IMAGES_PER_ADSET: int = 3
    MAX_IMAGE_GEN_RETRIES: int = 3

    # Service auth
    SERVICE_TOKEN: str = "dev-service-token"

    # Django backend (context loading)
    BACKEND_URL: str = "http://localhost:8001"
    BACKEND_SERVICE_TOKEN: str = "dev-service-token"

    # Kafka (optional)
    KAFKA_BOOTSTRAP_SERVERS: str = ""
    KAFKA_CONSUMERS_ENABLED: bool = False

    # GCS (image + package persistence)
    GCS_PROJECT_ID: str = ""
    GCS_BUCKET_NAME: str = ""
    GCS_CREDENTIALS_PATH: str = ""
    GCS_CREDENTIALS_JSON: str = ""

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"

    # Caching
    RESULT_CACHE_TTL: int = 14400  # 4 hours
    IDEMPOTENCY_TTL: int = 86400  # 24 hours

    # Guardrails
    CONFIDENCE_THRESHOLD: float = 0.7
    TOKEN_BUDGET_PER_SESSION: int = 100000


settings = Settings()
