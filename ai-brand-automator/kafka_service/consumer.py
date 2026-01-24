"""
Kafka Consumer Service for AI Brand Automator

This module provides Kafka consumer functionality to process events
from Kong Gateway and other producers.

Topics:
- gateway-logs: Request/response logs from Kong Gateway
- raw-ingestion-topic: Raw events from /ingest/event endpoint
- dlq-events: Dead letter queue for failed message processing

Usage:
    # Run as standalone consumer
    python -m kafka_service.consumer

    # Or use Celery task
    from kafka_service.tasks import consume_kafka_messages
    consume_kafka_messages.delay()
"""

import json
import logging
from typing import Callable, Dict, Any, Optional
from datetime import datetime
from decouple import config

logger = logging.getLogger(__name__)


class KafkaConfig:
    """Kafka connection configuration"""
    
    BOOTSTRAP_SERVERS = config("KAFKA_BOOTSTRAP_SERVERS", default="localhost:9092")
    GROUP_ID = config("KAFKA_CONSUMER_GROUP_ID", default="brand-automator-consumers")
    AUTO_OFFSET_RESET = config("KAFKA_AUTO_OFFSET_RESET", default="earliest")
    ENABLE_AUTO_COMMIT = config("KAFKA_ENABLE_AUTO_COMMIT", default=True, cast=bool)
    SESSION_TIMEOUT_MS = config("KAFKA_SESSION_TIMEOUT_MS", default=30000, cast=int)
    
    # Topics
    TOPIC_GATEWAY_LOGS = "gateway-logs"
    TOPIC_RAW_INGESTION = "raw-ingestion-topic"
    TOPIC_DLQ = "dlq-events"


