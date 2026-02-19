"""Tests for the AgentState TypedDict schema."""

from app.state.schema import AgentState


class TestAgentState:
    """Test AgentState construction and field types."""

    def test_create_minimal_state(self):
        state: AgentState = {
            "job_id": "test-123",
            "input_prompt": "Analyze brand",
            "progress": {},
        }
        assert state["job_id"] == "test-123"
        assert state["input_prompt"] == "Analyze brand"

    def test_create_full_state(self):
        state: AgentState = {
            "job_id": "test-456",
            "tenant_id": "tenant-1",
            "input_prompt": "Full analysis",
            "input_context": {"company_id": 42},
            "tenant_context": {
                "tenant_id": "tenant-1",
                "gcs_raw_bucket": "raw/",
                "gcs_processed_bucket": "curated/",
                "rag_data_store_id": "ds-1",
            },
            "global_config": {"model": "gemini-2.0-flash"},
            "callback_url": "http://localhost:8001/callback/",
            "available_manifests": [
                {"pipeline_id": "brand-analysis", "name": "BA", "description": ""}
            ],
            "resolved_manifest_id": None,
            "node_outputs": {},
            "progress": {"node1": {"status": "pending"}},
            "result_data": None,
            "error": None,
            "cancelled": False,
        }
        assert state["tenant_id"] == "tenant-1"
        assert state["cancelled"] is False
        assert len(state["progress"]) == 1

    def test_progress_matches_agent_progress_type(self):
        """Progress dict should match AgentProgress TS type shape."""
        progress = {
            "intent_router": {
                "status": "done",
                "output": {"resolved_manifest_id": "brand-analysis"},
                "started_at": "2026-02-19T10:00:00Z",
                "completed_at": "2026-02-19T10:00:01Z",
            },
            "web_research": {
                "status": "running",
                "started_at": "2026-02-19T10:00:02Z",
            },
            "manager": {
                "status": "pending",
            },
        }
        state: AgentState = {
            "job_id": "test",
            "input_prompt": "",
            "progress": progress,
        }
        assert state["progress"]["intent_router"]["status"] == "done"
        assert state["progress"]["web_research"]["status"] == "running"
        assert state["progress"]["manager"]["status"] == "pending"
