"""FastAPI application, lifespan and dependency wiring.

Configuration is resolved at import time. A missing required variable raises a
Pydantic validation error here — before the server binds a port — so a
misconfigured deploy fails loudly at rollout rather than quietly at the first
meeting (A-05 AC-2).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.api.routes import router
from app.api.ws import router as ws_router
from app.cache.redis_manager import RedisManager
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.telemetry import TraceContextMiddleware, configure_telemetry
from app.events.emitter import EventEmitter
from app.messaging.consumer import CommandConsumer
from app.logic.prep_executor import PrepExecutor
from app.messaging.producer import KafkaProducer
from app.providers.llm import LLMProvider
from app.circuit_breaker.breaker import BreakerRegistry
from app.providers.stt import GoogleSTTAdapter
from app.providers.tavily import TavilyProvider
from app.services.backend_client import BackendClient
from app.messaging.provision import provision, verify

settings = get_settings()
configure_logging(settings.LOG_LEVEL)
configure_telemetry(settings.OTEL_EXPORTER_ENDPOINT)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open connections on startup, close them on shutdown.

    Startup does not abort when a dependency is down. The health probe is the
    place where that is reported — a service that refuses to start cannot tell
    anyone *why* it is unhealthy, and Cloud Run would restart-loop it.
    """
    app.state.settings = settings
    app.state.redis = RedisManager(settings)
    app.state.kafka = KafkaProducer(settings)

    await app.state.redis.connect()
    try:
        await app.state.kafka.start()
    except Exception as exc:  # noqa: BLE001 — reported via /health
        logger.warning("kafka_start_failed", error=str(exc))

    # AC-1: provision the fleet topics and prove they are reachable. This runs
    # BEFORE the consumer subscribes and before the emitter can publish:
    # either would trigger Kafka's auto-create first, and an auto-created
    # topic takes the broker's default retention rather than the §13.1 value.
    # Skipped entirely where no broker is configured, which is production.
    if settings.kafka_enabled:
        try:
            report = await provision(settings.KAFKA_BOOTSTRAP_SERVERS)
            reachable, missing = await verify(settings.KAFKA_BOOTSTRAP_SERVERS)
            logger.info(
                "kafka_topics_ready",
                created=report.created,
                existing=report.existing,
                reconciled=report.reconciled,
                reachable=reachable,
                missing=missing,
            )
        except Exception as exc:  # noqa: BLE001 — reported via /health
            logger.warning("kafka_topic_provisioning_failed", error=str(exc))

    # C-02. Built once: loading the registry parses YAML and imports sixteen
    # modules, which is startup work rather than per-request work. The
    # providers are constructed here so a missing key is visible at boot in
    # the logs rather than on the first operator's turn.
    # One BackendClient, shared. Each one builds its own BreakerRegistry, so
    # two would give the PREP path and the IG-10 gate independent breakers for
    # the same dependency: Django could be failing for one and "healthy" for
    # the other, and the gate would keep paying a full timeout per socket
    # while PREP had already given up. The comment here used to claim they
    # shared one while the code created two.
    app.state.backend = BackendClient(settings.BACKEND_BASE_URL, settings.SERVICE_TOKEN)
    app.state.prep = PrepExecutor(
        app.state.redis,
        tavily=TavilyProvider(settings.TAVILY_API_KEY),
        llm=LLMProvider(settings.GEMINI_KEY),
        backend=app.state.backend,
    )
    if not settings.TAVILY_API_KEY:
        logger.warning(
            "tavily_not_configured",
            detail="research will degrade to operator-provided information only",
        )

    # F-06: shared registry so ws.py can wire the on_state_change callback.
    app.state.breakers = BreakerRegistry()

    # F-05: STT adapter and IG-04 registration.
    app.state.stt = GoogleSTTAdapter(
        project=settings.STT_PROJECT,
        location=settings.STT_LOCATION,
        recognizer=settings.STT_RECOGNIZER,
        credentials_path=settings.STT_CREDENTIALS,
        stream_limit_s=settings.STT_STREAM_LIMIT_S,
        breaker=app.state.breakers.get("stt"),
    )
    if not app.state.stt.configured:
        logger.warning(
            "stt_not_configured",
            detail="live transcription unavailable — set OIA_STT_PROJECT",
        )

    from app.logic.guardrails import Layer
    from app.skills.redact_pii import _ensure_engines, ig04_redact
    from app.logic.green_signal_integrity import og06_green_signal_integrity

    _ensure_engines()
    app.state.prep.registry.chain.register(Layer.INPUT, "IG-04", ig04_redact)
    app.state.prep.registry.chain.register(
        Layer.OUTPUT, "OG-06", og06_green_signal_integrity
    )

    app.state.events = EventEmitter(app.state.kafka)
    await app.state.events.start()

    app.state.commands = CommandConsumer(settings, app.state.kafka)
    try:
        await app.state.commands.start()
    except Exception as exc:  # noqa: BLE001 — reported via /health
        logger.warning("command_consumer_start_failed", error=str(exc))

    # AC-5: session state must not be evictable. Reported rather than fatal —
    # refusing to start would take the service down for a condition an
    # operator has to fix on the shared instance anyway.
    policy = await app.state.redis.eviction_policy()
    app.state.eviction_policy = policy
    if policy is None:
        logger.warning("redis_eviction_policy_unknown", detail="CONFIG GET refused")
    elif policy != "noeviction":
        logger.warning(
            "redis_eviction_policy_unsafe",
            policy=policy,
            detail=(
                "live session state can be evicted mid-meeting; "
                "expected noeviction (A-03 AC-5)"
            ),
        )

    logger.info(
        "service_started",
        service="onboarding-intelligence-agent",
        port=settings.PORT,
        redis_db=settings.REDIS_DB,
        kafka_configured=settings.kafka_enabled,
        eviction_policy=policy,
    )

    yield

    await app.state.commands.stop()
    await app.state.events.stop()
    await app.state.kafka.stop()
    await app.state.redis.close()
    logger.info("service_stopped")


app = FastAPI(
    title="Onboarding Intelligence Agent",
    description=(
        "Turns a recorded onboarding conversation, the documents shown during "
        "it, and the operator's prepared questions into a complete, "
        "provenance-tracked brand profile."
    ),
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(TraceContextMiddleware)
app.include_router(router)
# The LIVE socket. Only the IG-10 gate is behind it until F-04 lands; see
# app/api/ws.py and the A-02 spike note it cites.
app.include_router(ws_router)
