"""
Kafka-based dispatch for pipeline jobs.

KafkaTriggerProducer publishes a trigger event to ``pipeline-trigger-topic``
instead of making an HTTP POST to the orchestrator service.  The orchestrator
consumes this topic and starts the pipeline graph.

Uses the existing ``KafkaProducerService`` from ``kafka_service.consumer``.
"""

import logging

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class KafkaTriggerProducer:
    """Publish a pipeline trigger to Kafka.

    Drop-in replacement for ``OrchestratorDispatcher.dispatch()`` when
    ``ORCHESTRATION_KAFKA_ENABLED`` is True.
    """

    def dispatch(self, job):
        """Publish job to ``pipeline-trigger-topic``.

        Returns True on success (job status → RUNNING),
        False on failure (job left in QUEUED for Celery retry).
        """
        from kafka_service.consumer import KafkaProducerService

        from .models import AnalysisJob
        from .services import OrchestratorDispatcher

        # Reuse the existing payload builder
        http_dispatcher = OrchestratorDispatcher()
        payload = http_dispatcher._build_payload(job)

        topic = getattr(
            settings,
            "KAFKA_TOPIC_PIPELINE_TRIGGER",
            "pipeline-trigger-topic",
        )

        # Use tenant_id as message key for Kafka partitioning
        tenant = job.tenant
        key = str(tenant.id) if tenant else None

        try:
            producer = KafkaProducerService()
            producer.send(topic, payload, key=key)
            producer.flush(timeout=5.0)

            job.status = AnalysisJob.Status.RUNNING
            job.started_at = timezone.now()
            job.save(update_fields=["status", "started_at", "updated_at"])

            logger.info(
                "Job %s dispatched via Kafka to %s", job.job_id, topic
            )
            return True

        except Exception as exc:
            logger.error(
                "Kafka dispatch failed for job %s: %s", job.job_id, exc
            )
            return False
