"""J-02 AC-4 — Degraded STT: manual checks yield no extracted values.

Questions marked GREEN manually but having no evidence spans are flagged as
answered-but-not-captured. They contribute to coverage as answered but are
excluded from field extraction.
"""

import json

import pytest

from app.api.schemas import EvidenceManifest
from app.cache.redis_manager import TTL_LIVE
from app.logic.evidence_assembler import EvidenceAssembler

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]

TENANT_ID = "test-tenant-degraded"
SESSION_ID = "test-session-degraded"


@pytest.fixture
async def redis_manager(live_redis):
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


async def test_manual_checks_yield_no_values(redis_manager, settings):
    """AC-4: questions with source=manual, status=GREEN, empty evidence.

    Set up a session in degraded mode (RECORD_ONLY from F-06), mark questions
    manually, assemble evidence, verify those questions appear in
    degraded_question_ids with zero extracted values.
    """
    keys = redis_manager.keys_for(TENANT_ID)
    q_key = keys.questions(SESSION_ID)

    questions = {
        "q-normal": json.dumps(
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
        "q-manual-1": json.dumps(
            {
                "text": "Who are your target customers?",
                "target_field": "target_audience",
                "workflow_target": "WF2",
                "status": "GREEN",
                "evidence": [],
                "score": None,
                "source": "manual",
                "origin": "PREPARED",
                "version": 1,
            }
        ),
        "q-manual-2": json.dumps(
            {
                "text": "What is your brand personality?",
                "target_field": "brand_personality",
                "workflow_target": "WF2",
                "status": "GREEN",
                "evidence": [],
                "score": None,
                "source": "manual",
                "origin": "PREPARED",
                "version": 1,
            }
        ),
        "q-open": json.dumps(
            {
                "text": "What channels do you use?",
                "target_field": "sales_channels",
                "workflow_target": "WF3",
                "status": "OPEN",
                "evidence": [],
                "score": None,
                "source": "prepared",
                "origin": "PREPARED",
                "version": 1,
            }
        ),
    }

    for qid, qdata in questions.items():
        await redis_manager.client.hset(q_key, qid, qdata)
    await redis_manager.client.expire(q_key, TTL_LIVE)

    assembler = EvidenceAssembler(redis=redis_manager, backend=None, settings=settings)
    manifest = EvidenceManifest(
        recordings=["rec-1"], media=[], has_questionnaire=True, has_transcript=True
    )

    evidence = await assembler.assemble(
        tenant_id=TENANT_ID, session_id=SESSION_ID, manifest=manifest
    )

    assert "q-manual-1" in evidence.degraded_question_ids
    assert "q-manual-2" in evidence.degraded_question_ids

    assert "q-normal" not in evidence.degraded_question_ids
    assert "q-open" not in evidence.degraded_question_ids

    from app.logic.coverage import compute_coverage

    question_states = assembler.question_states_for_coverage()
    coverage = compute_coverage(question_states)

    green_count = sum(1 for q in question_states if q.get("status") == "GREEN")
    assert green_count == 3

    assert coverage.wf1.pct == 1.0
    assert coverage.wf2.pct == 1.0
    assert coverage.wf3.pct == 0.0