class KafkaConsumerService:
    """
    Kafka Consumer Service for processing messages from various topics.
    
    This service uses confluent-kafka for high-performance message consumption.
    """
    
    def __init__(self, topics: list = None, group_id: str = None):
        """
        Initialize Kafka consumer.
        
        Args:
            topics: List of topics to subscribe to
            group_id: Consumer group ID (defaults to config)
        """
        self.topics = topics or [
            KafkaConfig.TOPIC_GATEWAY_LOGS,
            KafkaConfig.TOPIC_RAW_INGESTION,
        ]
        self.group_id = group_id or KafkaConfig.GROUP_ID
        self.consumer = None
        self.running = False
        
        # Message handlers by topic
        self._handlers: Dict[str, Callable] = {
            KafkaConfig.TOPIC_GATEWAY_LOGS: self._handle_gateway_log,
            KafkaConfig.TOPIC_RAW_INGESTION: self._handle_raw_event,
        }
    
    def _create_consumer(self):
        """Create and configure Kafka consumer"""
        try:
            from confluent_kafka import Consumer, KafkaError
            
            config = {
                'bootstrap.servers': KafkaConfig.BOOTSTRAP_SERVERS,
                'group.id': self.group_id,
                'auto.offset.reset': KafkaConfig.AUTO_OFFSET_RESET,
                'enable.auto.commit': KafkaConfig.ENABLE_AUTO_COMMIT,
                'session.timeout.ms': KafkaConfig.SESSION_TIMEOUT_MS,
            }
            
            self.consumer = Consumer(config)
            self.consumer.subscribe(self.topics)
            logger.info(f"Kafka consumer created, subscribed to: {self.topics}")
            
        except ImportError:
            logger.error("confluent-kafka not installed. Run: pip install confluent-kafka")
            raise
        except Exception as e:
            logger.error(f"Failed to create Kafka consumer: {e}")
            raise
    
    def register_handler(self, topic: str, handler: Callable[[Dict[str, Any]], None]):
        """
        Register a custom message handler for a topic.
        
        Args:
            topic: Topic name
            handler: Function that takes a message dict as argument
        """
        self._handlers[topic] = handler
        logger.info(f"Registered handler for topic: {topic}")
    
    def _handle_gateway_log(self, message: Dict[str, Any]):
        """
        Handle gateway log messages from Kong.
        
        These messages contain request/response information for audit purposes.
        """
        try:
            # Import Django models here to avoid circular imports
            from django.utils import timezone
            
            # Extract relevant fields from Kong log
            request = message.get("request", {})
            response = message.get("response", {})
            latencies = message.get("latencies", {})
            
            log_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "client_ip": message.get("client_ip"),
                "method": request.get("method"),
                "uri": request.get("uri"),
                "status": response.get("status"),
                "latency_kong": latencies.get("kong"),
                "latency_proxy": latencies.get("proxy"),
                "latency_request": latencies.get("request"),
                "consumer": message.get("consumer", {}).get("username"),
                "service": message.get("service", {}).get("name"),
                "route": message.get("route", {}).get("name"),
            }
            
            # Log to Django logger (could also store in database)
            logger.info(f"Gateway Log: {json.dumps(log_entry)}")
            
            # Optionally store in database for analytics
            self._store_audit_log(log_entry)
            
        except Exception as e:
            logger.error(f"Error handling gateway log: {e}")
            self._send_to_dlq(message, str(e))
    
    def _handle_raw_event(self, message: Dict[str, Any]):
        """
        Handle raw event ingestion messages.
        
        These are custom events sent to /ingest/event endpoint.
        """
        try:
            event_type = message.get("type", "unknown")
            event_data = message.get("data", {})
            
            logger.info(f"Processing raw event: type={event_type}")
            
            # Route to specific handler based on event type
            if event_type == "user_action":
                self._process_user_action(event_data)
            elif event_type == "brand_update":
                self._process_brand_update(event_data)
            elif event_type == "content_scheduled":
                self._process_content_scheduled(event_data)
            else:
                logger.warning(f"Unknown event type: {event_type}")
            
        except Exception as e:
            logger.error(f"Error handling raw event: {e}")
            self._send_to_dlq(message, str(e))
    
    def _process_user_action(self, data: Dict[str, Any]):
        """Process user action events for analytics"""
        logger.info(f"User action: {data.get('action')} by user {data.get('user_id')}")
        # TODO: Store in analytics database or send to analytics service
    
    def _process_brand_update(self, data: Dict[str, Any]):
        """Process brand update events"""
        logger.info(f"Brand update for company {data.get('company_id')}")
        # TODO: Trigger any post-update workflows
    
    def _process_content_scheduled(self, data: Dict[str, Any]):
        """Process content scheduling events"""
        logger.info(f"Content scheduled: {data.get('content_id')}")
        # TODO: Update automation schedules
    
    def _store_audit_log(self, log_entry: Dict[str, Any]):
        """
        Store audit log entry in database.
        
        This creates a record in the AuditLog model for compliance and debugging.
        """
        try:
            # Import here to avoid circular imports
            from kafka_service.models import AuditLog
            
            AuditLog.objects.create(
                timestamp=log_entry.get("timestamp"),
                client_ip=log_entry.get("client_ip"),
                method=log_entry.get("method"),
                uri=log_entry.get("uri"),
                status_code=log_entry.get("status"),
                latency_ms=log_entry.get("latency_request"),
                consumer=log_entry.get("consumer"),
                service=log_entry.get("service"),
                route=log_entry.get("route"),
            )
        except Exception as e:
            logger.warning(f"Failed to store audit log: {e}")
    
    def _send_to_dlq(self, message: Dict[str, Any], error: str):
        """
        Send failed message to Dead Letter Queue.
        
        Args:
            message: Original message that failed processing
            error: Error description
        """
        try:
            from confluent_kafka import Producer
            
            producer = Producer({
                'bootstrap.servers': KafkaConfig.BOOTSTRAP_SERVERS,
            })
            
            dlq_message = {
                "original_message": message,
                "error": error,
                "timestamp": datetime.utcnow().isoformat(),
            }
            
            producer.produce(
                KafkaConfig.TOPIC_DLQ,
                json.dumps(dlq_message).encode('utf-8'),
            )
            producer.flush()
            
            logger.info(f"Sent message to DLQ: {error}")
            
        except Exception as e:
            logger.error(f"Failed to send to DLQ: {e}")
    
    def consume(self, timeout: float = 1.0, max_messages: int = None, max_duration: float = 10.0):
        """
        Start consuming messages from Kafka.
        
        Args:
            timeout: Poll timeout in seconds
            max_messages: Maximum messages to consume (None for unlimited)
            max_duration: Maximum time to run the consumer loop in seconds (default 10s)
        """
        import time
        
        if not self.consumer:
            self._create_consumer()
        
        self.running = True
        message_count = 0
        empty_poll_count = 0
        max_empty_polls = 3  # Stop after 3 empty polls (no messages and no Kafka)
        start_time = time.time()
        
        logger.info(f"Starting Kafka consumer for topics: {self.topics}")
        
        try:
            while self.running:
                # Check max duration
                if time.time() - start_time > max_duration:
                    logger.info(f"Reached max duration: {max_duration}s")
                    break
                
                msg = self.consumer.poll(timeout)
                
                if msg is None:
                    empty_poll_count += 1
                    if empty_poll_count >= max_empty_polls:
                        logger.info(f"No messages after {empty_poll_count} polls, stopping")
                        break
                    continue
                
                # Reset empty poll counter on valid message
                empty_poll_count = 0
                
                if msg.error():
                    from confluent_kafka import KafkaError
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        logger.debug(f"Reached end of partition: {msg.topic()}/{msg.partition()}")
                    else:
                        logger.error(f"Kafka error: {msg.error()}")
                    continue
                
                # Process message
                try:
                    topic = msg.topic()
                    value = json.loads(msg.value().decode('utf-8'))
                    
                    handler = self._handlers.get(topic)
                    if handler:
                        handler(value)
                    else:
                        logger.warning(f"No handler for topic: {topic}")
                    
                    message_count += 1
                    
                    if max_messages and message_count >= max_messages:
                        logger.info(f"Reached max messages: {max_messages}")
                        break
                        
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to decode message: {e}")
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    
        except KeyboardInterrupt:
            logger.info("Consumer interrupted by user")
        finally:
            self.stop()
        
        return message_count
    
    def stop(self):
        """Stop the consumer gracefully"""
        self.running = False
        if self.consumer:
            self.consumer.close()
            logger.info("Kafka consumer stopped")


