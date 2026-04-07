"""Shared fixtures for ILA tests."""

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.extractor import IntelligenceExtractor


@pytest.fixture
def client():
    # Stub state — bypass real lifespan (Redis/Kafka) for unit tests.
    app.state.redis_manager = AsyncMock()
    app.state.redis_manager.set_dedup = AsyncMock(return_value=True)
    app.state.redis_manager.mark_status = AsyncMock(return_value=None)
    app.state.audit_producer = AsyncMock()
    app.state.audit_producer.send = AsyncMock(return_value=None)
    app.state.event_producer = AsyncMock()
    app.state.django_client = AsyncMock()
    app.state.django_client.ingest_intelligence_report = AsyncMock(
        return_value={"ok": True}
    )
    app.state.extractor = IntelligenceExtractor()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def service_token_header():
    return {"X-Service-Token": settings.SERVICE_TOKEN}
