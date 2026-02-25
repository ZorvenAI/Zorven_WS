"""Shared test fixtures for chat-titling-worker."""

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, MagicMock

from app.messaging.schemas import TitlingEvent


@pytest.fixture
def sample_event() -> TitlingEvent:
    """A sample titling event for testing."""
    return TitlingEvent(
        session_id="abc-123-def-456",
        session_pk=42,
        tenant_id="tenant-1",
        first_message="Analyze NVIDIA brand positioning in the GPU market",
        first_response="",
    )


@pytest.fixture
def sample_event_dict() -> dict[str, Any]:
    """A sample titling event as a raw dict (Kafka message value)."""
    return {
        "session_id": "abc-123-def-456",
        "session_pk": 42,
        "tenant_id": "tenant-1",
        "first_message": "Analyze NVIDIA brand positioning in the GPU market",
        "first_response": "",
    }


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Mock RedisManager with default behavior."""
    redis = AsyncMock()
    redis.is_processed = AsyncMock(return_value=False)
    redis.mark_processed = AsyncMock()
    redis.close = AsyncMock()
    return redis


@pytest.fixture
def mock_generator() -> AsyncMock:
    """Mock TitleGenerator that returns a fixed title."""
    generator = AsyncMock()
    generator.generate = AsyncMock(return_value="NVIDIA Brand Positioning Analysis")
    return generator


@pytest.fixture
def mock_api_client() -> AsyncMock:
    """Mock CoreApiClient that succeeds."""
    client = AsyncMock()
    client.update_title = AsyncMock(return_value=True)
    client.close = AsyncMock()
    return client