class KafkaProducerService:
    """
    Kafka Producer Service for sending messages to Kafka topics.
    
    Use this to publish events from Django to Kafka for async processing.
    """
    
    def __init__(self):
        self.producer = None
    
    def _create_producer(self):
        """Create Kafka producer"""
        try:
            from confluent_kafka import Producer
            
            self.producer = Producer({
                'bootstrap.servers': KafkaConfig.BOOTSTRAP_SERVERS,
                'acks': 'all',
            })
            logger.info("Kafka producer created")
            
        except ImportError:
            logger.error("confluent-kafka not installed")
            raise
    
    def send(self, topic: str, message: Dict[str, Any], key: str = None):
        """
        Send a message to a Kafka topic.
        
        Args:
            topic: Target topic
            message: Message payload (will be JSON serialized)
            key: Optional message key for partitioning
        """
        if not self.producer:
            self._create_producer()
        
        try:
            value = json.dumps(message).encode('utf-8')
            key_bytes = key.encode('utf-8') if key else None
            
            self.producer.produce(
                topic,
                value=value,
                key=key_bytes,
                callback=self._delivery_callback,
            )
            self.producer.poll(0)  # Trigger delivery callbacks
            
        except Exception as e:
            logger.error(f"Failed to send message to {topic}: {e}")
            raise
    
    def flush(self, timeout: float = 10.0):
        """Flush pending messages"""
        if self.producer:
            self.producer.flush(timeout)
    
    def _delivery_callback(self, err, msg):
        """Callback for message delivery confirmation"""
        if err:
            logger.error(f"Message delivery failed: {err}")
        else:
            logger.debug(f"Message delivered to {msg.topic()}[{msg.partition()}]")


# Singleton instances
_consumer_service: Optional[KafkaConsumerService] = None
_producer_service: Optional[KafkaProducerService] = None


def get_consumer_service() -> KafkaConsumerService:
    """Get or create the Kafka consumer service singleton"""
    global _consumer_service
    if _consumer_service is None:
        _consumer_service = KafkaConsumerService()
    return _consumer_service


def get_producer_service() -> KafkaProducerService:
    """Get or create the Kafka producer service singleton"""
    global _producer_service
    if _producer_service is None:
        _producer_service = KafkaProducerService()
    return _producer_service


if __name__ == "__main__":
    # Run consumer directly
    import django
    django.setup()
    
    consumer = KafkaConsumerService()
    consumer.consume()
