"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SOCIAL_",
        case_sensitive=False,
    )

    REDIS_URL: str = "redis://localhost:6379/6"
    # Prompt optimization
    PROMPT_CACHE_REDIS_URL: str = "redis://localhost:6379/2"
    MLFLOW_TRACKING_URI: str = "http://prompt-optimization-svc:8110"
    PROMPT_FALLBACK_ONLY: bool = False
    KAFKA_BOOTSTRAP_SERVERS: str = ""
    GOOGLE_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash"
    CORE_API_URL: str = "http://localhost:8001"
    CORE_API_TOKEN: str = "dev-service-token"
    RATE_LIMIT_PER_MINUTE: int = 10
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"
    HOST: str = "0.0.0.0"
    PORT: int = 8060
    LOG_LEVEL: str = "INFO"
    # MCP server
    MCP_SERVER_URL: str = ""
    # Kafka topics
    CONTENT_PUBLISHED_TOPIC: str = "content-published-topic"
    SOCIAL_AUDIT_TOPIC: str = "social-audit-topic"


settings = Settings()
