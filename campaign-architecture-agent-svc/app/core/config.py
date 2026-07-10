"""CAA service configuration loaded from environment variables.

All settings use the CAA_ prefix. For example:
    CAA_SERVICE_TOKEN=my-secret-token
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Campaign Architecture Agent configuration."""

    model_config = SettingsConfigDict(
        env_prefix="CAA_",
        case_sensitive=False,
    )

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8041
    SERVICE_NAME: str = "campaign-architecture-agent"
    LOG_LEVEL: str = "INFO"

    # Redis (DB 21)
    REDIS_URL: str = "redis://localhost:6379/21"
    # Prompt optimization
    PROMPT_CACHE_REDIS_URL: str = "redis://localhost:6379/2"
    MLFLOW_TRACKING_URI: str = "http://mlflow-server:5000"
    PROMPT_FALLBACK_ONLY: bool = False

    # Anthropic Claude Sonnet 4
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-5"
    ANTHROPIC_MAX_TOKENS: int = 8192
    ANTHROPIC_TEMPERATURE: float = 0.3

    # Service auth
    SERVICE_TOKEN: str = "dev-service-token"

    # Django backend (WF1 + WF2 + Company context)
    BACKEND_URL: str = "http://localhost:8001"
    BACKEND_SERVICE_TOKEN: str = "dev-service-token"

    # Kafka (optional)
    KAFKA_BOOTSTRAP_SERVERS: str = ""
    KAFKA_CONSUMERS_ENABLED: bool = False

    # GCS (blueprint persistence)
    GCS_PROJECT_ID: str = ""
    GCS_BUCKET_NAME: str = ""
    GCS_CREDENTIALS_PATH: str = ""
    GCS_CREDENTIALS_JSON: str = ""

    # Tavily (web research for benchmarks + competitor ads)
    TAVILY_API_KEY: str = ""
    TAVILY_BENCHMARK_CACHE_TTL: int = 86400  # 24 hours
    TAVILY_COMPETITOR_CACHE_TTL: int = 43200  # 12 hours

    # Odoo CRM (optional — customer data for custom audiences)
    ODOO_MCP_URL: str = ""

    # RAG Intelligence Loop (optional — prior campaign learnings)
    RAG_DATA_STORE_ID: str = ""

    # Budget guardrails
    DEFAULT_DAILY_BUDGET_CAP: float = 10000.0
    MIN_DAILY_BUDGET: float = 10.0  # Meta minimum

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"

    # Caching
    RESULT_CACHE_TTL: int = 14400  # 4 hours
    IDEMPOTENCY_TTL: int = 86400  # 24 hours

    # Guardrails
    CONFIDENCE_THRESHOLD: float = 0.7
    TOKEN_BUDGET_PER_SESSION: int = 100000


settings = Settings()
