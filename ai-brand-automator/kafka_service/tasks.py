"""
Celery Tasks for Kafka Consumer

These tasks allow running Kafka consumers as Celery workers,
providing better process management and scalability.
"""

import logging
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def consume_gateway_logs(self, max_messages: int = 100, timeout: float = 5.0):
    """
    Celery task to consume gateway logs from Kafka.
    
    This task consumes a batch of messages from the gateway-logs topic
    and stores them as AuditLog records.
    
    Args:
        max_messages: Maximum messages to consume in this batch
        timeout: Poll timeout in seconds
    
    Returns:
        Number of messages processed
    """
    try:
        from kafka_service.consumer import KafkaConsumerService, KafkaConfig
        
        consumer = KafkaConsumerService(
            topics=[KafkaConfig.TOPIC_GATEWAY_LOGS],
            group_id=f"celery-gateway-logs-{timezone.now().strftime('%Y%m%d')}",
        )
        
        count = consumer.consume(timeout=timeout, max_messages=max_messages)
        logger.info(f"Consumed {count} gateway log messages")
        
        return count
        
    except Exception as e:
        logger.error(f"Error consuming gateway logs: {e}")
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def consume_raw_events(self, max_messages: int = 50, timeout: float = 5.0):
    """
    Celery task to consume raw events from Kafka.
    
    This task consumes events from the raw-ingestion-topic and
    processes them according to their event type.
    
    Args:
        max_messages: Maximum messages to consume in this batch
        timeout: Poll timeout in seconds
    
    Returns:
        Number of messages processed
    """
    try:
        from kafka_service.consumer import KafkaConsumerService, KafkaConfig
        
        consumer = KafkaConsumerService(
            topics=[KafkaConfig.TOPIC_RAW_INGESTION],
            group_id=f"celery-raw-events-{timezone.now().strftime('%Y%m%d')}",
        )
        
        count = consumer.consume(timeout=timeout, max_messages=max_messages)
        logger.info(f"Consumed {count} raw event messages")
        
        return count
        
    except Exception as e:
        logger.error(f"Error consuming raw events: {e}")
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=1)
def process_dlq_events(self, max_messages: int = 20, timeout: float = 5.0):
    """
    Celery task to process Dead Letter Queue events.
    
    This task attempts to reprocess failed messages from the DLQ.
    
    Args:
        max_messages: Maximum messages to process
        timeout: Poll timeout in seconds
    
    Returns:
        Number of messages processed
    """
    try:
        from kafka_service.consumer import KafkaConsumerService, KafkaConfig
        from kafka_service.models import KafkaEvent
        
        consumer = KafkaConsumerService(
            topics=[KafkaConfig.TOPIC_DLQ],
            group_id="celery-dlq-processor",
        )
        
        # Custom handler for DLQ - just log and store
        def handle_dlq_message(message):
            KafkaEvent.objects.create(
                topic=KafkaConfig.TOPIC_DLQ,
                payload=message,
                status="failed",
                error_message=message.get("error", "Unknown error"),
            )
            logger.warning(f"DLQ event stored: {message.get('error')}")
        
        consumer.register_handler(KafkaConfig.TOPIC_DLQ, handle_dlq_message)
        
        count = consumer.consume(timeout=timeout, max_messages=max_messages)
        logger.info(f"Processed {count} DLQ messages")
        
        return count
        
    except Exception as e:
        logger.error(f"Error processing DLQ: {e}")
        raise


@shared_task
def publish_event_to_kafka(topic: str, event_type: str, data: dict, key: str = None):
    """
    Celery task to publish an event to Kafka.
    
    Use this task to asynchronously send events to Kafka from Django.
    
    Args:
        topic: Kafka topic to publish to
        event_type: Type of event (e.g., "user_action", "brand_update")
        data: Event payload
        key: Optional message key for partitioning
    
    Returns:
        True if successful
    """
    try:
        from kafka_service.consumer import get_producer_service
        
        message = {
            "type": event_type,
            "data": data,
            "timestamp": timezone.now().isoformat(),
        }
        
        producer = get_producer_service()
        producer.send(topic, message, key=key)
        producer.flush()
        
        logger.info(f"Published event to {topic}: {event_type}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to publish event: {e}")
        raise


@shared_task
def run_kafka_consumer_continuously():
    """
    Long-running Celery task for continuous Kafka consumption.
    
    This task runs indefinitely and consumes messages as they arrive.
    Use with caution - ensure proper worker configuration.
    
    To run:
        celery -A brand_automator worker -l info -Q kafka_consumer --concurrency=1
    """
    try:
        from kafka_service.consumer import KafkaConsumerService
        
        logger.info("Starting continuous Kafka consumer...")
        
        consumer = KafkaConsumerService()
        consumer.consume()  # This will run until stopped
        
    except Exception as e:
        logger.error(f"Kafka consumer error: {e}")
        raise


# Periodic task schedule (add to Celery Beat)
KAFKA_CELERY_BEAT_SCHEDULE = {
    'consume-gateway-logs-every-minute': {
        'task': 'kafka_service.tasks.consume_gateway_logs',
        'schedule': 60.0,  # Every minute
        'kwargs': {'max_messages': 100},
    },
    'consume-raw-events-every-30s': {
        'task': 'kafka_service.tasks.consume_raw_events',
        'schedule': 30.0,  # Every 30 seconds
        'kwargs': {'max_messages': 50},
    },
    'process-dlq-every-5-minutes': {
        'task': 'kafka_service.tasks.process_dlq_events',
        'schedule': 300.0,  # Every 5 minutes
        'kwargs': {'max_messages': 20},
    },
}
