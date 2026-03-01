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

    # CORS origins (comma-separated list of allowed origins)
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8010

    # Logging
    LOG_LEVEL: str = "INFO"

    # Vertex AI Search (RAG queries)
    VERTEX_AI_PROJECT_ID: str = "brandsol-project"
    VERTEX_AI_LOCATION: str = "global"
    VERTEX_AI_DATA_STORE_ID: str = "prevision-rag-dev"

    # GCP credentials (service account JSON, for GCS + Vertex AI)
    GCS_CREDENTIALS_JSON: str = ""

    # Gemini (answer synthesis)
    GOOGLE_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"
    GEMINI_TEMPERATURE: float = 0.3

    # RAG query cache
    RAG_QUERY_CACHE_TTL: int = 3600
    RAG_SESSION_FILES_TTL: int = 86400

    # Agent service URLs (override for Railway/cloud deployment)
    DISCOVERY_AGENT_URL: str = "http://discovery-agent-svc:8020"
    CONTENT_AGENT_URL: str = "http://content-agent-svc:8050"
    SOCIAL_AGENT_URL: str = "http://social-agent-svc:8060"
    INTELLIGENCE_AGENT_URL: str = "http://intelligence-agent-svc:8030"
    RAG_UPLOADER_AGENT_URL: str = "http://rag-uploader-agent-svc:8070"


settings = Settings()
