"""
Application configuration loaded from environment variables.

All settings use the VOCA_ prefix. For example:
    VOCA_ANTHROPIC_API_KEY=sk-xxx
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Voice of Customer Agent service configuration."""

    model_config = SettingsConfigDict(
        env_prefix="VOCA_",
        case_sensitive=False,
    )

    # Redis connection (DB 15)
    REDIS_URL: str = "redis://localhost:6379/15"

    # Kafka connection
    KAFKA_BOOTSTRAP_SERVERS: str = ""

    # CORS origins (comma-separated)
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8025

    # Logging
    LOG_LEVEL: str = "INFO"

    # LLM — Claude Sonnet 4
    ANTHROPIC_API_KEY: str = ""
    LLM_MODEL: str = "claude-sonnet-4-5-20250929"
    LLM_TEMPERATURE: float = 0.3
    LLM_MAX_TOKENS: int = 16384

    # Data sources
    TAVILY_API_KEY: str = ""
    TAVILY_MCP_SERVER_URL: str = ""

    # RAG service
    RAG_SERVICE_URL: str = ""

    # GCS (for report persistence)
    GCS_PROJECT_ID: str = ""
    GCS_BUCKET_NAME: str = ""
    GCS_CREDENTIALS_JSON: str = ""

    # Odoo integration (feature-flagged)
    ODOO_ENABLED: bool = False
    ODOO_URL: str = ""
    ODOO_DB: str = ""
    ODOO_USERNAME: str = ""
    ODOO_PASSWORD: str = ""

    # Django backend
    CORE_API_URL: str = "http://localhost:8001"
    CORE_API_TOKEN: str = "dev-service-token"

    # Auth
    SERVICE_TOKEN: str = "dev-service-token"

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 10

    # Cache TTLs (seconds)
    RESULT_CACHE_TTL: int = 14400  # 4 hours
    IDEMPOTENCY_TTL: int = 86400  # 24 hours
    ODOO_CACHE_TTL: int = 1800  # 30 minutes (helpdesk/chatter)
    ODOO_SURVEY_CACHE_TTL: int = 3600  # 1 hour

    # Guardrail settings
    TOKEN_BUDGET_PER_SESSION: int = 100000  # PG-07 (highest in WF1)
    MAX_FEEDBACK_ITEMS: int = 5000  # PG-08
    INPUT_MAX_TOKENS: int = 8192  # IG-06 (higher for bulk feedback)
    OUTPUT_MAX_CHARS: int = 150000  # OG-06
    GROUNDING_THRESHOLD: float = 0.8
    CONFIDENCE_THRESHOLD: float = 0.7
    MAX_CONCURRENT_RESEARCH: int = 6  # PG-04

    # Circuit breaker thresholds
    CB_FAILURE_THRESHOLD: int = 5
    CB_RECOVERY_TIMEOUT: int = 30
    CB_LLM_FAILURE_THRESHOLD: int = 3
    CB_LLM_RECOVERY_TIMEOUT: int = 60
    CB_ODOO_FAILURE_THRESHOLD: int = 3
    CB_ODOO_RECOVERY_TIMEOUT: int = 60

    # Kafka consumers
    KAFKA_CONSUMERS_ENABLED: bool = False

    # Customer ID hashing (Decision #5)
    HASH_LOOKUP_TTL: int = 7776000  # 90 days

    # VoC health score weights (Decision #4)
    VOC_HEALTH_NPS_WEIGHT: float = 0.50
    VOC_HEALTH_SENTIMENT_WEIGHT: float = 0.25
    VOC_HEALTH_THEME_WEIGHT: float = 0.25

    # Continuous ingestion (Decision #3)
    INGESTION_POLL_INTERVAL: int = 900  # 15 minutes
    INGESTION_KAFKA_HEALTH_CHECK_INTERVAL: int = 60  # 60 seconds
    INGESTION_CONSUMER_GROUP: str = "voc-agent-ingestion-cg"


settings = Settings()
