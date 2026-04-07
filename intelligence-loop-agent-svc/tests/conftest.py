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
    mock_django = AsyncMock()
    mock_django.ingest_intelligence_report = AsyncMock(return_value={"ok": True})
    mock_django.ingest_rag_learning = AsyncMock(return_value={"ok": True})
    mock_django.get_campaign_context = AsyncMock(return_value=None)
    mock_django.create_wf2_request = AsyncMock(return_value={"ok": True})
    mock_django.auto_trigger_rerun = AsyncMock(return_value={"ok": True})
    app.state.django_client = mock_django

    mock_anthropic = AsyncMock()
    mock_anthropic.enabled = False
    mock_anthropic.complete_json = AsyncMock(return_value="")

    # Inject mocks so /v1/execute never performs real HTTP / Anthropic calls.
    app.state.extractor = IntelligenceExtractor(
        django_client=mock_django,
        anthropic_client=mock_anthropic,
    )
    with TestClient(app) as c:
        yield c


@pytest.fixture
def service_token_header():
    return {"X-Service-Token": settings.SERVICE_TOKEN}
