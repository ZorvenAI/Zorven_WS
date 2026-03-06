"""Service configuration — all settings from ODOO_MCP_ prefixed env vars."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ODOO_MCP_",
        case_sensitive=False,
    )

    # ── Odoo Connection ──
    ODOO_URL: str = "http://localhost:8069"
    ODOO_MASTER_PASSWORD: str = ""

    # ── MCP Transport ──
    MCP_TRANSPORT: str = "streamable-http"  # streamable-http | sse

    # ── Server ──
    HOST: str = "0.0.0.0"
    PORT: int = 8095

    # ── Redis (DB 9) ──
    REDIS_URL: str = "redis://localhost:6379/9"

    # ── CORS ──
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"

    # ── Logging ──
    LOG_LEVEL: str = "INFO"

    # ── Multi-Tenancy ──
    TENANT_MODEL: str = "shared_instance"  # dedicated_db | shared_instance | shared_db
    TENANT_CACHE_TTL: int = 3600  # 1 hour

    # ── RBAC ──
    RBAC_ENFORCEMENT: str = "enforcing"  # enforcing | permissive | disabled
    RBAC_ROLES_DIR: str = "config/roles"
    RBAC_CACHE_TTL: int = 300  # 5 minutes

    # ── RAG Integration ──
    RAG_SERVICE_URL: str = "http://localhost:8070"
    RAG_ENABLED: bool = False
    RAG_CONTEXT_MAX_TOKENS: int = 2000

    # ── Neon DB (read-only for tenant → data store resolution) ──
    DATABASE_URL: str = ""

    # ── Vertex AI Discovery Engine (direct RAG) ──
    VERTEX_AI_PROJECT_ID: str = "brandsol-project"
    VERTEX_AI_LOCATION: str = "global"
    VERTEX_AI_DATA_STORE_ID: str = "prevision-rag-dev"
    VERTEX_AI_MOCK_MODE: bool = False

    # ── Connection Pool ──
    POOL_SIZE_DEFAULT: int = 5
    POOL_SIZE_MAX: int = 20

    # ── Rate Limiting ──
    RATE_LIMIT_PER_MINUTE: int = 60

    # ── Cache TTL (seconds) ──
    SCHEMA_CACHE_TTL: int = 3600  # 1 hour
    SESSION_CACHE_TTL: int = 1800  # 30 minutes
    RESULT_CACHE_TTL: int = 14400  # 4 hours

    # ── Kafka (optional) ──
    KAFKA_BOOTSTRAP_SERVERS: str = ""

    # ── Service Auth ──
    SERVICE_TOKEN: str = "dev-service-token"

    # ── Retry ──
    RPC_RETRY_ATTEMPTS: int = 3
    RPC_RETRY_BACKOFF: float = 1.0
    RPC_TIMEOUT: float = 30.0


settings = Settings()
