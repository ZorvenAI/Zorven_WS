"""Tests for TitlingHandler."""

from unittest.mock import AsyncMock

from app.logic.handler import TitlingHandler
from app.messaging.schemas import TitlingEvent


class TestTitlingHandler:
    """Tests for the TitlingHandler class."""

    async def test_processes_new_event(
        self, sample_event, mock_redis, mock_generator, mock_api_client
    ):
        """Generates title and patches API for new events."""
        handler = TitlingHandler(
            redis=mock_redis,
            generator=mock_generator,
            api_client=mock_api_client,
        )

        await handler.handle(sample_event)

        mock_redis.is_processed.assert_called_once_with(sample_event.session_id)
        mock_generator.generate.assert_called_once_with(
            sample_event.first_message, sample_event.first_response
        )
        mock_api_client.update_title.assert_called_once_with(
            sample_event.session_id,
            "NVIDIA Brand Positioning Analysis",
            sample_event.tenant_id,
        )
        mock_redis.mark_processed.assert_called_once_with(sample_event.session_id)

    async def test_skips_already_processed(
        self, sample_event, mock_redis, mock_generator, mock_api_client
    ):
        """Redis dedup prevents re-processing."""
        mock_redis.is_processed = AsyncMock(return_value=True)

        handler = TitlingHandler(
            redis=mock_redis,
            generator=mock_generator,
            api_client=mock_api_client,
        )

        await handler.handle(sample_event)

        mock_redis.is_processed.assert_called_once_with(sample_event.session_id)
        mock_generator.generate.assert_not_called()
        mock_api_client.update_title.assert_not_called()
        mock_redis.mark_processed.assert_not_called()

    async def test_redis_failure_still_processes(
        self, sample_event, mock_redis, mock_generator, mock_api_client
    ):
        """Redis error in is_processed doesn't block titling (fail open)."""
        mock_redis.is_processed = AsyncMock(return_value=False)  # fail open

        handler = TitlingHandler(
            redis=mock_redis,
            generator=mock_generator,
            api_client=mock_api_client,
        )

        await handler.handle(sample_event)

        mock_generator.generate.assert_called_once()
        mock_api_client.update_title.assert_called_once()

    async def test_api_failure_does_not_mark_processed(
        self, sample_event, mock_redis, mock_generator, mock_api_client
    ):
        """PATCH failure prevents marking as processed (will retry)."""
        mock_api_client.update_title = AsyncMock(return_value=False)

        handler = TitlingHandler(
            redis=mock_redis,
            generator=mock_generator,
            api_client=mock_api_client,
        )

        await handler.handle(sample_event)

        mock_generator.generate.assert_called_once()
        mock_api_client.update_title.assert_called_once()
        mock_redis.mark_processed.assert_not_called()
