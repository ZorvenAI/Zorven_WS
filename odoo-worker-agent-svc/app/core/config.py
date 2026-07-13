"""
Application configuration loaded from environment variables.

All settings use the ODOO_WORKER_ prefix. For example:
    ODOO_WORKER_GOOGLE_API_KEY=AIza...
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Odoo worker agent service configuration."""

    model_config = SettingsConfigDict(
        env_prefix="ODOO_WORKER_",
        case_sensitive=False,
    )

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8100

    # MCP Server connection
    MCP_SERVER_URL: str = "http://odoo-mcp-server:8095"
    MCP_TIMEOUT: float = 60.0

    # Gemini AI (empty = stub mode)
    GOOGLE_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"

    # Redis (DB 10 — next available after DB 9 odoo-mcp-server)
    REDIS_URL: str = "redis://localhost:6379/10"

    # Kafka (empty = disabled)
    KAFKA_BOOTSTRAP_SERVERS: str = ""

    # CORS origins (comma-separated)
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"

    # Service authentication
    SERVICE_TOKEN: str = "dev-service-token"

    # PAOR loop limits
    MAX_REASONING_STEPS: int = 10
    MAX_TOOL_CALLS_PER_STEP: int = 5

    # Logging
    LOG_LEVEL: str = "INFO"

    # RBAC pre-flight validation
    RBAC_PRE_FLIGHT: bool = True

    # RAG context enrichment (empty URL = disabled)
    RAG_ENABLED: bool = False
    RAG_SERVICE_URL: str = "http://localhost:8070"

    # Personas directory
    PERSONAS_DIR: str = "config/personas"

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 10

    # Prompt optimization (prompt-optimization-svc integration)
    PROMPT_CACHE_REDIS_URL: str = "redis://localhost:6379/2"
    MLFLOW_TRACKING_URI: str = "http://prompt-optimization-svc:8110"
    PROMPT_CACHE_TTL: int = 300
    PROMPT_FALLBACK_ONLY: bool = False


settings = Settings()
