"""Campaign Optimization Agent service configuration loaded from environment variables.

All settings use the COA_ prefix. For example:
    COA_SERVICE_TOKEN=my-secret-token
    COA_META_ADS_SANDBOX_MODE=true
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Campaign Optimization Agent configuration."""

    model_config = SettingsConfigDict(
        env_prefix="COA_",
        case_sensitive=False,
    )

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8044
    SERVICE_NAME: str = "campaign-optimization-agent"
    LOG_LEVEL: str = "INFO"

    # Redis (DB 24)
    REDIS_URL: str = "redis://localhost:6379/24"

    # Service auth
    SERVICE_TOKEN: str = "dev-service-token"

    # Django backend (campaign discovery + callbacks)
    BACKEND_URL: str = "http://localhost:8001"
    BACKEND_SERVICE_TOKEN: str = "dev-service-token"

    @property
    def backend_url(self) -> str:
        """BACKEND_URL with whitespace stripped."""
        return self.BACKEND_URL.strip().rstrip("/")

    # Meta Marketing API v21.0
    META_API_VERSION: str = "v21.0"
    META_ADS_SANDBOX_MODE: bool = True  # DEFAULT: sandbox (stub data)

    # Anthropic Claude Sonnet 4 (analysis narratives)
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"
    ANTHROPIC_TEMPERATURE: float = 0.3

    # Kafka (optional)
    KAFKA_BOOTSTRAP_SERVERS: str = ""

    # Celery (uses Redis DB 24 as broker)
    CELERY_BROKER_URL: str = "redis://localhost:6379/24"

    # ── Guardrails (11 configurable thresholds) ──

    # PG-01: Maximum daily budget increase percentage
    MAX_DAILY_BUDGET_INCREASE_PCT: int = 20
    # PG-01: Maximum daily budget decrease percentage
    MAX_DAILY_BUDGET_DECREASE_PCT: int = 50
    # IG-03: Minimum spend before any optimization decision
    MIN_SPEND_BEFORE_DECISION_USD: float = 50.0
    # IG-03: Minimum impressions before any optimization decision
    MIN_IMPRESSIONS_BEFORE_DECISION: int = 1000
    # SKL-COA-04: CTR decline threshold for fatigue detection
    FATIGUE_CTR_DECLINE_THRESHOLD_PCT: int = 20
    # PG-05: CPA multiplier above which ad set is killed
    CPA_KILL_MULTIPLIER: float = 2.0
    # SKL-COA-05: ROAS threshold above which ad set is scaled
    ROAS_SCALE_THRESHOLD: float = 1.5
    # IG-05: Hours between optimization actions on the same entity
    OPTIMIZATION_COOLDOWN_HOURS: int = 24
    # IG-06: Maximum autonomous actions per tenant per day
    MAX_AUTO_ACTIONS_PER_DAY: int = 10
    # PG-02: Budget changes above this amount require approval
    REQUIRE_APPROVAL_ABOVE_USD: float = 500.0
    # PG-03: Campaign-level changes always require manual approval
    CAMPAIGN_LEVEL_ALWAYS_MANUAL: bool = True

    # Creative Generation Agent (creative refresh requests)
    CGA_SERVICE_URL: str = "http://localhost:8042"

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"


settings = Settings()
