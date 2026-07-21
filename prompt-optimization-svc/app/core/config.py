"""Prompt Optimization Service configuration via environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Service configuration loaded from POI_* environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="POI_",
        case_sensitive=False,
    )

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8110

    # MLflow Tracking Server
    MLFLOW_TRACKING_URI: str = "http://mlflow-server:5000"

    # PostgreSQL (shared with MLflow backend store)
    DATABASE_URL: str = "postgresql://mlflow:mlflow@mlflow-db:5432/mlflow"

    # Redis (DB 26 — general service cache/rate-limiting)
    REDIS_URL: str = "redis://localhost:6379/26"

    # Redis (DB 2 — prompt cache, optimization locks, progress tracking)
    PROMPT_CACHE_REDIS_URL: str = "redis://localhost:6379/2"

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = ""

    # Anthropic
    ANTHROPIC_API_KEY: str = ""

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/26"

    # Mining
    MINING_QUALITY_THRESHOLD: float = 0.8
    MINING_LOOKBACK_DAYS: int = 7

    # Re-optimization trigger
    REOPT_QUALITY_THRESHOLD: float = 0.7
    REOPT_DEBOUNCE_HOURS: int = 24

    # Canary deployment
    CANARY_REGRESSION_THRESHOLD: float = 0.05
    CANARY_METRICS_TTL_DAYS: int = 30
    CANARY_TRAFFIC_PCT: float = 0.10
    CANARY_DURATION_HOURS: int = 24

    # Health check (§14.1)
    HEALTH_CHECK_REGRESSION_THRESHOLD: float = 0.10

    # Validation (OPT-03/OPT-04)
    VALIDATION_HOLDOUT_PCT: float = 0.2
    VALIDATION_IMPROVEMENT_THRESHOLD: float = 0.05
    VALIDATION_REGRESSION_THRESHOLD: float = 0.03

    # Cost cap (OPT-02)
    OPTIMIZATION_COST_CAP_USD: float = 25.0

    # Cost estimation per GEPA candidate evaluation
    COST_PER_CANDIDATE_USD: float = 0.50

    # Length sanity (OPT-06)
    LENGTH_MULTIPLIER_LIMIT: float = 3.0

    # Circuit breaker (§17.2)
    CIRCUIT_BREAKER_FAILURE_THRESHOLD_SECONDS: int = 300
    CIRCUIT_BREAKER_HALF_OPEN_INTERVAL_SECONDS: int = 60

    # Auto-rollback (§17.2)
    AUTO_ROLLBACK_REGRESSION_THRESHOLD: float = 0.15
    AUTO_ROLLBACK_WINDOW_HOURS: int = 48

    # Redis TTLs (seconds)
    PROMPT_CACHE_TTL: int = 300
    OPTIMIZATION_LOCK_TTL: int = 7200
    OPTIMIZATION_PROGRESS_TTL: int = 86400

    # GEPA optimization
    GEPA_MODEL_NAME: str = "claude-sonnet-4-6"
    GEPA_MAX_TOKENS: int = 4096
    GEPA_REFLECTION_MODEL: str = "anthropic:/claude-sonnet-4-6"
    DEFAULT_OPTIMIZATION_BUDGET: int = 200

    # Optimization lock deferral retry delay (seconds)
    DEFERRED_RETRY_SECONDS: int = 3600

    # Critical agents requiring human approval before promotion
    CRITICAL_AGENTS: str = "adpub,coa"

    # Logging
    LOG_LEVEL: str = "INFO"

    # Service auth
    SERVICE_TOKEN: str = ""
    JWT_SECRET: str = ""


settings = Settings()
