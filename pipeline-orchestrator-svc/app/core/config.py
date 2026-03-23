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

    # Callback URL override — when set, the orchestrator constructs callback
    # URLs from this base instead of using the URL from the dispatch payload.
    # Set to the Django backend's private networking URL on Railway, e.g.
    # http://previsionws.railway.internal:8000
    CALLBACK_BASE_URL: str = ""

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

    # Gemini composition retry (Tier 1)
    GEMINI_COMPOSE_MAX_RETRIES: int = 1
    GEMINI_COMPOSE_RETRY_DELAY: float = 2.0

    # RAG query cache
    RAG_QUERY_CACHE_TTL: int = 3600
    RAG_SESSION_FILES_TTL: int = 86400

    # External agent HTTP timeout (seconds). Content and social agents
    # may take 10+ minutes for blog authoring / publishing.
    AGENT_TIMEOUT: float = 900.0

    # Agent service URLs (override for Railway/cloud deployment)
    DISCOVERY_AGENT_URL: str = "http://discovery-agent-svc:8020"
    CONTENT_AGENT_URL: str = "http://content-agent-svc:8050"
    SOCIAL_AGENT_URL: str = "http://social-agent-svc:8060"
    INTELLIGENCE_AGENT_URL: str = "http://intelligence-agent-svc:8030"
    RAG_UPLOADER_AGENT_URL: str = "http://rag-uploader-agent-svc:8070"
    ODOO_WORKER_AGENT_URL: str = "http://odoo-worker-agent:8100"
    MARKET_RESEARCH_AGENT_URL: str = "http://market-research-agent-svc:8021"
    COMPETITOR_INTEL_AGENT_URL: str = "http://competitor-intel-agent-svc:8022"
    AUDIENCE_PERSONA_AGENT_URL: str = "http://audience-persona-agent-svc:8023"
    TREND_CULTURAL_AGENT_URL: str = "http://trend-cultural-agent-svc:8024"
    VOC_AGENT_URL: str = "http://voc-agent-svc:8025"
    BRAND_POSITIONING_AGENT_URL: str = "http://brand-positioning-agent-svc:8031"


settings = Settings()
