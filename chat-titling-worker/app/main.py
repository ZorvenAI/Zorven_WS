"""
Chat Titling Worker — FastAPI application entry point.

Lightweight event-driven microservice that listens for new chat
sessions via Kafka, generates concise titles using Gemini Flash,
and PATCHes them back to the Django backend.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes
from app.api.routes import router
from app.cache.redis_manager import RedisManager
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.logic.handler import TitlingHandler
from app.logic.title_generator import TitleGenerator
from app.messaging.kafka_consumer import TitlingConsumer
from app.services.api_client import CoreApiClient

logger = logging.getLogger(__name__)

_SKILLS_DIR = Path(__file__).parent.parent / "skills"


def _load_skill_context() -> str:
    """Load skill Markdown from the skills directory (fail-open).

    Reads all .md files, strips YAML frontmatter, and concatenates
    the Markdown body.  Returns empty string if no skills found.
    """
    if not _SKILLS_DIR.is_dir():
        logger.info("No skills directory found at %s", _SKILLS_DIR)
        return ""

    parts: list[str] = []
    for path in sorted(_SKILLS_DIR.glob("*.md")):
        try:
            content = path.read_text(encoding="utf-8")
            if content.startswith("---"):
                # Strip YAML frontmatter
                split = content.split("---", 2)
                if len(split) >= 3:
                    body = split[2].strip()
                    if body:
                        parts.append(body)
                        logger.info("Loaded skill: %s", path.name)
            else:
                parts.append(content.strip())
        except Exception:
            logger.warning("Failed to read skill file: %s", path, exc_info=True)

    if parts:
        logger.info("Loaded %d skill(s) for title generation", len(parts))
    return "\n\n".join(parts)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    setup_logging()
    logger.info(
        "Chat Titling Worker starting on %s:%d",
        settings.HOST,
        settings.PORT,
    )

    # Initialize Redis manager
    redis_manager = RedisManager(settings.REDIS_URL)

    # Load skill context from skills directory (fail-open)
    skill_context = _load_skill_context()

    # Initialize title generator
    title_generator = TitleGenerator(
        api_key=settings.GOOGLE_API_KEY,
        model_name=settings.GEMINI_MODEL,
        skill_context=skill_context,
    )

    if settings.GOOGLE_API_KEY:
        logger.info("Google API key configured — live Gemini mode")
    else:
        logger.warning("No Google API key — running in stub mode")

    # Initialize API client
    api_client = CoreApiClient(
        base_url=settings.CORE_API_URL,
        worker_token=settings.WORKER_TOKEN,
    )

    # Initialize Kafka consumer
    consumer = TitlingConsumer(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id=settings.KAFKA_GROUP_ID,
        topic=settings.KAFKA_TOPIC,
    )
    await consumer.start()
    routes.consumer = consumer

    # Wire handler and start consume loop
    handler = TitlingHandler(
        redis=redis_manager,
        generator=title_generator,
        api_client=api_client,
    )
    consume_task = asyncio.create_task(consumer.consume(handler.handle))

    yield

    # Shutdown
    await consumer.stop()
    consume_task.cancel()
    try:
        await consume_task
    except asyncio.CancelledError:
        pass
    await api_client.close()
    await redis_manager.close()
    routes.consumer = None
    logger.info("Chat Titling Worker shut down")


app = FastAPI(
    title="Chat Titling Worker",
    description="Auto-titling background worker for chat sessions",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
