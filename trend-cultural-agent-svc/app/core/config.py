"""
Application configuration loaded from environment variables.

All settings use the TCIA_ prefix. For example:
    TCIA_ANTHROPIC_API_KEY=sk-xxx
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Trend & Cultural Insights Agent service configuration."""

    model_config = SettingsConfigDict(
        env_prefix="TCIA_",
        case_sensitive=False,
    )

    # Redis connection (DB 14)
    REDIS_URL: str = "redis://localhost:6379/14"

    # Kafka connection
    KAFKA_BOOTSTRAP_SERVERS: str = ""

    # CORS origins (comma-separated)
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8024

    # Logging
    LOG_LEVEL: str = "INFO"

    # LLM — Claude Sonnet 4
    ANTHROPIC_API_KEY: str = ""
    LLM_MODEL: str = "claude-sonnet-4-5-20250929"
    LLM_TEMPERATURE: float = 0.3
    LLM_MAX_TOKENS: int = 8192

    # Data sources
    TAVILY_API_KEY: str = ""
    TAVILY_MCP_SERVER_URL: str = ""

    # GCS (trend report persistence)
    GCS_PROJECT_ID: str = ""
    GCS_BUCKET_NAME: str = ""
    GCS_CREDENTIALS_JSON: str = ""
    GCS_CREDENTIALS_PATH: str = ""

    # RAG service
    RAG_SERVICE_URL: str = ""

    # Odoo integration (feature-flagged)
    ODOO_ENABLED: bool = False
    ODOO_URL: str = ""
    ODOO_DB: str = ""
    ODOO_USERNAME: str = ""
    ODOO_PASSWORD: str = ""

    # Django Core API
    CORE_API_URL: str = "http://localhost:8001"
    CORE_API_TOKEN: str = "dev-service-token"

    # Auth
    SERVICE_TOKEN: str = "dev-service-token"

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 10

    # Cache TTLs (seconds)
    RESULT_CACHE_TTL: int = 7200  # 2 hours (shorter for trend freshness)
    IDEMPOTENCY_TTL: int = 86400  # 24 hours
    ODOO_CRM_CACHE_TTL: int = 3600  # 1 hour

    # Trend-specific settings
    TOKEN_BUDGET_PER_SESSION: int = 60000  # PG-07
    MAX_TRENDS_PER_SESSION: int = 25  # PG-08
    ALERT_THRESHOLD: int = 75
    MAX_ALERTS_PER_DAY: int = 5  # PG-09
    MAX_CONCURRENT_RESEARCH: int = 8  # PG-04
    TREND_HISTORY_RETENTION_DAYS: int = 90

    # Guardrail settings
    INPUT_MAX_TOKENS: int = 4096  # IG-06
    OUTPUT_MAX_CHARS: int = 100000  # OG-06
    GROUNDING_THRESHOLD: float = 0.8  # OG-01
    CONFIDENCE_THRESHOLD: float = 0.7  # OG-03

    # Circuit breaker thresholds
    CB_FAILURE_THRESHOLD: int = 5
    CB_RECOVERY_TIMEOUT: int = 30
    CB_LLM_FAILURE_THRESHOLD: int = 3
    CB_LLM_RECOVERY_TIMEOUT: int = 60
    CB_ODOO_FAILURE_THRESHOLD: int = 3
    CB_ODOO_RECOVERY_TIMEOUT: int = 60

    # Kafka consumers
    KAFKA_CONSUMERS_ENABLED: bool = False


settings = Settings()
