"""
Tests for the Kafka trigger producer (orchestration/kafka_producer.py).

Verifies payload construction, job status transitions, Kafka error handling,
and tenant-based partitioning key.
"""

from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from orchestration.kafka_producer import KafkaTriggerProducer
from orchestration.models import AnalysisJob


@pytest.mark.django_db
class TestKafkaTriggerProducer:
    """Tests for KafkaTriggerProducer.dispatch()."""

    @patch("kafka_service.consumer.KafkaProducerService")
    def test_dispatch_success_updates_job(self, MockProducer, analysis_job):
        """Successful dispatch sets job to RUNNING with started_at."""
        mock_producer = MockProducer.return_value

        producer = KafkaTriggerProducer()
        result = producer.dispatch(analysis_job)

        assert result is True
        analysis_job.refresh_from_db()
        assert analysis_job.status == AnalysisJob.Status.RUNNING
        assert analysis_job.started_at is not None
        mock_producer.send.assert_called_once()
        mock_producer.flush.assert_called_once()

    @patch("kafka_service.consumer.KafkaProducerService")
    def test_dispatch_sends_to_correct_topic(self, MockProducer, analysis_job):
        """Message published to pipeline-trigger-topic."""
        mock_producer = MockProducer.return_value

        producer = KafkaTriggerProducer()
        producer.dispatch(analysis_job)

        call_args = mock_producer.send.call_args
        assert call_args[0][0] == "pipeline-trigger-topic"

    @patch("kafka_service.consumer.KafkaProducerService")
    def test_dispatch_payload_has_required_fields(self, MockProducer, analysis_job):
        """Payload contains job_id, input_prompt, callback_url, etc."""
        mock_producer = MockProducer.return_value

        producer = KafkaTriggerProducer()
        producer.dispatch(analysis_job)

        payload = mock_producer.send.call_args[0][1]
        assert payload["job_id"] == str(analysis_job.job_id)
        assert payload["input_prompt"] == analysis_job.input_prompt
        assert "callback_url" in payload

    @patch("kafka_service.consumer.KafkaProducerService")
    def test_dispatch_uses_tenant_id_as_key(self, MockProducer, analysis_job):
        """Message key is set to tenant_id for Kafka partitioning."""
        mock_producer = MockProducer.return_value

        producer = KafkaTriggerProducer()
        producer.dispatch(analysis_job)

        call_kwargs = mock_producer.send.call_args[1]
        assert call_kwargs["key"] == str(analysis_job.tenant.id)

    @patch("kafka_service.consumer.KafkaProducerService")
    def test_dispatch_failure_returns_false(self, MockProducer, analysis_job):
        """Kafka error returns False and does not update job status."""
        mock_producer = MockProducer.return_value
        mock_producer.send.side_effect = Exception("Kafka down")

        producer = KafkaTriggerProducer()
        result = producer.dispatch(analysis_job)

        assert result is False
        analysis_job.refresh_from_db()
        assert analysis_job.status == AnalysisJob.Status.QUEUED

    @patch("kafka_service.consumer.KafkaProducerService")
    def test_dispatch_no_tenant_key_is_none(self, MockProducer, auto_detect_job):
        """Job without tenant uses None as message key."""
        mock_producer = MockProducer.return_value
        # auto_detect_job has tenant set; create one without
        auto_detect_job.tenant = None
        auto_detect_job.save()

        producer = KafkaTriggerProducer()
        producer.dispatch(auto_detect_job)

        call_kwargs = mock_producer.send.call_args[1]
        assert call_kwargs["key"] is None
