"""
Application configuration loaded from environment variables.

All settings use the APA_ prefix. For example:
    APA_ANTHROPIC_API_KEY=sk-xxx
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Audience Persona Agent service configuration."""

    model_config = SettingsConfigDict(
        env_prefix="APA_",
        case_sensitive=False,
    )

    # Redis connection (DB 13)
    REDIS_URL: str = "redis://localhost:6379/13"

    # Kafka connection
    KAFKA_BOOTSTRAP_SERVERS: str = ""

    # CORS origins (comma-separated)
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8023

    # Logging
    LOG_LEVEL: str = "INFO"

    # LLM — Claude Sonnet 4
    ANTHROPIC_API_KEY: str = ""
    LLM_MODEL: str = "claude-sonnet-4-20250514"
    LLM_TEMPERATURE: float = 0.3
    LLM_MAX_TOKENS: int = 16384

    # Data sources
    TAVILY_API_KEY: str = ""

    # Odoo integration (feature-flagged)
    ODOO_ENABLED: bool = False
    ODOO_URL: str = ""
    ODOO_DB: str = ""
    ODOO_USERNAME: str = ""
    ODOO_PASSWORD: str = ""

    # RAG service
    RAG_SERVICE_URL: str = ""

    # GCS (for report persistence)
    GCS_CREDENTIALS_JSON: str = ""
    GCS_BUCKET: str = ""

    # Auth
    SERVICE_TOKEN: str = "dev-service-token"

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 10

    # Cache TTLs (seconds)
    RESULT_CACHE_TTL: int = 14400  # 4 hours
    ODOO_SURVEY_CACHE_TTL: int = 3600  # 1 hour
    ODOO_CRM_CACHE_TTL: int = 3600  # 1 hour
    PERSONA_VERSION_TTL: int = 15552000  # 180 days
    IDEMPOTENCY_TTL: int = 86400  # 24 hours

    # Guardrail settings
    INPUT_MAX_TOKENS: int = 16000  # ~4096 tokens
    OUTPUT_MAX_CHARS: int = 120000
    CONFIDENCE_THRESHOLD: float = 0.7
    TOKEN_BUDGET_PER_SESSION: int = 80000
    MAX_PERSONAS: int = 5
    MAX_PERSONAS_LIMIT: int = 8
    MAX_CONCURRENT_WEB_REQUESTS: int = 5

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
