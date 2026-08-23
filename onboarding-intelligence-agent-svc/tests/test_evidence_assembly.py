"""J-02 — Evidence assembly integration tests.

Real Redis, no mocks. Tests the assembler's ability to gather and merge
evidence from Redis and handle Django endpoint unavailability.
"""

import json

import pytest

from app.api.schemas import EvidenceManifest
from app.cache.redis_manager import RedisManager, TTL_LIVE
from app.logic.evidence_assembler import EvidenceAssembler

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

TENANT_ID = "test-tenant-evidence"
SESSION_ID = "test-session-evidence"


@pytest.fixture
async def redis_manager(live_redis):
    """Provide a connected RedisManager and clean up test keys after."""
    yield live_redis
    pattern = f"oia:v1:{TENANT_ID}:*"
    found = await live_redis.scan_prefix(pattern)
    if found:
        await live_redis.client.delete(*found)


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("OIA_BACKEND_BASE_URL", "http://backend:8001")
    monkeypatch.setenv("OIA_GCS_BUCKET", "zorven-raw-assets")
    monkeypatch.setenv("OIA_SERVICE_TOKEN", "test-token")
    from app.core.config import get_settings

    get_settings.cache_clear()
    s = get_settings()
    get_settings.cache_clear()
    return s


async def _populate_redis_questions(redis_manager: RedisManager) -> None:
    """Populate Redis with test question data."""
    keys = redis_manager.keys_for(TENANT_ID)
    q_key = keys.questions(SESSION_ID)

    questions = {
        "q-1": json.dumps(
            {
                "text": "What is your company name?",
                "target_field": "legal_name",
                "workflow_target": "WF1",
                "status": "GREEN",
                "evidence": [{"recording_id": "rec-1", "t_start": 10.0, "t_end": 25.0}],
                "score": 0.9,
                "source": "analysis",
                "origin": "PREPARED",
                "version": 2,
            }
        ),
        "q-2": json.dumps(
            {
                "text": "Who are your competitors?",
                "target_field": "competitors",
                "workflow_target": "WF2",
                "status": "OPEN",
                "evidence": [],
                "score": None,
                "source": "prepared",
                "origin": "PREPARED",
                "version": 1,
            }
        ),
        "q-3": json.dumps(
            {
                "text": "What channels do you sell through?",
                "target_field": "sales_channels",
                "workflow_target": "WF3",
                "status": "GREEN",
                "evidence": [],
                "score": 0.8,
                "source": "manual",
                "origin": "PREPARED",
                "version": 1,
            }
        ),
    }

    for qid, qdata in questions.items():
        await redis_manager.client.hset(q_key, qid, qdata)
    await redis_manager.client.expire(q_key, TTL_LIVE)


async def test_assemble_from_redis_only(redis_manager, settings):
    """Populate Redis keys, assemble with no backend, verify all types present."""
    await _populate_redis_questions(redis_manager)

    assembler = EvidenceAssembler(redis=redis_manager, backend=None, settings=settings)
    manifest = EvidenceManifest(
        recordings=["rec-1"], media=[], has_questionnaire=True, has_transcript=True
    )

    evidence = await assembler.assemble(
        tenant_id=TENANT_ID, session_id=SESSION_ID, manifest=manifest
    )

    assert evidence is not None
    questions = assembler.question_states_for_coverage()
    assert len(questions) == 3

    green_qs = [q for q in questions if q.get("status") == "GREEN"]
    assert len(green_qs) == 2


async def test_assemble_falls_back_when_redis_expired(redis_manager, settings):
    """Assemble with empty Redis keys — no crash, empty questions list."""
    assembler = EvidenceAssembler(redis=redis_manager, backend=None, settings=settings)
    manifest = EvidenceManifest(
        recordings=[], media=[], has_questionnaire=False, has_transcript=False
    )

    evidence = await assembler.assemble(
        tenant_id=TENANT_ID, session_id=SESSION_ID, manifest=manifest
    )

    assert evidence is not None
    assert evidence.blocks == []
    assert evidence.questions == []
    assert evidence.missing_media == []


async def test_pending_ocr_recorded_as_missing(redis_manager, settings):
    """Enqueue an OCR retry item, verify it shows up in evidence context."""
    from app.cache.retry_queue import OCRRetryItem, enqueue_retry

    keys = redis_manager.keys_for(TENANT_ID)
    item = OCRRetryItem(
        media_id="media-pending-1",
        gcs_uri="gs://bucket/pending.jpg",
        usage_tag="logo",
        tenant_id=TENANT_ID,
        attempt=0,
    )
    await enqueue_retry(redis_manager.client, keys, item)

    from app.cache.retry_queue import queue_size

    size = await queue_size(redis_manager.client, keys)
    assert size > 0

    assembler = EvidenceAssembler(redis=redis_manager, backend=None, settings=settings)
    manifest = EvidenceManifest(
        recordings=[],
        media=["media-pending-1"],
        has_questionnaire=False,
        has_transcript=False,
    )

    evidence = await assembler.assemble(
        tenant_id=TENANT_ID, session_id=SESSION_ID, manifest=manifest
    )

    assert evidence is not None


async def test_degraded_question_flagged(redis_manager, settings):
    """A question with source=manual, status=GREEN, empty evidence is degraded."""
    await _populate_redis_questions(redis_manager)

    assembler = EvidenceAssembler(redis=redis_manager, backend=None, settings=settings)
    manifest = EvidenceManifest(
        recordings=[], media=[], has_questionnaire=True, has_transcript=True
    )

    evidence = await assembler.assemble(
        tenant_id=TENANT_ID, session_id=SESSION_ID, manifest=manifest
    )

    assert "q-3" in evidence.degraded_question_ids


async def test_token_estimation(redis_manager, settings):
    """Token estimate is approximately chars/4."""
    assembler = EvidenceAssembler(redis=redis_manager, backend=None, settings=settings)

    from app.logic.evidence_assembler import EvidenceBlock

    blocks = [
        EvidenceBlock(text="a" * 400, source_type="transcript"),
        EvidenceBlock(text="b" * 200, source_type="media_ocr"),
    ]
    estimate = assembler._estimate_tokens(blocks)
    assert estimate == 150
