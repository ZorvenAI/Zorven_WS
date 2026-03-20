import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def emit_analytics_event(event_type: str, tenant_id: str, data: dict):
    """Emit an analytics event to Kafka (conditional on ANALYTICS_KAFKA_ENABLED).

    Uses the existing publish_event_to_kafka Celery task from kafka_service.

    Args:
        event_type: Event type (e.g. "metrics.extracted", "brand.affinity.rejected")
        tenant_id: Tenant ID for topic partitioning
        data: Event payload dict
    """
    if not getattr(settings, "ANALYTICS_KAFKA_ENABLED", False):
        return

    topic = f"analytics.{event_type}.{tenant_id}"

    try:
        from kafka_service.tasks import publish_event_to_kafka

        publish_event_to_kafka.delay(
            topic=topic,
            event_type=event_type,
            data=data,
            key=str(tenant_id),
        )
    except Exception as e:
        logger.warning("Failed to emit analytics event %s: %s", event_type, e)
