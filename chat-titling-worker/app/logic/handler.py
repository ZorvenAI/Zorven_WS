"""
Titling handler — orchestrates dedup, generation, and callback.

This is the core business logic that the Kafka consumer invokes
for each titling event.
"""

import logging

from app.cache.redis_manager import RedisManager
from app.logic.title_generator import TitleGenerator
from app.messaging.schemas import TitlingEvent
from app.services.api_client import CoreApiClient

logger = logging.getLogger(__name__)


class TitlingHandler:
    """Processes titling events: dedup → generate → callback."""

    def __init__(
        self,
        redis: RedisManager,
        generator: TitleGenerator,
        api_client: CoreApiClient,
    ) -> None:
        self.redis = redis
        self.generator = generator
        self.api_client = api_client

    async def handle(self, event: TitlingEvent) -> None:
        """Process a single titling event."""
        session_id = event.session_id

        # 1. Check Redis dedup
        if await self.redis.is_processed(session_id):
            logger.info("Session %s already processed — skipping", session_id)
            return

        # 2. Generate title
        title = await self.generator.generate(
            event.first_message, event.first_response
        )
        logger.info(
            "Generated title for session %s: '%s'", session_id, title
        )

        # 3. PATCH to Django
        success = await self.api_client.update_title(
            session_id, title, event.tenant_id
        )
        if not success:
            logger.warning(
                "Failed to update title for session %s — will retry on next event",
                session_id,
            )
            return

        # 4. Mark as processed (only after successful PATCH)
        await self.redis.mark_processed(session_id)
        logger.info("Session %s titled successfully: '%s'", session_id, title)
