"""
Kafka consumers for the orchestration module.

ResultConsumer  — consumes ``pipeline-result-topic``, delegates to
                  ``handle_pipeline_result()`` for DB + Redis update.
TraceConsumer   — consumes ``agent-trace-topic``, updates Redis only
                  (lightweight "AI is thinking…" display).
"""

import json
import logging
import time

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Orchestrator status → frontend-friendly mapping
_STATUS_MAP = {
    "started": "running",
    "completed": "done",
    "failed": "failed",
    "running": "running",
    "done": "done",
}


class ResultConsumer:
    """Consume pipeline results from Kafka.

    Each message is a final (or partial) result from the
    pipeline-orchestrator-svc.  The consumer delegates all DB / Redis
    work to ``handle_pipeline_result()``.
    """

    def __init__(self):
        self.topic = getattr(
            settings,
            "KAFKA_TOPIC_PIPELINE_RESULT",
            "pipeline-result-topic",
        )
        self.group_id = getattr(
            settings,
            "ORCHESTRATION_KAFKA_GROUP_ID",
            "orchestration-result-consumers",
        )

    def consume(self, max_messages=50, timeout=5.0):
        """Consume a batch of result messages.

        Returns the number of messages successfully processed.
        """
        from kafka_service.consumer import KafkaConfig, KafkaConsumerService

        from .result_handler import handle_pipeline_result

        consumer = KafkaConsumerService(
            topics=[self.topic],
            group_id=self.group_id,
        )
        # Register our handler instead of the default ones
        consumer.register_handler(
            self.topic,
            lambda msg: self._handle(msg, handle_pipeline_result),
        )

        count = consumer.consume(
            timeout=timeout,
            max_messages=max_messages,
        )
        logger.info("ResultConsumer processed %d messages", count)
        return count

    @staticmethod
    def _handle(msg, handler_fn):
        """Process a single pipeline-result message."""
        job_id = msg.get("job_id")
        if not job_id:
            logger.warning("ResultConsumer: message missing job_id: %s", msg)
            return

        handler_fn(
            job_id,
            status=msg.get("status"),
            progress=msg.get("progress"),
            result_data=msg.get("result_data"),
            error_message=msg.get("error_message"),
            resolved_manifest_id=msg.get("resolved_manifest_id"),
        )


class TraceConsumer:
    """Consume agent trace events from Kafka.

    Writes **only to Redis** (not DB) for low-latency UI updates.
    The frontend polls ``/quick-status`` which reads from this cache.
    """

    def __init__(self):
        self.topic = getattr(
            settings,
            "KAFKA_TOPIC_AGENT_TRACE",
            "agent-trace-topic",
        )
        self.group_id = getattr(
            settings,
            "ORCHESTRATION_KAFKA_GROUP_ID",
            "orchestration-result-consumers",
        )

    def consume(self, max_messages=100, timeout=2.0):
        """Consume a batch of trace messages.

        Returns the number of messages successfully processed.
        """
        from kafka_service.consumer import KafkaConsumerService

        consumer = KafkaConsumerService(
            topics=[self.topic],
            group_id=f"{self.group_id}-traces",
        )
        consumer.register_handler(self.topic, self._handle)

        count = consumer.consume(
            timeout=timeout,
            max_messages=max_messages,
        )
        logger.info("TraceConsumer processed %d messages", count)
        return count

    @staticmethod
    def _handle(msg):
        """Process a single agent-trace message.

        Updates the Redis hash ``job:status:{job_id}`` with:
        - ``current_node`` — which pipeline node is active
        - ``progress_percent`` — overall % complete
        - ``last_thought`` — latest AI reasoning snippet
        - ``progress`` — per-agent status dict
        """
        job_id = msg.get("job_id")
        if not job_id:
            logger.warning("TraceConsumer: message missing job_id: %s", msg)
            return

        cache_key = f"job:status:{job_id}"

        try:
            cached = cache.get(cache_key) or {}

            # Map orchestrator node/agent status to frontend status
            node_id = msg.get("node_id") or msg.get("agent_id")
            node_status = msg.get("status", "running")
            mapped_status = _STATUS_MAP.get(node_status, node_status)

            # Update per-agent progress dict
            progress = cached.get("progress", {})
            if node_id:
                progress[node_id] = {
                    "status": mapped_status,
                    "output": msg.get("output"),
                }

            cached.update(
                {
                    "progress": progress,
                    "current_node": node_id,
                    "progress_percent": msg.get(
                        "progress_percent",
                        _calc_percent(progress),
                    ),
                    "last_thought": msg.get("last_thought"),
                }
            )

            cache.set(cache_key, cached, timeout=3600)

        except Exception:
            logger.exception(
                "TraceConsumer: failed to update Redis for job %s", job_id
            )


def _calc_percent(progress):
    """Estimate overall progress from per-agent statuses."""
    if not progress:
        return 0
    total = len(progress)
    done = sum(
        1 for v in progress.values() if v.get("status") in ("done", "failed")
    )
    return int((done / total) * 100) if total else 0
