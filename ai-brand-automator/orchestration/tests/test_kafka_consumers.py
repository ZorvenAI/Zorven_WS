"""
Tests for the Kafka consumers (orchestration/kafka_consumers.py).

Covers ResultConsumer delegation to handle_pipeline_result,
TraceConsumer Redis updates, status mapping, and missing-field handling.
"""

from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache

from orchestration.kafka_consumers import TraceConsumer, _calc_percent


@pytest.mark.django_db
class TestResultConsumer:
    """Tests for ResultConsumer._handle()."""

    def test_delegates_to_handler(self, running_job):
        """_handle calls handle_pipeline_result with correct args."""
        from orchestration.kafka_consumers import ResultConsumer

        mock_handler = MagicMock()
        msg = {
            "job_id": str(running_job.job_id),
            "status": "completed",
            "result_data": {"score": 95},
        }
        ResultConsumer._handle(msg, mock_handler)

        mock_handler.assert_called_once_with(
            str(running_job.job_id),
            status="completed",
            progress=None,
            result_data={"score": 95},
            error_message=None,
            resolved_manifest_id=None,
        )

    def test_missing_job_id_skipped(self):
        """Messages without job_id are logged and skipped."""
        from orchestration.kafka_consumers import ResultConsumer

        mock_handler = MagicMock()
        ResultConsumer._handle({"status": "completed"}, mock_handler)
        mock_handler.assert_not_called()

    def test_passes_all_fields(self, running_job):
        """All optional fields forwarded when present."""
        from orchestration.kafka_consumers import ResultConsumer

        mock_handler = MagicMock()
        msg = {
            "job_id": str(running_job.job_id),
            "status": "failed",
            "progress": {"node1": {"status": "failed"}},
            "result_data": None,
            "error_message": "Timeout",
            "resolved_manifest_id": "brand-v2",
        }
        ResultConsumer._handle(msg, mock_handler)

        mock_handler.assert_called_once_with(
            str(running_job.job_id),
            status="failed",
            progress={"node1": {"status": "failed"}},
            result_data=None,
            error_message="Timeout",
            resolved_manifest_id="brand-v2",
        )


class TestTraceConsumer:
    """Tests for TraceConsumer._handle()."""

    def test_updates_redis_with_trace(self, running_job):
        """Trace message populates Redis with current_node and last_thought."""
        cache_key = f"job:status:{running_job.job_id}"
        cache.delete(cache_key)

        msg = {
            "job_id": str(running_job.job_id),
            "node_id": "web_research",
            "status": "started",
            "last_thought": "Searching SEC filings for NVIDIA...",
            "progress_percent": 33,
        }
        TraceConsumer._handle(msg)

        cached = cache.get(cache_key)
        assert cached is not None
        assert cached["current_node"] == "web_research"
        assert cached["last_thought"] == "Searching SEC filings for NVIDIA..."
        assert cached["progress_percent"] == 33
        assert cached["progress"]["web_research"]["status"] == "running"

    def test_maps_started_to_running(self, running_job):
        """Orchestrator 'started' status mapped to 'running'."""
        cache_key = f"job:status:{running_job.job_id}"
        cache.delete(cache_key)

        TraceConsumer._handle(
            {
                "job_id": str(running_job.job_id),
                "node_id": "valuation",
                "status": "started",
            }
        )

        cached = cache.get(cache_key)
        assert cached["progress"]["valuation"]["status"] == "running"

    def test_maps_completed_to_done(self, running_job):
        """Orchestrator 'completed' status mapped to 'done'."""
        cache_key = f"job:status:{running_job.job_id}"
        cache.delete(cache_key)

        TraceConsumer._handle(
            {
                "job_id": str(running_job.job_id),
                "node_id": "valuation",
                "status": "completed",
            }
        )

        cached = cache.get(cache_key)
        assert cached["progress"]["valuation"]["status"] == "done"

    def test_missing_job_id_skipped(self):
        """Messages without job_id are ignored."""
        # Should not raise
        TraceConsumer._handle({"node_id": "test", "status": "started"})

    def test_preserves_existing_progress(self, running_job):
        """New trace events merge with existing progress in cache."""
        cache_key = f"job:status:{running_job.job_id}"
        cache.set(
            cache_key,
            {
                "status": "running",
                "progress": {"node_a": {"status": "done", "output": None}},
            },
            timeout=3600,
        )

        TraceConsumer._handle(
            {
                "job_id": str(running_job.job_id),
                "node_id": "node_b",
                "status": "started",
            }
        )

        cached = cache.get(cache_key)
        assert "node_a" in cached["progress"]
        assert "node_b" in cached["progress"]
        assert cached["progress"]["node_a"]["status"] == "done"
        assert cached["progress"]["node_b"]["status"] == "running"


class TestCalcPercent:
    """Tests for _calc_percent helper."""

    def test_empty_progress(self):
        assert _calc_percent({}) == 0

    def test_all_done(self):
        progress = {
            "a": {"status": "done"},
            "b": {"status": "done"},
        }
        assert _calc_percent(progress) == 100

    def test_half_done(self):
        progress = {
            "a": {"status": "done"},
            "b": {"status": "running"},
        }
        assert _calc_percent(progress) == 50

    def test_failed_counts_as_done(self):
        progress = {
            "a": {"status": "failed"},
            "b": {"status": "running"},
        }
        assert _calc_percent(progress) == 50
